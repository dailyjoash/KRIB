"""Provider-agnostic payment core for KRIB.

IntaSend is the first provider adapter wired in here. Stripe and PayPal go
through the same `apply_payment_event` entry point so security checks
(amount/currency/lease/tenant/idempotency) cannot diverge between providers.
A future Pesapal (or other Kenyan PSP) adapter only needs to:
  1. expose a webhook view that verifies its own signature,
  2. produce a `PaymentEvent` via its own `normalize_*` helper,
  3. call `apply_payment_event(event)`.
"""

from .core import (  # noqa: F401
    PROVIDER_INTASEND,
    PROVIDER_PAYPAL,
    PROVIDER_STRIPE,
    PaymentEvent,
    PaymentEventResult,
    PaymentEventStatus,
    apply_payment_event,
    reconcile_successful_unallocated_payments,
)
from .intasend import normalize_intasend_callback  # noqa: F401
from .paypal import normalize_paypal_capture  # noqa: F401
from .stripe import normalize_stripe_event  # noqa: F401
