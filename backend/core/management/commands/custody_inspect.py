"""Read-only snapshot of the legacy KRIB-custody float.

Phase 2A operational tool. Surfaces exactly how much the custody flow still
owes landlords so an operator can settle obligations BEFORE flipping anyone to
direct_paybill. Reports:

  * aggregate available / locked balance across all LandlordBalance rows
  * landlords carrying a non-zero balance (per-landlord breakdown)
  * successful PaymentTransactions not yet allocated to a balance (gaps)
  * in-flight (non-final) LandlordPayouts
  * tenant wallet float (informational — see custody settlement runbook for the
    tenant-wallet policy: legacy-redeemable, never silently dropped)

This command NEVER mutates state. Safe to run anytime, as often as needed.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce

from core.models import (
    LandlordBalance,
    LandlordPayout,
    LandlordSettings,
    PaymentTransaction,
    Profile,
)
from core.services import NON_FINAL_PAYOUT_STATUSES


def _money(value):
    return f"KES {Decimal(value or 0):,.2f}"


def _display_name(user):
    if not user:
        return "(unknown)"
    return user.get_full_name() or user.username


class Command(BaseCommand):
    help = "Read-only snapshot of the legacy custody float (balances, gaps, in-flight payouts)."

    def handle(self, *args, **options):
        write = self.stdout.write

        write(self.style.MIGRATE_HEADING("=== KRIB custody float inspection ==="))

        # --- Aggregate landlord balances ---------------------------------
        totals = LandlordBalance.objects.aggregate(
            total_available=Coalesce(Sum("available_balance"), Decimal("0.00")),
            total_locked=Coalesce(Sum("locked_balance"), Decimal("0.00")),
        )
        nonzero = (
            LandlordBalance.objects.select_related("landlord")
            .filter(Q(available_balance__gt=0) | Q(locked_balance__gt=0))
            .order_by("-available_balance", "-locked_balance")
        )
        modes = dict(LandlordSettings.objects.values_list("user_id", "collection_mode"))

        write("")
        write(self.style.HTTP_INFO("Landlord custody balances"))
        write(f"  total available_balance : {_money(totals['total_available'])}")
        write(f"  total locked_balance    : {_money(totals['total_locked'])}")
        write(f"  landlords with non-zero balance: {nonzero.count()}")

        if nonzero:
            write("")
            write("  per-landlord breakdown:")
            write(
                "    {:>6}  {:<28} {:>16} {:>16}  {}".format(
                    "id", "name", "available", "locked", "collection_mode"
                )
            )
            for balance in nonzero:
                mode = modes.get(balance.landlord_id) or LandlordSettings.COLLECTION_CUSTODY_LEGACY
                write(
                    "    {:>6}  {:<28} {:>16} {:>16}  {}".format(
                        balance.landlord_id,
                        _display_name(balance.landlord)[:28],
                        _money(balance.available_balance),
                        _money(balance.locked_balance),
                        mode,
                    )
                )

        # --- Unallocated successful payments (reconciliation gaps) -------
        unallocated = PaymentTransaction.objects.filter(
            status=PaymentTransaction.STATUS_SUCCESS,
            allocation_done=False,
        )
        unalloc_count = unallocated.count()
        unalloc_total = unallocated.aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"))
        )["total"]
        write("")
        write(self.style.HTTP_INFO("Successful-but-unallocated PaymentTransactions"))
        write(f"  count: {unalloc_count}   total: {_money(unalloc_total)}")
        if unalloc_count:
            write(
                self.style.WARNING(
                    "  ^ these successful payments never credited a LandlordBalance; "
                    "run reconcile_payment_allocations before settling."
                )
            )

        # --- In-flight payouts -------------------------------------------
        pending = (
            LandlordPayout.objects.select_related("landlord")
            .filter(status__in=NON_FINAL_PAYOUT_STATUSES)
            .order_by("created_at")
        )
        pending_total = pending.aggregate(total=Coalesce(Sum("amount"), Decimal("0.00")))["total"]
        write("")
        write(self.style.HTTP_INFO("In-flight (non-final) LandlordPayouts"))
        write(f"  count: {pending.count()}   total: {_money(pending_total)}")
        if pending:
            write(
                "    {:>6}  {:<28} {:>16} {:<12} {}".format(
                    "id", "landlord", "amount", "status", "created_at"
                )
            )
            for payout in pending:
                write(
                    "    {:>6}  {:<28} {:>16} {:<12} {}".format(
                        payout.id,
                        _display_name(payout.landlord)[:28],
                        _money(payout.amount),
                        payout.status,
                        payout.created_at.strftime("%Y-%m-%d %H:%M"),
                    )
                )

        # --- Tenant wallet float (informational) -------------------------
        wallet = Profile.objects.filter(role=Profile.ROLE_TENANT).aggregate(
            total_available=Coalesce(Sum("wallet_available"), Decimal("0.00")),
            total_locked=Coalesce(Sum("wallet_locked"), Decimal("0.00")),
        )
        wallet_holders = Profile.objects.filter(
            role=Profile.ROLE_TENANT
        ).filter(Q(wallet_available__gt=0) | Q(wallet_locked__gt=0)).count()
        write("")
        write(self.style.HTTP_INFO("Tenant wallet float (informational)"))
        write(f"  total wallet_available : {_money(wallet['total_available'])}")
        write(f"  total wallet_locked    : {_money(wallet['total_locked'])}")
        write(f"  tenants with non-zero wallet: {wallet_holders}")
        write(
            "  policy: tenant wallet credits stay legacy-redeemable and are never "
            "dropped on landlord cutover (see docs/custody_settlement_runbook.md)."
        )

        write("")
        write(self.style.SUCCESS("Inspection complete (read-only; no state changed)."))
