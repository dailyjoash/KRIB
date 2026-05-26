import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import LedgerTransaction
from core.services import _unlock_single_ledger_row

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Unlocks landlord and tenant balances whose hold period has expired."

    def handle(self, *args, **options):
        # Both this cron and the view-side helpers route through the same
        # `_unlock_single_ledger_row` service so they cannot diverge on
        # locking discipline.
        due_ids = list(
            LedgerTransaction.objects.filter(
                status=LedgerTransaction.STATUS_LOCKED,
                available_at__lte=timezone.now(),
            )
            .order_by("available_at", "id")
            .values_list("id", flat=True)
        )

        unlocked = 0
        skipped = 0
        failed = 0

        for ledger_id in due_ids:
            try:
                if _unlock_single_ledger_row(ledger_id):
                    unlocked += 1
                else:
                    skipped += 1
            except Exception:
                failed += 1
                logger.exception("Failed to unlock ledger transaction %s", ledger_id)

        message = (
            f"Balance unlock complete. Unlocked: {unlocked}. "
            f"Skipped: {skipped}. Failed: {failed}."
        )
        logger.info(message)
        self.stdout.write(self.style.SUCCESS(message))
