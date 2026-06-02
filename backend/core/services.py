import base64
import json
import logging
import os
import re
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Lease, compute_lease_rent_status
try:
    from intasend import APIService
except ImportError:  # pragma: no cover - optional dependency in lightweight builds
    APIService = None
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
except ImportError:  # pragma: no cover - optional dependency in lightweight builds
    A4 = None
    ImageReader = None
    canvas = None

logger = logging.getLogger(__name__)


def _env_flag(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _safe_invoice_email(reference):
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(reference or "payment")).strip("-").lower()
    return f"{slug or 'payment'}@payments.krib.local"


def _intasend_error_message(payload, fallback):
    if not isinstance(payload, dict):
        return fallback

    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict):
            return first.get("message") or first.get("detail") or fallback
        return str(first)

    return (
        payload.get("error")
        or payload.get("message")
        or payload.get("detail")
        or fallback
    )


def _normalize_sms_phone_number(phone_number):
    value = re.sub(r"[^\d+]", "", str(phone_number or "").strip())
    if not value:
        return ""
    if value.startswith("+"):
        return value
    if value.startswith("0") and len(value) == 10:
        return f"+254{value[1:]}"
    if value.startswith("254") and len(value) == 12:
        return f"+{value}"
    return value


def normalize_mpesa_phone_number(phone_number):
    value = re.sub(r"\D", "", str(phone_number or "").strip())
    if not value:
        return ""
    if len(value) == 9 and value[0] in {"1", "7"}:
        return f"254{value}"
    if len(value) == 10 and value.startswith("0") and value[1] in {"1", "7"}:
        return f"254{value[1:]}"
    if len(value) == 12 and value.startswith("254") and value[3] in {"1", "7"}:
        return value
    return ""


def current_period_string(today=None):
    today = today or timezone.localdate()
    return today.strftime("%Y-%m")


def current_billing_period(today=None):
    today = today or timezone.localdate()
    return date(today.year, today.month, 1)


def reconcile_processing_payouts(limit=None):
    """Walk PROCESSING (and stale REQUESTED-with-reference) payouts and ask
    the provider for an authoritative settlement state.

    State machine applied here:
      PROCESSING + provider says SETTLED   → PAID    (release credit ledger)
      PROCESSING + provider says REJECTED  → REVERSED (refund balance)
      PROCESSING + provider says ACCEPTED  → stay PROCESSING (still in flight)
      PROCESSING + provider AMBIGUOUS      → stay PROCESSING, update last_reconciled_at
      PROCESSING + provider TRANSPORT_ERR  → stay PROCESSING, no state change

    The function is safe to run as a cron job. Each payout transitions in
    its own atomic block under select_for_update, so a parallel admin
    mark-paid call cannot race with the reconciler.

    Returns a dict of counts for logging.
    """
    from .models import LandlordBalance, LandlordPayout, LedgerTransaction

    qs = LandlordPayout.objects.filter(
        status=LandlordPayout.STATUS_PROCESSING
    ).order_by("processing_at", "id")
    if limit:
        qs = qs[:limit]

    payout_ids = list(qs.values_list("id", flat=True))
    stats = {"checked": 0, "paid": 0, "reversed": 0, "left_processing": 0, "errored": 0}

    for payout_id in payout_ids:
        stats["checked"] += 1
        try:
            payout = LandlordPayout.objects.select_related("landlord").get(pk=payout_id)
        except LandlordPayout.DoesNotExist:
            continue

        result = intasend_payout_status(payout.provider_reference)
        outcome = result.get("outcome")
        provider_status = result.get("provider_status")
        redacted = result.get("redacted_response") or {}

        now = timezone.now()

        if outcome == PAYOUT_OUTCOME_SETTLED:
            with transaction.atomic():
                locked = LandlordPayout.objects.select_for_update().get(pk=payout_id)
                if locked.status == LandlordPayout.STATUS_PROCESSING:
                    locked.status = LandlordPayout.STATUS_PAID
                    locked.paid_at = now
                    locked.provider_status = provider_status or locked.provider_status
                    locked.provider_response = redacted or locked.provider_response
                    locked.last_reconciled_at = now
                    locked.save(update_fields=[
                        "status", "paid_at", "provider_status",
                        "provider_response", "last_reconciled_at",
                    ])
                    # The original "request" ledger row becomes PAID; create
                    # the matching "paid" ledger entry exactly once.
                    LedgerTransaction.objects.filter(
                        user=locked.landlord,
                        kind=LedgerTransaction.KIND_LANDLORD_PAYOUT_REQUEST,
                        reference_text__startswith=f"payout:{locked.id}",
                    ).update(status=LedgerTransaction.STATUS_PAID)
                    LedgerTransaction.objects.create(
                        user=locked.landlord,
                        kind=LedgerTransaction.KIND_LANDLORD_PAYOUT_PAID,
                        amount=locked.amount,
                        status=LedgerTransaction.STATUS_PAID,
                        reference_text=f"payout:{locked.id};source:reconcile",
                    )
            stats["paid"] += 1
            continue

        if outcome == PAYOUT_OUTCOME_REJECTED:
            with transaction.atomic():
                locked = LandlordPayout.objects.select_for_update().get(pk=payout_id)
                if locked.status == LandlordPayout.STATUS_PROCESSING:
                    locked.status = LandlordPayout.STATUS_REVERSED
                    locked.reversed_at = now
                    locked.provider_status = provider_status or locked.provider_status
                    locked.provider_response = redacted or locked.provider_response
                    locked.last_reconciled_at = now
                    locked.save(update_fields=[
                        "status", "reversed_at", "provider_status",
                        "provider_response", "last_reconciled_at",
                    ])
                    # Restore the reserved funds under the balance lock so a
                    # concurrent new payout request sees the refunded value.
                    balance, _ = LandlordBalance.objects.get_or_create(landlord=locked.landlord)
                    balance = LandlordBalance.objects.select_for_update().get(pk=balance.pk)
                    balance.available_balance = balance.available_balance + locked.amount
                    balance.save(update_fields=["available_balance", "updated_at"])
                    LedgerTransaction.objects.filter(
                        user=locked.landlord,
                        kind=LedgerTransaction.KIND_LANDLORD_PAYOUT_REQUEST,
                        reference_text__startswith=f"payout:{locked.id}",
                    ).update(status=LedgerTransaction.STATUS_REJECTED)
            stats["reversed"] += 1
            continue

        # ACCEPTED / AMBIGUOUS / TRANSPORT_ERROR: keep PROCESSING, but
        # bump last_reconciled_at so an operator can see we tried.
        with transaction.atomic():
            locked = LandlordPayout.objects.select_for_update().get(pk=payout_id)
            locked.last_reconciled_at = now
            if provider_status:
                locked.provider_status = provider_status
            if redacted:
                locked.provider_response = redacted
            locked.save(update_fields=["last_reconciled_at", "provider_status", "provider_response"])
        if outcome == PAYOUT_OUTCOME_TRANSPORT_ERROR:
            stats["errored"] += 1
        stats["left_processing"] += 1

    return stats


