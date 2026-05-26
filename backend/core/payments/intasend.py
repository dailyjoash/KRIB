"""IntaSend → PaymentEvent adapter.

IntaSend posts JSON to our STK callback URL. The signature (HMAC-SHA256) is
checked at the view boundary; this module only does normalization. Keep it
provider-specific so a future Pesapal/Daraja adapter can sit next to it
without changing the view.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional

from .core import PROVIDER_INTASEND, PaymentEvent, PaymentEventStatus
from .redact import redact_payment_payload


def _decimal_or_none(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _lease_id_from_account(account: Any) -> Optional[int]:
    """Recover lease_id from the account narrative IntaSend echoes back.

    The STK push initiator passes f"LEASE-{lease.id}" as the narrative; the
    callback returns it on `invoice.account`. If the value is malformed we
    return None and the verifier in core.py rejects on lease mismatch.
    """
    if not account:
        return None
    raw = str(account).strip()
    if raw.upper().startswith("LEASE-"):
        try:
            return int(raw[len("LEASE-") :])
        except ValueError:
            return None
    return None


def normalize_intasend_callback(payload: Mapping[str, Any]) -> PaymentEvent:
    """Translate an IntaSend webhook body into a PaymentEvent.

    Caller MUST have verified the X-IntaSend-Signature HMAC before calling.
    """
    invoice = payload.get("invoice") or {}
    invoice_id = str(payload.get("invoice_id") or invoice.get("invoice_id") or "").strip()
    state = str(payload.get("state") or invoice.get("state") or "").upper()

    if state == "COMPLETE":
        status = PaymentEventStatus.SUCCESS
    elif state == "FAILED":
        status = PaymentEventStatus.FAILED
    elif state in {"PENDING", "PROCESSING", "RETRY"}:
        status = PaymentEventStatus.PENDING
    else:
        status = PaymentEventStatus.IGNORED

    # IntaSend's M-Pesa rail does NOT carry a tenant_id of any kind. We
    # therefore only require lease_id (extracted from the `account` narrative
    # we control on STK initiation) as the extra cross-check. The binding to
    # the local payment relies on (merchant_reference == checkout_request_id)
    # plus the amount/currency match enforced by the core. A future provider
    # that can supply tenant identifiers should add "tenant_id" here.
    currency_value = (
        (invoice.get("currency") or "KES").upper()
        if isinstance(invoice, Mapping)
        else "KES"
    )
    return PaymentEvent(
        provider=PROVIDER_INTASEND,
        provider_reference=invoice_id,
        merchant_reference=invoice_id,  # we store invoice_id as checkout_request_id
        status=status,
        amount=_decimal_or_none(invoice.get("value") or invoice.get("net_amount")) if isinstance(invoice, Mapping) else None,
        currency=currency_value,
        lease_id=_lease_id_from_account(invoice.get("account")) if isinstance(invoice, Mapping) else None,
        tenant_id=None,  # IntaSend has no notion of our tenant_id
        raw_event_id=str(payload.get("event_id") or payload.get("id") or invoice_id or ""),
        transaction_code=str(invoice.get("mpesa_receipt") or "").strip() or None,
        redacted_payload=redact_payment_payload(
            {"invoice_id": invoice_id, "state": state, "raw": payload}
        ),
        required_for_success=frozenset({"lease_id"}),
    )
