"""Stripe → PaymentEvent adapter.

The view is responsible for `stripe.Webhook.construct_event` BEFORE calling
us. This module only normalizes the verified event into a PaymentEvent.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, Optional

from .core import PROVIDER_STRIPE, PaymentEvent, PaymentEventStatus
from .redact import redact_payment_payload


def _amount_from_intent(intent: Mapping[str, Any]) -> Optional[Decimal]:
    """Stripe amounts are integers in the smallest currency unit (cents).
    Convert back to a 2dp decimal for comparison against our local amount."""
    value = intent.get("amount") or intent.get("amount_received")
    if value is None:
        return None
    try:
        return (Decimal(int(value)) / Decimal(100)).quantize(Decimal("0.01"))
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_stripe_event(event: Mapping[str, Any]) -> PaymentEvent:
    intent = (event.get("data") or {}).get("object") or {}
    intent_id = str(intent.get("id") or "").strip()
    metadata = intent.get("metadata") or {}
    event_type = str(event.get("type") or "").lower()

    if event_type == "payment_intent.succeeded":
        status = PaymentEventStatus.SUCCESS
    elif event_type == "payment_intent.payment_failed":
        status = PaymentEventStatus.FAILED
    elif event_type.startswith("payment_intent."):
        status = PaymentEventStatus.PENDING
    else:
        status = PaymentEventStatus.IGNORED

    charges = (intent.get("charges") or {}).get("data") or []
    charge_id = (charges[0].get("id") if charges else None) or intent.get("latest_charge")

    # Stripe carries both lease_id and tenant_id in PaymentIntent metadata
    # (we set them in StripeCreateIntentView when initiating). A SUCCESS
    # event without that metadata is a sign the intent was created outside
    # KRIB or someone forged the event, so we fail closed.
    return PaymentEvent(
        provider=PROVIDER_STRIPE,
        provider_reference=intent_id,
        merchant_reference=intent_id,  # we store intent.id as checkout_request_id
        status=status,
        amount=_amount_from_intent(intent),
        currency=(intent.get("currency") or "").upper() or None,
        lease_id=_int_or_none(metadata.get("lease_id")),
        tenant_id=_int_or_none(metadata.get("tenant_id")),
        raw_event_id=str(event.get("id") or "") or None,
        transaction_code=str(charge_id) if charge_id else None,
        redacted_payload=redact_payment_payload(
            {
                "event_id": event.get("id"),
                "type": event_type,
                "intent_id": intent_id,
                "metadata": metadata,
            }
        ),
        required_for_success=frozenset({"lease_id", "tenant_id"}),
    )