def _unlock_single_ledger_row(ledger_id):
    """Unlock a single LedgerTransaction with proper row-level locking.

    Returns True iff the row transitioned from LOCKED→AVAILABLE and its
    counterpart balance row was credited. Safe to call concurrently — if two
    requests race for the same row, only one will see status=LOCKED inside
    the `select_for_update` window and the other will short-circuit.
    """
    from .models import LandlordBalance, LedgerTransaction, Profile

    with transaction.atomic():
        try:
            row = (
                LedgerTransaction.objects.select_for_update()
                .select_related("user")
                .get(pk=ledger_id)
            )
        except LedgerTransaction.DoesNotExist:
            return False

        if row.status != LedgerTransaction.STATUS_LOCKED:
            return False
        if row.available_at is None or row.available_at > timezone.now():
            return False

        if row.kind == LedgerTransaction.KIND_LANDLORD_CREDIT_RENT:
            balance, _ = LandlordBalance.objects.get_or_create(landlord=row.user)
            balance = LandlordBalance.objects.select_for_update().get(pk=balance.pk)
            balance.locked_balance = max(balance.locked_balance - row.amount, Decimal("0.00"))
            balance.available_balance += row.amount
            balance.save(update_fields=["locked_balance", "available_balance", "updated_at"])
        elif row.kind == LedgerTransaction.KIND_WALLET_CREDIT:
            profile, _ = Profile.objects.get_or_create(user=row.user)
            profile = Profile.objects.select_for_update().get(pk=profile.pk)
            profile.wallet_locked = max(profile.wallet_locked - row.amount, Decimal("0.00"))
            profile.wallet_available += row.amount
            profile.save(update_fields=["wallet_locked", "wallet_available", "updated_at"])
        else:
            return False

        row.status = LedgerTransaction.STATUS_AVAILABLE
        row.save(update_fields=["status"])
        return True


def unlock_due_wallet_for_user(user):
    """Unlock all wallet-credit ledger rows for `user` whose hold has expired.

    Returns the total amount that became newly available. Idempotent: rows
    that another caller (cron or a parallel request) already unlocked are
    skipped via the per-row lock in `_unlock_single_ledger_row`.
    """
    from .models import LedgerTransaction

    if not user or not getattr(user, "is_authenticated", False):
        return Decimal("0.00")

    due_ids = list(
        LedgerTransaction.objects.filter(
            user=user,
            kind=LedgerTransaction.KIND_WALLET_CREDIT,
            status=LedgerTransaction.STATUS_LOCKED,
            available_at__lte=timezone.now(),
        )
        .order_by("available_at", "id")
        .values_list("id", flat=True)
    )
    unlocked = Decimal("0.00")
    for ledger_id in due_ids:
        # Look up the amount inside the row lock window so we never count
        # an amount belonging to a row another worker already unlocked.
        row = LedgerTransaction.objects.filter(
            pk=ledger_id,
            status=LedgerTransaction.STATUS_LOCKED,
        ).first()
        amount = row.amount if row else Decimal("0.00")
        if _unlock_single_ledger_row(ledger_id):
            unlocked += amount
    return unlocked


def unlock_due_landlord_balance(landlord):
    """Unlock all landlord-credit ledger rows for `landlord` whose hold has
    expired. Returns the total amount that became newly available."""
    from .models import LedgerTransaction

    if not landlord or not getattr(landlord, "is_authenticated", False):
        return Decimal("0.00")

    due_ids = list(
        LedgerTransaction.objects.filter(
            user=landlord,
            kind=LedgerTransaction.KIND_LANDLORD_CREDIT_RENT,
            status=LedgerTransaction.STATUS_LOCKED,
            available_at__lte=timezone.now(),
        )
        .order_by("available_at", "id")
        .values_list("id", flat=True)
    )
    unlocked = Decimal("0.00")
    for ledger_id in due_ids:
        row = LedgerTransaction.objects.filter(
            pk=ledger_id,
            status=LedgerTransaction.STATUS_LOCKED,
        ).first()
        amount = row.amount if row else Decimal("0.00")
        if _unlock_single_ledger_row(ledger_id):
            unlocked += amount
    return unlocked


# ---------------------------------------------------------------------------
# Phase 2A: custody float drain & cutover safety
# ---------------------------------------------------------------------------

# A payout in one of these states is money KRIB has committed to send but has
# not confirmed as settled (or returned to the balance). Switching a landlord
# to direct_paybill while such a payout is in flight risks stranding or
# double-handling funds, so the cutover rail treats them as outstanding.
# Mirrors LandlordPayout.STATUS_{REQUESTED,PROCESSING,PENDING}.
NON_FINAL_PAYOUT_STATUSES = ("REQUESTED", "PROCESSING", "PENDING")


class CustodyCutoverError(Exception):
    """Raised when a landlord cannot yet be switched to direct_paybill because
    they still have outstanding custody obligations: a non-zero LandlordBalance
    (available or locked) or an in-flight LandlordPayout."""

    def __init__(self, *, available, locked, pending_count, pending_total):
        self.available = available
        self.locked = locked
        self.pending_count = pending_count
        self.pending_total = pending_total
        super().__init__(self.detail)

    @property
    def outstanding_total(self):
        return self.available + self.locked + self.pending_total

    @property
    def detail(self):
        parts = []
        if self.available:
            parts.append(f"available balance KES {self.available}")
        if self.locked:
            parts.append(f"locked balance KES {self.locked}")
        if self.pending_count:
            parts.append(
                f"{self.pending_count} in-flight payout(s) totalling KES {self.pending_total}"
            )
        joined = "; ".join(parts) or "outstanding custody obligations"
        return (
            "Cannot switch this landlord to direct Paybill while custody funds "
            f"are outstanding ({joined}). Settle the custody balance first."
        )


def _lock_landlord_balance(landlord):
    """Return the landlord's LandlordBalance row locked FOR UPDATE (or None).

    MUST be called inside a transaction.atomic() block. Exposed as a named seam
    so the cutover guard's locked read can be exercised deterministically in
    tests (simulating a credit that committed just before we took the lock)."""
    from .models import LandlordBalance

    return LandlordBalance.objects.select_for_update().filter(landlord=landlord).first()


def landlord_outstanding_custody(landlord, *, lock=False):
    """Compute a landlord's outstanding custody obligations.

    Returns dict(available, locked, pending_count, pending_total, has_outstanding).
    When lock=True the LandlordBalance row is read FOR UPDATE (call inside an
    atomic block) so the result cannot be invalidated by a concurrent credit or
    payout before the caller acts on it.
    """
    from .models import LandlordBalance, LandlordPayout

    if lock:
        balance = _lock_landlord_balance(landlord)
    else:
        balance = LandlordBalance.objects.filter(landlord=landlord).first()

    available = balance.available_balance if balance else Decimal("0.00")
    locked = balance.locked_balance if balance else Decimal("0.00")

    pending_qs = LandlordPayout.objects.filter(
        landlord=landlord,
        status__in=NON_FINAL_PAYOUT_STATUSES,
    )
    pending_count = pending_qs.count()
    pending_total = pending_qs.aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )["total"]

    has_outstanding = bool(available) or bool(locked) or pending_count > 0
    return {
        "available": available,
        "locked": locked,
        "pending_count": pending_count,
        "pending_total": pending_total,
        "has_outstanding": has_outstanding,
    }


