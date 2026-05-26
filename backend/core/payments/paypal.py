"""PayPal → PaymentEvent adapter.

PayPal is pull-based in KRIB: the tenant clicks "Capture", we hit PayPal's
REST API server-to-server, and PayPal returns the capture JSON. The capture
is therefore trusted because we initiated the HTTPS request ourselves; this
adapter still verifies amount/currency to defend against ID-reuse or
metadata tampering on our side.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional

from .core import PROVIDER_PAYPAL, PaymentEvent, PaymentEventStatus
from .redact import redact_payment_payload


def _decimal_or_none(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def normalize_paypal_capture(
    capture: Mapping[str, Any],
    *,
    expected_lease_id: Optional[int] = None,
    expected_tenant_id: Optional[int] = None,
) -> PaymentEvent:
    """Build a PaymentEvent from a PayPal capture response.

    `expected_lease_id` and `expected_tenant_id` are supplied by the view
    because PayPal's `purchase_units[0].reference_id` is the only piece that
    carries our lease reference (encoded as f"lease-{id}-{period}"). We don't
    want to re-parse that here when the view already knows the answer.
    """
    order_id = str(capture.get("id") or "").strip()
    status = str(capture.get("status") or "").upper()

    purchase_units = capture.get("purchase_units") or []
    captures = (purchase_units[0].get("payments") or {}).get("captures") if purchase_units else []
    capture_row = (captures or [{}])[0]
    capture_id = str(capture_row.get("id") or "").strip() or None
    amount_obj = capture_row.get("amount") or (purchase_units[0].get("amount") if purchase_units else {})
    amount = _decimal_or_none((amount_obj or {}).get("value"))
    currency = ((amount_obj or {}).get("currency_code") or "").upper() or None

    if status == "COMPLETED":
        ev_status = PaymentEventStatus.SUCCESS
    elif status in {"DECLINED", "FAILED", "VOIDED", "DENIED"}:
        ev_status = PaymentEventStatus.FAILED
    elif status in {"PENDING", "APPROVED", "CREATED"}:
        ev_status = PaymentEventStatus.PENDING
    else:
        ev_status = PaymentEventStatus.IGNORED

    # PayPal: the view passes expected_lease_id/expected_tenant_id from the
    # local PaymentTransaction it already looked up before initiating the
    # capture, so we always carry both for SUCCESS events.
    return PaymentEvent(
        provider=PROVIDER_PAYPAL,
        provider_reference=order_id,
        merchant_reference=order_id,  # we store order_id as checkout_request_id
        status=ev_status,
        amount=amount,
        currency=currency,
        lease_id=expected_lease_id,
        tenant_id=expected_tenant_id,
        raw_event_id=order_id,
        transaction_code=capture_id or order_id,
        redacted_payload=redact_payment_payload(
            {
                "order_id": order_id,
                "status": status,
                "capture_id": capture_id,
            }
        ),
        required_for_success=frozenset({"lease_id", "tenant_id"}),
    )
