import os
import time

from django.core.management import BaseCommand, call_command
from django.utils import timezone


class Command(BaseCommand):
    help = "Runs lightweight recurring KRIB background jobs on a fixed interval."

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "3600")),
            help="Seconds to wait between job runs. Defaults to SCHEDULER_INTERVAL_SECONDS or 3600.",
        )

    def handle(self, *args, **options):
        interval = max(options["interval"], 60)
        self.stdout.write(self.style.SUCCESS(f"Starting periodic task runner with {interval}s interval"))

        while True:
            started_at = timezone.now().isoformat()
            self.stdout.write(f"[{started_at}] Running scheduled jobs")
            call_command("check_arrears")
            self.stdout.write(self.style.SUCCESS("Scheduled jobs completed"))
            time.sleep(interval)