def assert_can_switch_to_direct_paybill(landlord):
    """Raise CustodyCutoverError if the landlord still owes custody funds.

    Locks the LandlordBalance row FOR UPDATE so the check is atomic with the
    caller's subsequent collection_mode write. MUST be called inside an atomic
    block. Returns the outstanding-state dict on success.
    """
    state = landlord_outstanding_custody(landlord, lock=True)
    if state["has_outstanding"]:
        raise CustodyCutoverError(
            available=state["available"],
            locked=state["locked"],
            pending_count=state["pending_count"],
            pending_total=state["pending_total"],
        )
    return state


def switch_landlord_to_direct_paybill(landlord, *, actor=None, note=""):
    """Atomically flip a landlord to direct_paybill behind the safety rail.

    Locks the balance row, asserts zero outstanding custody obligations, sets
    collection_mode='direct_paybill', and writes a CustodyAuditLog row. If the
    rail blocks the switch, records a blocked-attempt audit row (in its own
    transaction, so it survives the guarded block's rollback) and re-raises
    CustodyCutoverError. Returns the LandlordSettings instance on success.
    """
    from .models import CustodyAuditLog, LandlordSettings

    try:
        with transaction.atomic():
            state = assert_can_switch_to_direct_paybill(landlord)
            settings_obj, _ = LandlordSettings.objects.get_or_create(
                user=landlord,
                defaults={"business_name": landlord.get_full_name().strip() or landlord.username},
            )
            settings_obj.collection_mode = LandlordSettings.COLLECTION_DIRECT_PAYBILL
            settings_obj.save(update_fields=["collection_mode"])
            CustodyAuditLog.objects.create(
                actor=actor,
                landlord=landlord,
                action=CustodyAuditLog.ACTION_CUTOVER,
                available_balance=state["available"],
                locked_balance=state["locked"],
                note=note or "",
            )
        return settings_obj
    except CustodyCutoverError as exc:
        CustodyAuditLog.objects.create(
            actor=actor,
            landlord=landlord,
            action=CustodyAuditLog.ACTION_CUTOVER_BLOCKED,
            available_balance=exc.available,
            locked_balance=exc.locked,
            note=((note or "") + " | blocked: " + exc.detail)[:2000],
        )
        raise


# ---------------------------------------------------------------------------
# Phase 2B: KRIB subscription billing rail
# ---------------------------------------------------------------------------
#
# Distinct from rent collection. KRIB charges landlords a per-billable-unit fee
# for using the platform; once the count exceeds the free-tier threshold the
# landlord pays for ALL units. These helpers are the chokepoint the management
# command, the API, and the webhook all go through so the count, the price,
# and the snapshot stay consistent across surfaces.


def _subscription_price_per_unit():
    from django.conf import settings as dj_settings

    return Decimal(str(getattr(dj_settings, "SUBSCRIPTION_PER_UNIT_KES", 50)))


def _subscription_free_tier_threshold():
    from django.conf import settings as dj_settings

    return int(getattr(dj_settings, "SUBSCRIPTION_FREE_TIER_THRESHOLD", 5))


def _subscription_grace_days():
    from django.conf import settings as dj_settings

    return int(getattr(dj_settings, "SUBSCRIPTION_GRACE_PERIOD_DAYS", 7))


def current_subscription_period(today=None):
    """The YYYY-MM string the next subscription invoice cycle bills against.

    Aliased to current_period_string so the subscription rail uses the same
    period vocabulary as the rent rail; kept as a named helper so a future
    "bill on a different cadence" change has one place to update.
    """
    return current_period_string(today=today)


def subscription_billable_units_qs(landlord):
    """Active-lease units owned by `landlord`, deduplicated.

    "Billable" = a unit with an ACTIVE lease at the moment this query runs.
    Vacant units and units whose only leases are inactive are excluded. The
    rule applies uniformly regardless of collection_mode (custody_legacy and
    direct_paybill landlords both pay the platform fee).
    """
    from .models import Lease, Unit

    return (
        Unit.objects.filter(
            property__landlord=landlord,
            leases__status=Lease.STATUS_ACTIVE,
        )
        .select_related("property")
        .distinct()
    )


def generate_subscription_invoice_for_landlord(landlord, period, *, actor=None):
    """Idempotently create (or return the existing) SubscriptionInvoice.

    Returns the SubscriptionInvoice and a "created" bool. The (landlord,
    period) DB unique constraint is the authoritative guard against
    duplicates; the get_or_create here is the optimistic fast-path.
    """
    from .models import (
        Lease,
        SubscriptionInvoice,
        SubscriptionInvoiceAuditLog,
        SubscriptionInvoiceLineItem,
    )

    per_unit = _subscription_price_per_unit()
    free_threshold = _subscription_free_tier_threshold()
    grace_days = _subscription_grace_days()

    with transaction.atomic():
        existing = SubscriptionInvoice.objects.filter(
            landlord=landlord, period=period
        ).first()
        if existing:
            return existing, False

        billable_units = list(subscription_billable_units_qs(landlord))
        count = len(billable_units)

        if count == 0:
            return None, False

        if count <= free_threshold:
            amount = Decimal("0.00")
            status_value = SubscriptionInvoice.STATUS_FREE_TIER
        else:
            amount = (per_unit * count).quantize(Decimal("0.01"))
            status_value = SubscriptionInvoice.STATUS_PENDING

        now = timezone.now()
        due_at = now + timedelta(days=grace_days) if status_value == SubscriptionInvoice.STATUS_PENDING else None
        invoice = SubscriptionInvoice.objects.create(
            landlord=landlord,
            period=period,
            billable_units_count=count,
            amount=amount,
            status=status_value,
            generated_at=now,
            due_at=due_at,
        )

        # Line items: snapshot exactly which units made up the bill. Use the
        # unit's currently-ACTIVE lease for the lease snapshot.
        for unit in billable_units:
            active_lease = (
                Lease.objects.filter(unit=unit, status=Lease.STATUS_ACTIVE)
                .order_by("-id")
                .first()
            )
            SubscriptionInvoiceLineItem.objects.create(
                invoice=invoice,
                unit=unit,
                lease=active_lease,
                unit_label=f"{unit.property.name} / {unit.unit_number}"[:255],
                lease_status_at_snapshot=(active_lease.status if active_lease else ""),
            )

        SubscriptionInvoiceAuditLog.objects.create(
            invoice=invoice,
            actor=actor,
            action=SubscriptionInvoiceAuditLog.ACTION_GENERATED,
            old_status="",
            new_status=invoice.status,
            note=f"count={count} amount={amount}",
        )

    # Tell the landlord (in-app + best-effort SMS). Free-tier landlords still
    # get notified — it's a "your bill came in at KES 0" message which doubles
    # as proof KRIB ran the cycle.
    _send_subscription_notification(
        invoice,
        title="Subscription invoice ready",
        message=_subscription_notification_message(invoice, kind="generated"),
    )
    return invoice, True


