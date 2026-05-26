# KRIB payment providers

KRIB currently uses **IntaSend** as the primary M-Pesa rail. The payment
layer is intentionally provider-agnostic so a Pesapal (or other PSP) adapter
can be added without touching the views or the wallet/ledger logic.

## Architecture

```
HTTPS request
   │
   ▼
provider webhook view (in core/views.py)
   │   verify HMAC / SDK signature
   │
   ▼
provider normalizer (in core/payments/<provider>.py)
   │   return PaymentEvent(provider, reference, amount, currency,
   │                       lease_id, tenant_id, status, ...)
   │
   ▼
apply_payment_event (in core/payments/core.py)
   │   - select_for_update on PaymentTransaction
   │   - idempotency (already-terminal → no-op)
   │   - amount / currency / lease / tenant verification
   │   - state transition under the lock
   │
   ▼
post-success side effects in the view
   - save_payment_receipt
   - send_sms
   - _allocate_success_payment (ledger credit, runs inside transaction)
```

Every security check that protects payment integrity (amount match, currency
match, lease/tenant match, idempotency) lives in `apply_payment_event`.
Adding a new provider only requires that provider's signature check + a
normalizer; you cannot accidentally bypass any of the integrity checks.

## Adding a new provider (e.g. Pesapal)

1. Create `backend/core/payments/<provider>.py` with one function:

   ```python
   def normalize_<provider>_event(payload) -> PaymentEvent:
       ...
   ```

   - Pull out the provider's invoice/transaction id (this becomes
     `merchant_reference` — KRIB stores it as `PaymentTransaction.checkout_request_id`
     so the local row can be looked up).
   - Pull out amount + currency. Normalize cents → 2dp decimals where needed.
   - Pull out the lease and tenant ids from whatever metadata channel the
     provider gives you. If the provider does not carry them, return `None`
     and let the verifier rely on `merchant_reference` alone.
   - Set `status` to one of `PaymentEventStatus.{SUCCESS,FAILED,PENDING,IGNORED}`.

2. Add a view (or extend STKInitiateView) that:

   - Verifies the provider's signature **before** calling the normalizer.
   - Builds the `PaymentEvent` and calls `apply_payment_event(event)`.
   - Triggers receipt + SMS side effects only when `result.ok and result.code == "applied"`.

3. Import the normalizer from `core/payments/__init__.py`.

That is the whole integration. Do not write your own duplicate
"already-processed?" check, "amount-matches?" check, or ledger credit —
the core handles them.

## Required environment

| Variable | Notes |
| --- | --- |
| `INTASEND_API_TOKEN` | Primary M-Pesa token. |
| `INTASEND_PUBLISHABLE_KEY` | Required by the IntaSend SDK. |
| `INTASEND_WEBHOOK_SECRET` | HMAC secret. Must be ≥ 32 chars in production — `settings.py` refuses to boot otherwise. |
| `INTASEND_TEST_MODE` | `1` for sandbox, `0` for live. |
| `DEFAULT_PAYMENT_CURRENCY` | Currency the payment core compares incoming events against. Defaults to `KES`. |
| `STRIPE_SECRET_KEY` | Optional; if set, `STRIPE_WEBHOOK_SECRET` must also be set. |
| `STRIPE_WEBHOOK_SECRET` | Enforced at boot whenever Stripe key is set. |
| `PAYPAL_CLIENT_ID` / `PAYPAL_SECRET` | Optional. |

## Logging policy

The payment core logs only `provider`, local `payment_id`, and the provider's
own event id. Raw provider payloads are run through `redact_payment_payload`
before being stored on `PaymentTransaction.raw_callback`, and never
emitted directly to logs. See `core/payments/redact.py`.
