"""Operator-runnable safety net for payments stuck SUCCESS-but-not-allocated.

Background: when a provider callback marks a payment successful but the
follow-on `_allocate_success_payment` call raises (DB hiccup, deadlock,
etc.), the payment row is left with `status=SUCCESS, allocation_done=False`.
The next duplicate webhook re-runs allocation automatically, but if the
provider never retries we need an out-of-band sweep. That sweep is this
command.

Safe to run repeatedly: the underlying `_allocate_success_payment` is
idempotent (re-checks `allocation_done` inside its own row lock).

Suggested schedule: every 5-15 minutes via cron, plus on-demand after any
incident report involving missing landlord credits.
"""

from django.core.management.base import BaseCommand

from core.payments import reconcile_successful_unallocated_payments


class Command(BaseCommand):
    help = "Retry ledger allocation for payments stuck SUCCESS-but-not-allocated."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of payments to process in this run (default: all).",
        )

    def handle(self, *args, **options):
        stats = reconcile_successful_unallocated_payments(limit=options.get("limit"))
        message = (
            "Payment allocation reconciliation complete. "
            f"Retried: {stats['retried']}. OK: {stats['ok']}. Failed: {stats['failed']}."
        )
        self.stdout.write(self.style.SUCCESS(message))