def mark_subscription_invoice_paid(invoice, *, paid_via, actor=None, note=""):
    """Idempotently mark a SubscriptionInvoice paid + write audit + notify.

    Idempotent: callers may invoke this from a webhook that fires twice. If
    the invoice is already paid we return (False, invoice) without touching
    audit / notifications a second time.
    """
    from .models import SubscriptionInvoice, SubscriptionInvoiceAuditLog

    with transaction.atomic():
        locked = (
            SubscriptionInvoice.objects.select_for_update()
            .select_related("landlord")
            .get(pk=invoice.pk)
        )
        if locked.status == SubscriptionInvoice.STATUS_PAID:
            return False, locked
        if locked.status not in (
            SubscriptionInvoice.STATUS_PENDING,
            SubscriptionInvoice.STATUS_OVERDUE,
        ):
            # Free-tier / waived invoices can't transition to paid.
            return False, locked

        old_status = locked.status
        locked.status = SubscriptionInvoice.STATUS_PAID
        locked.paid_at = timezone.now()
        locked.paid_via = paid_via or locked.paid_via
        locked.save(update_fields=["status", "paid_at", "paid_via", "updated_at"])

        SubscriptionInvoiceAuditLog.objects.create(
            invoice=locked,
            actor=actor,
            action=SubscriptionInvoiceAuditLog.ACTION_PAYMENT_CONFIRMED,
            old_status=old_status,
            new_status=locked.status,
            note=note or f"paid_via={paid_via or ''}",
        )

    _send_subscription_notification(
        locked,
        title="Subscription invoice paid",
        message=_subscription_notification_message(locked, kind="paid"),
    )
    return True, locked


def waive_subscription_invoice(invoice, *, actor, note=""):
    """Staff-only manual waive. Idempotent."""
    from .models import SubscriptionInvoice, SubscriptionInvoiceAuditLog

    with transaction.atomic():
        locked = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
        if locked.status == SubscriptionInvoice.STATUS_WAIVED:
            return False, locked
        if locked.status == SubscriptionInvoice.STATUS_PAID:
            # Don't quietly undo a paid invoice — make the operator confirm.
            return False, locked
        old_status = locked.status
        locked.status = SubscriptionInvoice.STATUS_WAIVED
        locked.save(update_fields=["status", "updated_at"])
        SubscriptionInvoiceAuditLog.objects.create(
            invoice=locked,
            actor=actor,
            action=SubscriptionInvoiceAuditLog.ACTION_WAIVED,
            old_status=old_status,
            new_status=locked.status,
            note=note or "manual waiver",
        )
    return True, locked


def apply_subscription_reminders(now=None):
    """Walk all PENDING/OVERDUE subscription invoices, send reminders and
    flip overdue when appropriate.

    Light surface only — no enforcement. SUBSCRIPTION_ENFORCEMENT_ENABLED is
    explicitly NOT read here this phase.
    """
    from django.conf import settings as dj_settings

    from .models import SubscriptionInvoice, SubscriptionInvoiceAuditLog

    now = now or timezone.now()
    grace_days = int(getattr(dj_settings, "SUBSCRIPTION_GRACE_PERIOD_DAYS", 7))
    overdue_days = int(getattr(dj_settings, "SUBSCRIPTION_OVERDUE_DAYS", 14))

    grace_cutoff = now - timedelta(days=grace_days)
    overdue_cutoff = now - timedelta(days=overdue_days)

    stats = {"grace_reminders": 0, "overdue_transitions": 0, "overdue_reminders": 0}

    pending = SubscriptionInvoice.objects.filter(status=SubscriptionInvoice.STATUS_PENDING)
    for invoice in pending.filter(generated_at__lte=grace_cutoff):
        _send_subscription_notification(
            invoice,
            title="Subscription invoice reminder",
            message=_subscription_notification_message(invoice, kind="reminder"),
        )
        stats["grace_reminders"] += 1

    for invoice in pending.filter(generated_at__lte=overdue_cutoff):
        with transaction.atomic():
            locked = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
            if locked.status != SubscriptionInvoice.STATUS_PENDING:
                continue
            old_status = locked.status
            locked.status = SubscriptionInvoice.STATUS_OVERDUE
            locked.save(update_fields=["status", "updated_at"])
            SubscriptionInvoiceAuditLog.objects.create(
                invoice=locked,
                action=SubscriptionInvoiceAuditLog.ACTION_STATUS_CHANGED,
                old_status=old_status,
                new_status=locked.status,
                note="auto: overdue threshold reached",
            )
        stats["overdue_transitions"] += 1
        _send_subscription_notification(
            locked,
            title="Subscription invoice overdue",
            message=_subscription_notification_message(locked, kind="overdue"),
        )
        stats["overdue_reminders"] += 1

    return stats


def _subscription_notification_message(invoice, *, kind):
    from .models import SubscriptionInvoice

    if invoice.status == SubscriptionInvoice.STATUS_FREE_TIER:
        threshold = _subscription_free_tier_threshold()
        return (
            f"Free tier — {invoice.billable_units_count} units under the "
            f"{threshold}-unit threshold. No payment required for {invoice.period}."
        )
    if kind == "paid":
        return (
            f"Thank you. KRIB subscription for {invoice.period} "
            f"(KES {invoice.amount}) is paid."
        )
    if kind == "reminder":
        return (
            f"KRIB subscription for {invoice.period} (KES {invoice.amount}) is "
            "still pending. Please complete payment to keep things tidy."
        )
    if kind == "overdue":
        return (
            f"KRIB subscription for {invoice.period} (KES {invoice.amount}) is "
            "overdue. Please clear it at your convenience."
        )
    return (
        f"KRIB subscription invoice for {invoice.period} is ready: "
        f"{invoice.billable_units_count} unit(s), KES {invoice.amount}."
    )


def _send_subscription_notification(invoice, *, title, message):
    """Create an in-app Notification for the landlord. SMS/email are
    intentionally not duplicated here in this phase — landlords already
    receive the in-app surface, and KRIB transactional messaging is centralized
    via the existing send_mail / send_sms helpers callers can use when they
    have a phone number to hand."""
    from .models import Notification

    Notification.objects.create(
        user=invoice.landlord,
        title=title,
        message=message,
    )


def can_withdraw_wallet(tenant_user, amount):
    """
    Returns (True, None) if withdrawal is allowed.
    Returns (False, message) if blocked.

    Wallet withdrawals are balance-based: available wallet credit is only
    withdrawable when the tenant has no outstanding balance on any active lease.
    """
    active_leases = Lease.objects.filter(
        tenant=tenant_user,
        status=Lease.STATUS_ACTIVE,
    ).select_related("unit", "unit__property")

    for lease in active_leases:
        status = compute_lease_rent_status(lease)
        if status["balance"] > Decimal("0.00"):
            return False, (
                "You have outstanding rent of KES "
                f"{status['balance']:,.2f}. Clear your "
                "balance before withdrawing."
            )

    return True, None


def period_string_to_date(period):
    if not period:
        return current_billing_period()
    year, month = period.split("-")
    return date(int(year), int(month), 1)


def build_public_url(path):
    base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if not base or not path:
        return path
    return f"{base}{path}"


