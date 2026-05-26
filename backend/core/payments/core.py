"""Internal normalized payment event format and shared transition logic.

Every provider adapter normalizes its webhook/capture payload into a
`PaymentEvent`, then calls `apply_payment_event`. The shared transition does:
  - resolve the local PaymentTransaction row by provider_reference
  - lock that row (`select_for_update`) so duplicate callbacks are idempotent
  - verify amount, currency, lease_id, tenant_id against the saved payment
  - update status under the lock; trigger allocation + side effects once
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping, Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


PROVIDER_INTASEND = "intasend"
PROVIDER_STRIPE = "stripe"
PROVIDER_PAYPAL = "paypal"


class PaymentEventStatus:
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    IGNORED = "ignored"  # intermediate provider state we don't act on


@dataclass(frozen=True)
class PaymentEvent:
    """Normalized payment event.

    Fields are intentionally minimal. Providers must populate everything they
    can; missing fields cause the verifier to fail closed.

    `required_for_success` is the per-provider set of additional fields that
    MUST be present on a SUCCESS event. amount + currency + merchant_reference
    are always required for SUCCESS (enforced by the core); each provider
    adds whatever else is structurally available (e.g. Stripe always has
    metadata.tenant_id because we set it at intent-create time).
    """

    provider: str
    provider_reference: str  # invoice id, payment_intent id, paypal order id
    merchant_reference: str  # local PaymentTransaction.checkout_request_id
    status: str  # PaymentEventStatus
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    lease_id: Optional[int] = None
    tenant_id: Optional[int] = None
    raw_event_id: Optional[str] = None  # provider's own event/dedup id
    # Provider-specific transaction code we want to record (M-Pesa receipt
    # number, Stripe charge id, PayPal capture id).
    transaction_code: Optional[str] = None
    # Minimal redacted callback we are willing to persist. Should NOT contain
    # full phone numbers, emails, payer names or tokens. Use the redactor
    # before populating this field.
    redacted_payload: Mapping[str, Any] = field(default_factory=dict)
    # Provider-declared extra fields required for SUCCESS. Subset of:
    # {"lease_id", "tenant_id"} — the core already enforces amount + currency
    # for every SUCCESS event.
    required_for_success: frozenset = field(default_factory=frozenset)


# Fields the core requires on every SUCCESS event, regardless of provider.
# A provider that cannot supply any of these MUST set the event status to
# something other than SUCCESS (e.g. PENDING / IGNORED).
_BASE_REQUIRED_FOR_SUCCESS = frozenset({"amount", "currency"})


@dataclass(frozen=True)
class PaymentEventResult:
    ok: bool
    payment_id: Optional[int] = None
    detail: str = ""
    # When ok=False this carries the machine-readable failure reason so the
    # provider view can decide whether to respond 200 (already handled),
    # 400 (mismatch), or 404 (no matching row).
    code: str = ""


# ---- internal helpers -------------------------------------------------------


def _amounts_equal(a: Decimal, b: Decimal) -> bool:
    """Tolerant equality for monetary decimals.

    Providers sometimes round to 2dp; we already store 2dp internally. We
    quantize both sides to 2dp before comparing to avoid 0.10 vs 0.100 noise.
    """
    if a is None or b is None:
        return False
    q = Decimal("0.01")
    return a.quantize(q) == b.quantize(q)


# ---- public API -------------------------------------------------------------


def _missing_required_fields(event: PaymentEvent):
    """Return the first missing-required-field code, or None if all good."""
    required = _BASE_REQUIRED_FOR_SUCCESS | (event.required_for_success or frozenset())
    for field_name in required:
        value = getattr(event, field_name, None)
        if value in (None, ""):
            return field_name
    return None


def apply_payment_event(event: PaymentEvent) -> PaymentEventResult:
    """Apply a normalized payment event to KRIB state.

    This is the single chokepoint where provider callbacks become local
    PaymentTransaction state changes. Every check that protects payment
    integrity lives here so adding a new provider cannot accidentally skip
    one. The provider adapter is responsible for SIGNATURE verification
    before calling us.

    Return codes the view layer should know about:
      - "applied":            payment just transitioned PENDING → SUCCESS.
                              View runs receipt + SMS + notification.
      - "failed_marked":      payment transitioned PENDING → FAILED.
      - "allocation_retried": payment was already SUCCESS but allocation was
                              never completed (e.g. the first allocation
                              raised). We retried it on this duplicate event.
                              The view MUST NOT re-send receipt/SMS because
                              those already ran on the original event.
      - "duplicate":          fully-applied duplicate; nothing to do.
      - "non_terminal":       provider sent an intermediate-state event.
      - "no_match":           merchant_reference does not match any local row.
      - "amount_mismatch" | "lease_mismatch" | "tenant_mismatch"
        | "currency_mismatch" | "missing_<field>": fail-closed verification.
    """
    # Local imports to keep this module light and to avoid app-loading order
    # surprises during settings boot.
    from core.models import PaymentTransaction
    from core.views import _allocate_success_payment  # type: ignore

    if not event.merchant_reference:
        logger.warning("payment.event.missing_reference provider=%s", event.provider)
        return PaymentEventResult(ok=False, detail="Missing merchant reference.", code="missing_reference")

    retry_allocation = False
    action_code: Optional[str] = None

    with transaction.atomic():
        payment = (
            PaymentTransaction.objects.select_for_update()
            .select_related("lease", "lease__unit", "lease__unit__property", "tenant")
            .filter(checkout_request_id=event.merchant_reference)
            .first()
        )
        if not payment:
            logger.info(
                "payment.event.unmatched provider=%s reference=%s",
                event.provider,
                event.merchant_reference,
            )
            return PaymentEventResult(ok=False, detail="No matching payment.", code="no_match")

        # Already-success branch:
        #   - If allocation is done already, we are a true duplicate and exit.
        #   - If allocation_done=False AND the duplicate event is still
        #     SUCCESS, we re-run allocation. This closes the failure window
        #     where the first allocation attempt crashed (logger.exception)
        #     and the payment was stuck SUCCESS-but-not-allocated.
        if payment.status == PaymentTransaction.STATUS_SUCCESS:
            if payment.allocation_done or event.status != PaymentEventStatus.SUCCESS:
                logger.info(
                    "payment.event.duplicate provider=%s payment_id=%s current_status=%s incoming=%s",
                    event.provider,
                    payment.id,
                    payment.status,
                    event.status,
                )
                return PaymentEventResult(
                    ok=True,
                    payment_id=payment.id,
                    detail="Duplicate event ignored.",
                    code="duplicate",
                )
            retry_allocation = True
            action_code = "allocation_retried"
            logger.info(
                "payment.event.allocation_retry_queued provider=%s payment_id=%s",
                event.provider,
                payment.id,
            )
        elif payment.status != PaymentTransaction.STATUS_PENDING:
            # FAILED (or any future terminal state). No-op.
            logger.info(
                "payment.event.duplicate provider=%s payment_id=%s current_status=%s incoming=%s",
                event.provider,
                payment.id,
                payment.status,
                event.status,
            )
            return PaymentEventResult(
                ok=True,
                payment_id=payment.id,
                detail="Duplicate event ignored.",
                code="duplicate",
            )

        if not retry_allocation:
            # Only act on terminal states for first-time transitions.
            # Intermediate states (PENDING/IGNORED) leave the payment alone.
            if event.status not in (PaymentEventStatus.SUCCESS, PaymentEventStatus.FAILED):
                return PaymentEventResult(
                    ok=True,
                    payment_id=payment.id,
                    detail="Non-terminal event ignored.",
                    code="non_terminal",
                )

            if event.status == PaymentEventStatus.SUCCESS:
                # ---- Mandatory-field gate ------------------------------------
                # Fail closed if the provider did not supply a field we need
                # for reconciliation. Without this guard, a SUCCESS event with
                # amount=None or missing metadata.tenant_id could mark the
                # payment successful without any cross-check at all.
                missing = _missing_required_fields(event)
                if missing:
                    logger.warning(
                        "payment.event.missing_required provider=%s payment_id=%s field=%s",
                        event.provider,
                        payment.id,
                        missing,
                    )
                    return PaymentEventResult(
                        ok=False,
                        payment_id=payment.id,
                        detail=f"Missing required field: {missing}.",
                        code=f"missing_{missing}",
                    )

                # ---- Cross-field verification --------------------------------
                # Amount: stored payment is the source of truth.
                if not _amounts_equal(event.amount, payment.amount):
                    logger.warning(
                        "payment.event.amount_mismatch provider=%s payment_id=%s",
                        event.provider,
                        payment.id,
                    )
                    return PaymentEventResult(
                        ok=False,
                        payment_id=payment.id,
                        detail="Amount mismatch.",
                        code="amount_mismatch",
                    )
                # Currency: must match the configured DEFAULT_PAYMENT_CURRENCY.
                from django.conf import settings as dj_settings
                expected_currency = (
                    getattr(dj_settings, "DEFAULT_PAYMENT_CURRENCY", "KES") or "KES"
                ).upper()
                if event.currency.upper() != expected_currency:
                    logger.warning(
                        "payment.event.currency_mismatch provider=%s payment_id=%s",
                        event.provider,
                        payment.id,
                    )
                    return PaymentEventResult(
                        ok=False,
                        payment_id=payment.id,
                        detail="Currency mismatch.",
                        code="currency_mismatch",
                    )
                # lease_id / tenant_id: only verified when the provider actually
                # supplies them. Required-ness is enforced above per provider
                # via `required_for_success`, so reaching this point with a
                # missing value means the provider does not carry it (e.g.
                # IntaSend does not encode tenant_id).
                if event.lease_id is not None and event.lease_id != payment.lease_id:
                    logger.warning(
                        "payment.event.lease_mismatch provider=%s payment_id=%s",
                        event.provider,
                        payment.id,
                    )
                    return PaymentEventResult(
                        ok=False,
                        payment_id=payment.id,
                        detail="Lease mismatch.",
                        code="lease_mismatch",
                    )
                if event.tenant_id is not None and event.tenant_id != payment.tenant_id:
                    logger.warning(
                        "payment.event.tenant_mismatch provider=%s payment_id=%s",
                        event.provider,
                        payment.id,
                    )
                    return PaymentEventResult(
                        ok=False,
                        payment_id=payment.id,
                        detail="Tenant mismatch.",
                        code="tenant_mismatch",
                    )

            # All checks passed — apply the state transition.
            payment.raw_callback = dict(event.redacted_payload) if event.redacted_payload else None
            payment.result_desc = event.status.upper()
            update_fields = ["raw_callback", "result_desc", "status"]

            if event.status == PaymentEventStatus.SUCCESS:
                payment.status = PaymentTransaction.STATUS_SUCCESS
                payment.result_code = 0
                if event.transaction_code:
                    payment.transaction_code = event.transaction_code
                    payment.mpesa_receipt = payment.mpesa_receipt or event.transaction_code
                    update_fields += ["transaction_code", "mpesa_receipt"]
                if not payment.transaction_date:
                    payment.transaction_date = timezone.now()
                    update_fields += ["transaction_date"]
                update_fields += ["result_code"]
                action_code = "applied"
            else:
                payment.status = PaymentTransaction.STATUS_FAILED
                payment.result_code = 1
                update_fields += ["result_code"]
                action_code = "failed_marked"

            payment.save(update_fields=list(dict.fromkeys(update_fields)))

            logger.info(
                "payment.event.applied provider=%s payment_id=%s status=%s reference=%s",
                event.provider,
                payment.id,
                payment.status,
                event.merchant_reference,
            )

        # The payment row is up to date inside the lock. We capture the id
        # for the post-lock allocation call. The transaction commits on the
        # `with` exit.
        needs_allocation_call = action_code in ("applied", "allocation_retried")

    # Side-effects (ledger allocation) only run for the success branch,
    # OUTSIDE the lock so a slow allocation cannot block other webhooks.
    # _allocate_success_payment is itself transactional and idempotent — it
    # re-checks allocation_done inside its own select_for_update window and
    # returns early if already allocated.
    if needs_allocation_call:
        try:
            _allocate_success_payment(payment)
        except Exception:
            logger.exception("payment.event.allocation_failed payment_id=%s", payment.id)

    detail_map = {
        "applied": "Event applied.",
        "failed_marked": "Event applied.",
        "allocation_retried": "Allocation retried.",
    }
    return PaymentEventResult(
        ok=True,
        payment_id=payment.id,
        detail=detail_map.get(action_code or "", "Event applied."),
        code=action_code or "applied",
    )


def reconcile_successful_unallocated_payments(limit: Optional[int] = None) -> dict:
    """Find PaymentTransaction rows that are SUCCESS but never had ledger
    allocation completed, and retry allocation safely.

    Used by:
      - `manage.py reconcile_payment_allocations` (operator-triggered or cron)
      - Anywhere a periodic safety-net is wanted to catch payments stuck
        in the SUCCESS-but-not-allocated window if a provider callback
        runs allocation, crashes, and the duplicate never arrives.

    Returns a dict of counts: {"retried": N, "ok": N, "failed": N}.
    """
    from core.models import PaymentTransaction
    from core.views import _allocate_success_payment  # type: ignore

    qs = PaymentTransaction.objects.filter(
        status=PaymentTransaction.STATUS_SUCCESS,
        allocation_done=False,
    ).order_by("created_at")
    if limit:
        qs = qs[:limit]
    payment_ids = list(qs.values_list("id", flat=True))

    stats = {"retried": 0, "ok": 0, "failed": 0}
    for payment_id in payment_ids:
        stats["retried"] += 1
        try:
            payment = (
                PaymentTransaction.objects.select_related(
                    "lease", "lease__unit", "lease__unit__property", "tenant"
                )
                .get(pk=payment_id)
            )
            # _allocate_success_payment runs inside its own select_for_update +
            # transaction.atomic so concurrent callers cannot double-credit.
            _allocate_success_payment(payment)
            payment.refresh_from_db()
            if payment.allocation_done:
                stats["ok"] += 1
            else:
                stats["failed"] += 1
        except Exception:
            stats["failed"] += 1
            logger.exception(
                "payment.reconcile.allocation_failed payment_id=%s",
                payment_id,
            )
    return stats
