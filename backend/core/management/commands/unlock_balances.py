import logging
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import LandlordBalance, LedgerTransaction, Profile

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Unlocks landlord and tenant balances whose hold period has expired."

    def handle(self, *args, **options):
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
                if self._unlock_transaction(ledger_id):
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

    def _unlock_transaction(self, ledger_id):
        # Each ledger row is processed in its own atomic block so a single
        # failure rolls back only that row and does not stop other unlocks.
        with transaction.atomic():
            row = (
                LedgerTransaction.objects.select_for_update()
                .select_related("user")
                .get(pk=ledger_id)
            )
            now = timezone.now()

            if row.status != LedgerTransaction.STATUS_LOCKED:
                return False
            if row.available_at is None or row.available_at > now:
                return False

            if row.kind == LedgerTransaction.KIND_LANDLORD_CREDIT_RENT:
                return self._unlock_landlord_credit(row)
            if row.kind == LedgerTransaction.KIND_WALLET_CREDIT:
                return self._unlock_wallet_credit(row)

            logger.info(
                "Skipping locked ledger transaction %s with unsupported kind %s",
                row.pk,
                row.kind,
            )
            return False

    def _unlock_landlord_credit(self, row):
        balance, _ = LandlordBalance.objects.get_or_create(landlord=row.user)
        balance = LandlordBalance.objects.select_for_update().get(pk=balance.pk)
        balance.locked_balance = max(
            balance.locked_balance - row.amount,
            Decimal("0.00"),
        )
        balance.available_balance += row.amount
        balance.save(update_fields=["locked_balance", "available_balance", "updated_at"])

        row.status = LedgerTransaction.STATUS_AVAILABLE
        row.save(update_fields=["status"])
        return True

    def _unlock_wallet_credit(self, row):
        profile, _ = Profile.objects.get_or_create(user=row.user)
        profile = Profile.objects.select_for_update().get(pk=profile.pk)
        profile.wallet_locked = max(
            profile.wallet_locked - row.amount,
            Decimal("0.00"),
        )
        profile.wallet_available += row.amount
        profile.save(update_fields=["wallet_locked", "wallet_available", "updated_at"])

        row.status = LedgerTransaction.STATUS_AVAILABLE
        row.save(update_fields=["status"])
        return True