def save_payment_receipt(payment):
    if payment.receipt_file:
        return payment.receipt_file.path
    if canvas is None or A4 is None:
        logger.warning("Skipping receipt generation because reportlab is not installed.")
        return None

    tenant_name = getattr(payment.tenant, "username", "Tenant")
    property_name = getattr(payment.lease.unit.property, "name", "Property")
    unit_number = getattr(payment.lease.unit, "unit_number", "-")
    business_name = os.getenv("BUSINESS_NAME", os.getenv("MPESA_BUSINESS_NAME", "KRIB"))
    support_phone = os.getenv("SUPPORT_PHONE", "")
    support_email = os.getenv("SUPPORT_EMAIL", "")
    business_address = os.getenv("BUSINESS_ADDRESS", "")
    transaction_code = payment.transaction_code or payment.mpesa_receipt or payment.checkout_request_id or f"PAY-{payment.id}"
    payment_date = payment.transaction_date or payment.created_at or timezone.now()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    _, height = A4

    y = height - 72
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(72, y, business_name)
    y -= 22
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, y, "KRIB Payment Receipt")
    y -= 18
    if business_address:
        pdf.drawString(72, y, business_address)
        y -= 16
    if support_email or support_phone:
        pdf.drawString(72, y, f"{support_email}  {support_phone}".strip())
        y -= 24

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(72, y, "Receipt Details")
    y -= 18
    pdf.setFont("Helvetica", 11)

    rows = [
        ("Tenant", tenant_name),
        ("Property", f"{property_name} / {unit_number}"),
        ("Billing Period", payment.period or current_period_string()),
        ("Payment Method", (payment.payment_method or "mpesa").upper()),
        ("Amount", f"KES {Decimal(payment.amount):,.2f}"),
        ("Transaction Code", transaction_code),
        ("Date", timezone.localtime(payment_date).strftime("%Y-%m-%d %H:%M:%S")),
    ]

    for label, value in rows:
        pdf.drawString(72, y, f"{label}: {value}")
        y -= 18

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    filename = f"receipt-{payment.id}-{current_period_string()}.pdf"
    payment.receipt_file.save(filename, ContentFile(buffer.read()), save=False)
    payment.save(update_fields=["receipt_file"])
    return payment.receipt_file.path


def _decode_data_url_file(data_url):
    if not data_url or "," not in data_url:
        return None
    _header, encoded = data_url.split(",", 1)
    try:
        return base64.b64decode(encoded)
    except Exception as exc:  # pragma: no cover - defensive parsing
        raise ValueError("Invalid base64 file data.") from exc


def _draw_wrapped_text(pdf, text, x, y, max_width, *, font_name="Helvetica", font_size=11, line_height=16):
    text = str(text or "").strip()
    if not text:
        return y

    pdf.setFont(font_name, font_size)
    words = text.split()
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or pdf.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
            continue
        pdf.drawString(x, y, current)
        y -= line_height
        current = word
    if current:
        pdf.drawString(x, y, current)
        y -= line_height
    return y


def build_lease_agreement_pdf(lease, *, signature_data_url=""):
    if canvas is None or A4 is None:
        logger.warning("Skipping lease agreement generation because reportlab is not installed.")
        return None

    signature_reader = None
    if signature_data_url:
        if ImageReader is None:
            logger.warning("Skipping lease agreement signature embedding because reportlab image tools are unavailable.")
        else:
            signature_bytes = _decode_data_url_file(signature_data_url)
            if not signature_bytes:
                raise ValueError("Invalid tenant signature data.")
            signature_reader = ImageReader(BytesIO(signature_bytes))

    property_obj = lease.unit.property
    tenant = lease.tenant
    landlord = property_obj.landlord
    landlord_settings = getattr(landlord, "landlord_settings", None)
    business_name = getattr(landlord_settings, "business_name", "") or os.getenv("BUSINESS_NAME", "KRIB")
    tenant_profile = getattr(tenant, "tenant_profile", None)
    tenant_phone = getattr(tenant_profile, "phone", "") or getattr(getattr(tenant, "profile", None), "phone_number", "")
    tenant_name = tenant.get_full_name() or tenant.username
    landlord_name = landlord.get_full_name() or landlord.username
    created_at = timezone.localtime()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 72

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(72, y, business_name)
    y -= 22
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, y, "KRIB Tenant Agreement / Lease Document")
    y -= 24

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(72, y, "Lease Summary")
    y -= 18
    pdf.setFont("Helvetica", 11)

    summary_rows = [
        ("Tenant", tenant_name),
        ("Tenant Email", tenant.email or "-"),
        ("Tenant Phone", tenant_phone or "-"),
        ("Landlord", landlord_name),
        ("Property", property_obj.name),
        ("Location", property_obj.location),
        ("Unit", lease.unit.unit_number),
        ("Unit Type", lease.unit.get_unit_type_display()),
        ("Monthly Rent", f"KES {Decimal(lease.rent_amount):,.2f}"),
        ("Deposit", f"KES {Decimal(lease.unit.deposit):,.2f}"),
        ("Start Date", lease.start_date.strftime("%d %b %Y")),
        ("End Date", lease.end_date.strftime("%d %b %Y") if lease.end_date else "Open ended"),
        ("Due Day", f"Day {lease.due_day} of each month"),
        ("Generated On", created_at.strftime("%d %b %Y %H:%M")),
    ]
    for label, value in summary_rows:
        pdf.drawString(72, y, f"{label}: {value}")
        y -= 18

    y -= 6
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(72, y, "Agreement Notes")
    y -= 20
    y = _draw_wrapped_text(
        pdf,
        f"This lease confirms that {tenant_name} will occupy unit {lease.unit.unit_number} at {property_obj.name}, "
        f"{property_obj.location}, and pay KES {Decimal(lease.rent_amount):,.2f} per month.",
        72,
        y,
        width - 144,
    )
    y = _draw_wrapped_text(
        pdf,
        f"The tenant acknowledges the agreed deposit of KES {Decimal(lease.unit.deposit):,.2f} and the monthly due day of {lease.due_day}.",
        72,
        y,
        width - 144,
    )
    y = _draw_wrapped_text(
        pdf,
        "This document was prepared electronically in KRIB and shared with the tenant, landlord, and manager as the active lease record.",
        72,
        y,
        width - 144,
    )

    y -= 8
    if y < 170:
        pdf.showPage()
        y = height - 72

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(72, y, "Tenant Signature")
    y -= 18

    if signature_reader is not None:
        pdf.drawImage(signature_reader, 72, y - 68, width=170, height=68, mask="auto", preserveAspectRatio=True)
        pdf.line(72, y - 72, 242, y - 72)
        pdf.setFont("Helvetica", 10)
        pdf.drawString(72, y - 88, f"Captured electronically on {created_at.strftime('%d %b %Y %H:%M')}")
        y -= 106
    else:
        pdf.line(72, y - 12, 242, y - 12)
        pdf.setFont("Helvetica", 10)
        pdf.drawString(72, y - 28, "No signature image was embedded.")
        y -= 44

    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, y, "Landlord approval is recorded in KRIB when this lease is created.")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    filename = f"lease-agreement-{lease.id}-{lease.unit.unit_number}.pdf"
    return filename, ContentFile(buffer.read(), name=filename)


