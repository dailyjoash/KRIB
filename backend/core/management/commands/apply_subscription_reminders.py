from django.core.management.base import BaseCommand

from core.services import apply_subscription_reminders


class Command(BaseCommand):
    help = "Apply KRIB subscription invoice reminders and overdue transitions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report that reminders would run without applying changes.",
        )

    def handle(self, *args, **options):
        if options.get("dry_run"):
            self.stdout.write("Dry run: would apply subscription reminders")
            return

        stats = apply_subscription_reminders()
        self.stdout.write(
            self.style.SUCCESS(
                "Subscription reminders applied. "
                f"grace={stats['grace_reminders']} "
                f"overdue_transitions={stats['overdue_transitions']} "
                f"overdue_reminders={stats['overdue_reminders']}"
            )
        )
