"""Generate one SubscriptionInvoice per landlord for the current period.

Phase 2B platform-fee rail. Distinct from rent collection: the invoice this
command produces is KRIB's bill TO the landlord for using the platform, not
the tenant's bill to the landlord. Idempotent: re-running for the same period
returns the existing rows untouched (the (landlord, period) DB unique
constraint is the authoritative guard).

Usage:
  python manage.py generate_subscription_invoices               # current month
  python manage.py generate_subscription_invoices --period 2026-06
  python manage.py generate_subscription_invoices --dry-run     # report only
"""

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from core.models import (
    Profile,
    SubscriptionInvoice,
)
from core.services import (
    current_subscription_period,
    generate_subscription_invoice_for_landlord,
    subscription_billable_units_qs,
)
from django.contrib.auth.models import User


def _money(value):
    return f"KES {Decimal(value or 0):,.2f}"


class Command(BaseCommand):
    help = "Generate KRIB platform-fee subscription invoices for all landlords for a billing period."

    def add_arguments(self, parser):
        parser.add_argument(
            "--period",
            help='Override billing period (YYYY-MM). Defaults to the current month.',
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute counts/amounts without writing invoices.",
        )

    def handle(self, *args, **options):
        write = self.stdout.write

        period = (options.get("period") or current_subscription_period()).strip()
        if len(period) != 7 or period[4] != "-":
            raise CommandError(f"--period must be YYYY-MM, got: {period!r}")

        dry_run = bool(options.get("dry_run"))

        write(self.style.MIGRATE_HEADING(
            f"=== Subscription invoice generation: period={period} dry_run={dry_run} ==="
        ))

        landlords = (
            User.objects.filter(profile__role=Profile.ROLE_LANDLORD)
            .order_by("id")
        )

        stats = {
            "scanned": 0,
            "created": 0,
            "existing": 0,
            "skipped_no_units": 0,
            "free_tier": 0,
            "pending": 0,
            "total_billable_kes": Decimal("0.00"),
        }

        for landlord in landlords:
            stats["scanned"] += 1
            count = subscription_billable_units_qs(landlord).count()
            existing = SubscriptionInvoice.objects.filter(
                landlord=landlord, period=period
            ).first()
            if existing:
                stats["existing"] += 1
                self._report_invoice(landlord, existing, prefix="existing")
                continue
            if count == 0:
                stats["skipped_no_units"] += 1
                write(f"  landlord={landlord.id} {landlord.username}: no billable units, skipped")
                continue
            if dry_run:
                write(f"  landlord={landlord.id} {landlord.username}: would create invoice for {count} unit(s)")
                continue

            invoice, created = generate_subscription_invoice_for_landlord(
                landlord, period
            )
            if not invoice:
                stats["skipped_no_units"] += 1
                continue
            if created:
                stats["created"] += 1
                self._report_invoice(landlord, invoice, prefix="created")
            else:
                stats["existing"] += 1
                self._report_invoice(landlord, invoice, prefix="existing")

        # Re-pull aggregates from the DB so the summary is consistent whether
        # we wrote rows this run or not.
        if not dry_run:
            invoices_for_period = SubscriptionInvoice.objects.filter(period=period)
            stats["free_tier"] = invoices_for_period.filter(
                status=SubscriptionInvoice.STATUS_FREE_TIER
            ).count()
            stats["pending"] = invoices_for_period.filter(
                status=SubscriptionInvoice.STATUS_PENDING
            ).count()
            stats["total_billable_kes"] = sum(
                (inv.amount for inv in invoices_for_period.filter(
                    status=SubscriptionInvoice.STATUS_PENDING
                )),
                Decimal("0.00"),
            )

        write("")
        write(self.style.HTTP_INFO("Summary"))
        write(f"  scanned             : {stats['scanned']}")
        write(f"  created             : {stats['created']}")
        write(f"  pre-existing        : {stats['existing']}")
        write(f"  skipped (0 units)   : {stats['skipped_no_units']}")
        if not dry_run:
            write(f"  free-tier invoices  : {stats['free_tier']}")
            write(f"  pending invoices    : {stats['pending']}")
            write(f"  total billable      : {_money(stats['total_billable_kes'])}")
        write(self.style.SUCCESS("Subscription invoice generation complete."))

    def _report_invoice(self, landlord, invoice, *, prefix):
        self.stdout.write(
            f"  {prefix:>8} landlord={landlord.id} {landlord.username} "
            f"period={invoice.period} units={invoice.billable_units_count} "
            f"status={invoice.status} amount={_money(invoice.amount)}"
        )