def send_sms(phone_number, message, *, include_detail=False):
    username = os.getenv("AFRICASTALKING_USERNAME", "")
    api_key = os.getenv("AFRICASTALKING_API_KEY", "")
    sender_id = os.getenv("AFRICASTALKING_SENDER_ID", "")
    normalized_phone = _normalize_sms_phone_number(phone_number)
    if not username or not api_key or not normalized_phone:
        logger.info("Skipping SMS send because Africa's Talking is not configured.")
        result = {"ok": False, "detail": "Africa's Talking is not configured or the phone number is invalid."}
        return result if include_detail else False

    payload_dict = {
        "username": username,
        "to": normalized_phone,
        "message": message,
    }
    if sender_id:
        payload_dict["from"] = sender_id

    payload = urllib_parse.urlencode(payload_dict).encode()
    req = urllib_request.Request(
        os.getenv("AFRICASTALKING_SMS_URL", "https://api.africastalking.com/version1/messaging"),
        data=payload,
        method="POST",
        headers={
            "apiKey": api_key,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=20) as resp:
            raw_body = resp.read().decode()
            parsed = json.loads(raw_body or "{}")
            recipients = ((parsed.get("SMSMessageData") or {}).get("Recipients")) or []
            first_recipient = recipients[0] if recipients else {}
            status_text = first_recipient.get("status") or (parsed.get("SMSMessageData") or {}).get("Message") or "SMS sent."
            ok = first_recipient.get("status") == "Success" or "Sent to" in ((parsed.get("SMSMessageData") or {}).get("Message") or "")
            # Log only the boolean outcome + a short safe status word. The
            # provider body echoes the recipient phone number and was being
            # written verbatim to stdout/logs.
            logger.info("sms.send result=%s status=%s", ok, status_text[:80])
            result = {"ok": ok, "detail": status_text, "body": parsed}
            return result if include_detail else ok
    except HTTPError as exc:  # pragma: no cover - network path
        from .payments.redact import redact_text
        body = ""
        try:
            body = exc.read().decode()
        except Exception:
            body = ""
        logger.warning("sms.send.failed %s", redact_text(body or str(exc)))
        detail = body or str(exc)
        result = {"ok": False, "detail": detail}
        return result if include_detail else False
    except Exception as exc:  # pragma: no cover - network path
        from .payments.redact import redact_text
        logger.warning("sms.send.failed %s", redact_text(str(exc)))
        result = {"ok": False, "detail": str(exc)}
        return result if include_detail else False


def intasend_stk_push(phone_number, amount, reference):
    token = os.getenv("INTASEND_API_TOKEN", "").strip()
    publishable_key = os.getenv("INTASEND_PUBLISHABLE_KEY", "").strip()
    test_mode = _env_flag(os.getenv("INTASEND_TEST_MODE"), default=False)

    if not token or not publishable_key:
        return {"success": False, "error": "IntaSend is not configured."}

    if APIService is None:
        return {"success": False, "error": "IntaSend SDK is not installed."}

    try:
        service = APIService(
            token=token,
            publishable_key=publishable_key,
            test=test_mode,
        )
        response = service.collect.mpesa_stk_push(
            phone_number=phone_number,
            email=_safe_invoice_email(reference),
            amount=float(Decimal(amount)),
            narrative=str(reference or "KRIB rent payment"),
        )
    except Exception as exc:  # pragma: no cover - SDK/network path
        logger.warning("IntaSend STK push failed: %s", exc)
        return {"success": False, "error": str(exc) or "IntaSend STK push failed."}

    invoice_id = None
    if isinstance(response, dict):
        invoice_id = response.get("invoice_id") or (response.get("invoice") or {}).get("invoice_id")

    if invoice_id:
        return {"success": True, "invoice_id": str(invoice_id)}

    logger.warning("IntaSend STK push did not return an invoice id: %s", response)
    return {
        "success": False,
        "error": _intasend_error_message(response, "IntaSend STK push failed."),
    }


def _intasend_service_kwargs():
    token = os.getenv("INTASEND_API_TOKEN", "").strip()
    publishable_key = os.getenv("INTASEND_PUBLISHABLE_KEY", "").strip()
    kwargs = {
        "token": token,
        "test": _env_flag(os.getenv("INTASEND_TEST_MODE"), default=False),
    }
    if publishable_key:
        kwargs["publishable_key"] = publishable_key
    return kwargs


def _payout_beneficiary_name(payout):
    landlord = getattr(payout, "landlord", None)
    if not landlord:
        return "KRIB Landlord"
    return landlord.get_full_name() or landlord.username or "KRIB Landlord"


def _intasend_payout_error(response, fallback):
    if isinstance(response, dict):
        status = str(response.get("status") or response.get("state") or "").upper()
        if status in {"FAILED", "ERROR", "REJECTED"}:
            return _intasend_error_message(response, fallback)

        for key in ("error", "detail", "message"):
            value = response.get(key)
            if value:
                return str(value)
    return fallback


# Payout lifecycle outcomes returned by the provider adapter. The view
# translates these into LandlordPayout state transitions. Keep the surface
# narrow so Pesapal / Daraja / any other adapter cannot accidentally widen
# the contract.
PAYOUT_OUTCOME_ACCEPTED = "accepted"            # provider acknowledged; awaiting settlement → PROCESSING
PAYOUT_OUTCOME_SETTLED = "settled"              # provider explicitly confirmed settlement → PAID
PAYOUT_OUTCOME_REJECTED = "rejected"            # provider explicitly rejected pre-settlement → FAILED + restore
PAYOUT_OUTCOME_AMBIGUOUS = "ambiguous"          # no clear answer; stay PROCESSING + reconcile later
PAYOUT_OUTCOME_TRANSPORT_ERROR = "transport_error"  # never reached the provider → stay REQUESTED + reconcile later


def _extract_provider_reference(response):
    """Pull the provider's tracking identifier out of an IntaSend response.

    Reconciliation needs this id to look up the eventual settlement state.
    """
    if not isinstance(response, dict):
        return None
    for key in ("tracking_id", "id", "reference", "batch_reference"):
        value = response.get(key)
        if value:
            return str(value)
    # The collection-status SDK returns nested results.
    results = response.get("results") if isinstance(response.get("results"), list) else []
    for entry in results:
        if isinstance(entry, dict):
            for key in ("tracking_id", "id", "reference"):
                value = entry.get(key)
                if value:
                    return str(value)
    return None


# --- IntaSend status vocabulary ---------------------------------------------
# Statuses that unambiguously indicate the provider has rejected the transfer.
_INTASEND_REJECT_STATUSES = frozenset({"FAILED", "ERROR", "REJECTED", "DECLINED"})

# Statuses that unambiguously indicate the provider has SETTLED the transfer
# (the money has moved to the beneficiary). These are the only labels we
# accept as "settled" — not "SUCCESS", because for the asynchronous M-Pesa
# rail "SUCCESS" only means "request accepted into the queue".
_INTASEND_SETTLED_STATUSES = frozenset({"COMPLETED", "PAID", "SETTLED"})

# Statuses that mean "we have it, awaiting settlement". The provider may
# still mark these COMPLETED later via a callback or status lookup.
_INTASEND_ACCEPTED_STATUSES = frozenset({
    "SENT", "PROCESSING", "QUEUED", "APPROVED",
    "INITIATED", "RECEIVED", "SUCCESS",
    # IntaSend's payout API returns "SUCCESS" on the *submission* call to
    # signal "your request was accepted" — NOT "money has settled". With
    # requires_approval="YES" enabled, the actual settlement happens later
    # in their dashboard. The previous classifier promoted SUCCESS straight
    # to SETTLED here, which is the bug this pass fixes.
})


def classify_initial_intasend_payout_response(response):
    """Classification for the response returned by the INITIAL payout
    submission (`service.transfer.mpesa(...)` / `service.transfer.bank(...)`).

    Be conservative: even when the provider says "SUCCESS", treat the payout
    as accepted-but-not-settled. The reconciler / a dedicated payout-status
    webhook is the authoritative source for settlement.
    """
    if not isinstance(response, dict):
        return PAYOUT_OUTCOME_AMBIGUOUS, None

    raw_status = str(response.get("status") or response.get("state") or "").upper().strip()
    provider_reference = _extract_provider_reference(response)

    if raw_status in _INTASEND_REJECT_STATUSES:
        return PAYOUT_OUTCOME_REJECTED, provider_reference

    # Settlement is a strong claim. We only honour it on the initial
    # submission if the provider used one of the explicit settled keywords.
    # "SUCCESS" deliberately does NOT count here — it lives in
    # _INTASEND_ACCEPTED_STATUSES.
    if raw_status in _INTASEND_SETTLED_STATUSES:
        return PAYOUT_OUTCOME_SETTLED, provider_reference

    if raw_status in _INTASEND_ACCEPTED_STATUSES and provider_reference:
        return PAYOUT_OUTCOME_ACCEPTED, provider_reference

    # No explicit status but we have a tracking id → still only ACCEPTED.
    if provider_reference:
        return PAYOUT_OUTCOME_ACCEPTED, provider_reference

    # No status, no tracking id. Fail closed: ambiguous, do not auto-reverse.
    return PAYOUT_OUTCOME_AMBIGUOUS, provider_reference


def classify_intasend_payout_status_response(response):
    """Classification for the response returned by an explicit STATUS LOOKUP
    on an existing transfer (i.e. `service.transfer.status(tracking_id=...)`).

    Status-lookup responses are the authoritative source of settlement
    truth: when the provider tells us "SUCCESS" via the status endpoint it
    means the underlying transaction has been settled, not just queued.

    This is also where SETTLED keywords act as PAID.
    """
    if not isinstance(response, dict):
        return PAYOUT_OUTCOME_AMBIGUOUS, None

    raw_status = str(response.get("status") or response.get("state") or "").upper().strip()
    provider_reference = _extract_provider_reference(response)

    if raw_status in _INTASEND_REJECT_STATUSES:
        return PAYOUT_OUTCOME_REJECTED, provider_reference

    # The status lookup treats "SUCCESS" as settled, in addition to the
    # explicit settled keywords. This is the *only* IntaSend code path
    # where a "SUCCESS" string graduates a payout to PAID.
    if raw_status in _INTASEND_SETTLED_STATUSES or raw_status == "SUCCESS":
        return PAYOUT_OUTCOME_SETTLED, provider_reference

    if raw_status in _INTASEND_ACCEPTED_STATUSES and provider_reference:
        return PAYOUT_OUTCOME_ACCEPTED, provider_reference

    if provider_reference:
        return PAYOUT_OUTCOME_ACCEPTED, provider_reference

    return PAYOUT_OUTCOME_AMBIGUOUS, provider_reference


def _classify_intasend_payout_response(response):
    """Backwards-compatible alias for code that has not been updated yet.

    Behaves like `classify_initial_intasend_payout_response` because that is
    the safer of the two interpretations. New code should call one of the
    explicit variants above.
    """
    return classify_initial_intasend_payout_response(response)


def execute_intasend_payout(payout):
    """Submit a payout to IntaSend and return a structured outcome dict.

    Shape:
        {
            "outcome": one of PAYOUT_OUTCOME_*,
            "provider_reference": str | None,
            "provider_status": str | None,
            "detail": str | None,
            "redacted_response": dict,
        }
    """
    from .payments.redact import redact_payment_payload

    token = os.getenv("INTASEND_API_TOKEN", "").strip()
    if not token:
        return {
            "outcome": PAYOUT_OUTCOME_TRANSPORT_ERROR,
            "provider_reference": None,
            "provider_status": None,
            "detail": "IntaSend is not configured.",
            "redacted_response": {},
        }

    if APIService is None:
        return {
            "outcome": PAYOUT_OUTCOME_TRANSPORT_ERROR,
            "provider_reference": None,
            "provider_status": None,
            "detail": "IntaSend SDK is not installed.",
            "redacted_response": {},
        }

    # Compose the provider request first; if the destination/method itself
    # is invalid we return REJECTED *without* ever touching the provider so
    # the caller can FAIL safely and release funds.
    txn = {
        "name": _payout_beneficiary_name(payout),
        "account": str(payout.destination or "").strip(),
        "amount": float(Decimal(payout.amount)),
        # Include the local payout id and idempotency_key so the provider's
        # logs/dashboard show our cross-reference. IntaSend does not have a
        # first-class idempotency-key feature on payouts; KRIB enforces
        # idempotency on its side via LandlordPayout.idempotency_key.
        "narrative": f"KRIB payout #{payout.id} key:{payout.idempotency_key}",
    }

    if payout.method == payout.METHOD_MPESA:
        normalized_account = normalize_mpesa_phone_number(txn["account"])
        if not normalized_account:
            return {
                "outcome": PAYOUT_OUTCOME_REJECTED,
                "provider_reference": None,
                "provider_status": None,
                "detail": "Use a valid Kenyan M-Pesa number for payouts.",
                "redacted_response": {},
            }
        txn["account"] = normalized_account
    elif payout.method == payout.METHOD_BANK:
        if not getattr(payout, "bank_code", ""):
            return {
                "outcome": PAYOUT_OUTCOME_REJECTED,
                "provider_reference": None,
                "provider_status": None,
                "detail": "Bank code is required for bank payouts.",
                "redacted_response": {},
            }
        txn["bank_code"] = str(payout.bank_code).strip()
    else:
        return {
            "outcome": PAYOUT_OUTCOME_REJECTED,
            "provider_reference": None,
            "provider_status": None,
            "detail": "Unsupported payout method.",
            "redacted_response": {},
        }

    # Real provider call. Any exception below has to be classified as
    # transport_error because we cannot be sure whether the request reached
    # the provider — that's why the caller leaves the payout in REQUESTED
    # until reconciliation can ask the provider directly.
    try:
        service = APIService(**_intasend_service_kwargs())
        if payout.method == payout.METHOD_MPESA:
            response = service.transfer.mpesa(
                currency="KES",
                transactions=[txn],
                requires_approval="YES",
            )
        else:
            response = service.transfer.bank(
                currency="KES",
                transactions=[txn],
                requires_approval="YES",
            )
    except Exception as exc:  # pragma: no cover - SDK/network path
        logger.warning("payout.intasend.transport_error payout_id=%s", getattr(payout, "id", None))
        return {
            "outcome": PAYOUT_OUTCOME_TRANSPORT_ERROR,
            "provider_reference": None,
            "provider_status": None,
            "detail": str(exc) or "IntaSend payout transport error.",
            "redacted_response": {},
        }

    # Initial submission MUST use the conservative classifier — provider
    # "SUCCESS" here means "request queued", not "money settled". Only the
    # status-lookup path (used by the reconciler) can promote SUCCESS to PAID.
    outcome, provider_reference = classify_initial_intasend_payout_response(response)
    provider_status = None
    if isinstance(response, dict):
        provider_status = str(response.get("status") or response.get("state") or "").upper() or None

    redacted = redact_payment_payload(response) if isinstance(response, dict) else {}

    logger.info(
        "payout.intasend.response payout_id=%s outcome=%s provider_status=%s has_ref=%s",
        getattr(payout, "id", None),
        outcome,
        provider_status,
        bool(provider_reference),
    )

    detail = None
    if outcome == PAYOUT_OUTCOME_REJECTED:
        detail = _intasend_payout_error(response, "IntaSend payout rejected.")
    elif outcome == PAYOUT_OUTCOME_AMBIGUOUS:
        detail = _intasend_payout_error(response, "IntaSend response was ambiguous.")

    return {
        "outcome": outcome,
        "provider_reference": provider_reference,
        "provider_status": provider_status,
        "detail": detail,
        "redacted_response": redacted,
    }


def intasend_payout_status(provider_reference):
    """Ask IntaSend for the current settlement state of a previously-submitted
    transfer. Used by the reconciliation loop to upgrade PROCESSING payouts
    to PAID/REVERSED only when the provider gives a clear answer.

    Returns the same outcome shape as execute_intasend_payout(), with one
    of: SETTLED, REJECTED, ACCEPTED (still processing on their side),
    AMBIGUOUS, or TRANSPORT_ERROR.
    """
    from .payments.redact import redact_payment_payload

    if not provider_reference:
        return {
            "outcome": PAYOUT_OUTCOME_AMBIGUOUS,
            "provider_status": None,
            "detail": "No provider reference to query.",
            "redacted_response": {},
        }

    token = os.getenv("INTASEND_API_TOKEN", "").strip()
    if not token or APIService is None:
        return {
            "outcome": PAYOUT_OUTCOME_TRANSPORT_ERROR,
            "provider_status": None,
            "detail": "IntaSend is not configured.",
            "redacted_response": {},
        }

    try:
        service = APIService(**_intasend_service_kwargs())
        # The IntaSend SDK exposes transfer.status(tracking_id=...). If the
        # installed SDK version does not have this method, the reconciliation
        # loop will fail closed (TRANSPORT_ERROR) and the operator can run a
        # manual mark-paid once they verify settlement off-platform.
        status_fn = getattr(service.transfer, "status", None)
        if status_fn is None:
            return {
                "outcome": PAYOUT_OUTCOME_TRANSPORT_ERROR,
                "provider_status": None,
                "detail": "IntaSend SDK does not expose transfer.status().",
                "redacted_response": {},
            }
        response = status_fn(tracking_id=provider_reference)
    except Exception as exc:  # pragma: no cover - SDK/network path
        logger.warning("payout.intasend.status_transport_error ref=%s", provider_reference)
        return {
            "outcome": PAYOUT_OUTCOME_TRANSPORT_ERROR,
            "provider_status": None,
            "detail": str(exc) or "IntaSend status lookup failed.",
            "redacted_response": {},
        }

    # Status lookups are authoritative: this is where provider "SUCCESS" can
    # legitimately mean "settled" because the lookup endpoint reports the
    # outcome of a transfer rather than the outcome of submitting it.
    outcome, _ = classify_intasend_payout_status_response(response)
    provider_status = None
    if isinstance(response, dict):
        provider_status = str(response.get("status") or response.get("state") or "").upper() or None

    return {
        "outcome": outcome,
        "provider_status": provider_status,
        "detail": None,
        "redacted_response": redact_payment_payload(response) if isinstance(response, dict) else {},
    }


def _paypal_api_base():
    explicit = os.getenv("PAYPAL_API_BASE", "").strip()
    if explicit:
        return explicit.rstrip("/")
    mode = os.getenv("PAYPAL_MODE", "sandbox").lower()
    if mode == "live":
        return "https://api-m.paypal.com"
    return "https://api-m.sandbox.paypal.com"


def _paypal_currency():
    return os.getenv("PAYPAL_CURRENCY", "KES").strip().upper() or "KES"


def _paypal_error_result(exc, fallback):
    body = {}
    try:
        payload = exc.read().decode()
        body = json.loads(payload) if payload else {}
    except Exception:  # pragma: no cover - defensive parsing
        body = {}

    details = body.get("details") or []
    first_detail = details[0] if details else {}
    issue = first_detail.get("issue", "")
    description = first_detail.get("description") or body.get("message") or fallback

    if issue == "CURRENCY_NOT_SUPPORTED":
        description = (
            f"PayPal checkout does not support {_paypal_currency()} for this account. "
            "Use M-Pesa or change PayPal currency to a supported code."
        )

    return {
        "error": True,
        "status": getattr(exc, "code", 502),
        "issue": issue,
        "detail": description,
        "body": body,
    }


def paypal_access_token():
    client_id = os.getenv("PAYPAL_CLIENT_ID", "").strip()
    secret = os.getenv("PAYPAL_SECRET", "").strip()
    if not client_id or not secret:
        return None

    auth = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    req = urllib_request.Request(
        f"{_paypal_api_base()}/v1/oauth2/token",
        data=b"grant_type=client_credentials",
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode())
            return payload.get("access_token")
    except HTTPError as exc:
        from .payments.redact import redact_text
        error = _paypal_error_result(exc, "PayPal authentication failed.")
        logger.warning("paypal.token.failed %s", redact_text(str(error.get("detail") or "")))
        return None
    except URLError as exc:
        logger.warning("PayPal access token failed: %s", exc)
        return None


def paypal_create_order(amount, reference):
    token = paypal_access_token()
    if not token:
        return None

    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": reference,
                "amount": {
                    "currency_code": _paypal_currency(),
                    "value": f"{Decimal(amount):.2f}",
                },
            }
        ],
        "application_context": {
            "brand_name": os.getenv("BUSINESS_NAME", "KRIB"),
            "user_action": "PAY_NOW",
        },
    }
    req = urllib_request.Request(
        f"{_paypal_api_base()}/v2/checkout/orders",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as exc:
        from .payments.redact import redact_text
        error = _paypal_error_result(exc, "PayPal order creation failed.")
        logger.warning("paypal.create_order.failed %s", redact_text(str(error.get("detail") or "")))
        return error
    except URLError as exc:
        logger.warning("PayPal create order failed: %s", exc)
        return {"error": True, "status": 502, "detail": "PayPal is unreachable right now. Please try again."}


def paypal_capture_order(order_id):
    token = paypal_access_token()
    if not token:
        return None
    req = urllib_request.Request(
        f"{_paypal_api_base()}/v2/checkout/orders/{order_id}/capture",
        data=b"{}",
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as exc:
        from .payments.redact import redact_text
        error = _paypal_error_result(exc, "PayPal capture failed.")
        logger.warning("paypal.capture.failed %s", redact_text(str(error.get("detail") or "")))
        return error
    except URLError as exc:
        logger.warning("PayPal capture failed: %s", exc)
        return {"error": True, "status": 502, "detail": "PayPal is unreachable right now. Please try again."}
