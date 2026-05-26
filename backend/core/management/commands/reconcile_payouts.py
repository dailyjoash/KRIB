"""Periodic reconciliation for landlord payouts.

Payouts move through this lifecycle:

    REQUESTED -> PROCESSING -> { PAID | REVERSED }
                            \-> FAILED (from REQUESTED on provider reject)

When a payout sits in PROCESSING for long it means the provider accepted
the transfer but has not yet sent us a callback confirming settlement.
This command asks the provider directly and finalizes the state.

Safe to run repeatedly: each transition happens inside a select_for_update
window, so a parallel admin mark-paid call cannot race the reconciler.

Suggested schedule: every 5-15 minutes.
"""

from django.core.management.base import BaseCommand

from core.services import reconcile_processing_payouts


class Command(BaseCommand):
    help = "Reconcile PROCESSING landlord payouts against the provider."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of payouts to check in this run.",
        )

    def handle(self, *args, **options):
        stats = reconcile_processing_payouts(limit=options.get("limit"))
        message = (
            "Payout reconciliation complete. "
            f"Checked: {stats['checked']}. "
            f"Paid: {stats['paid']}. "
            f"Reversed: {stats['reversed']}. "
            f"Still processing: {stats['left_processing']}. "
            f"Provider errors: {stats['errored']}."
        )
        self.stdout.write(self.style.SUCCESS(message))
