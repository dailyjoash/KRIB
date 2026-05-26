"""Lightweight in-process scheduler for KRIB recurring background jobs.

This command is the entrypoint used by the production `scheduler` container
(see docker-compose.prod.yml). It loops forever, running a fixed set of
management commands every `--interval` seconds.

Recommended interval: 5–15 minutes for environments that take live payments,
so PROCESSING payouts and SUCCESS-but-not-allocated payments are finalized
within one cron cycle. Default is 3600s for low-traffic dev environments,
overridable via SCHEDULER_INTERVAL_SECONDS.

Each task runs in its own try/except. A single failing task is logged but
does NOT stop the rest of the schedule — getting reconcile_payouts to run
when check_arrears blew up is exactly the failure mode we care about.
"""

import logging
import os
import time

from django.core.management import BaseCommand, call_command
from django.utils import timezone

logger = logging.getLogger(__name__)


# Order matters for clarity but not correctness — each task is independent.
# Tuple of (command_name, kwargs) so future tasks can pass options.
PERIODIC_TASKS = (
    # Tenant-side billing alerts.
    ("check_arrears", {}),
    # Retry ledger allocation for payments that landed in SUCCESS but never
    # got their landlord-credit/wallet-credit ledger rows written (e.g. a
    # crash in `_allocate_success_payment` after the status save committed).
    ("reconcile_payment_allocations", {}),
    # Promote PROCESSING payouts to PAID/REVERSED by asking IntaSend (or any
    # future provider) for an authoritative settlement state.
    ("reconcile_payouts", {}),
)


def _run_one(command_name, command_kwargs, *, stdout_writer=None):
    """Run a single management command and swallow its exception.

    Returns True on success, False on failure. Side effects: structured
    log entry + optional stdout write so the operator sees per-task status
    in the scheduler container's logs.
    """
    started = timezone.now()
    try:
        if stdout_writer:
            stdout_writer(f"[{started.isoformat()}] start task={command_name}")
        logger.info("scheduler.task.start name=%s", command_name)
        call_command(command_name, **command_kwargs)
        logger.info("scheduler.task.success name=%s", command_name)
        if stdout_writer:
            stdout_writer(f"[{timezone.now().isoformat()}] ok task={command_name}")
        return True
    except Exception:
        # Log with traceback for debugging but DO NOT re-raise — the next
        # task must still run. This is the entire reason for the wrapper.
        logger.exception("scheduler.task.failed name=%s", command_name)
        if stdout_writer:
            stdout_writer(
                f"[{timezone.now().isoformat()}] FAILED task={command_name} (see logs)"
            )
        return False


def run_scheduled_tasks(stdout_writer=None):
    """Execute every task in PERIODIC_TASKS exactly once.

    Extracted so the unit tests can call it directly without patching
    time.sleep or wrapping the whole `while True` loop.
    """
    results = {}
    for command_name, command_kwargs in PERIODIC_TASKS:
        results[command_name] = _run_one(
            command_name, command_kwargs, stdout_writer=stdout_writer
        )
    return results


class Command(BaseCommand):
    help = "Runs lightweight recurring KRIB background jobs on a fixed interval."

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "3600")),
            help="Seconds to wait between job runs. Defaults to SCHEDULER_INTERVAL_SECONDS or 3600.",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run the schedule exactly once and exit. Used by ad-hoc operator runs and by tests.",
        )

    def handle(self, *args, **options):
        interval = max(options["interval"], 60)
        once = options.get("once", False)

        self.stdout.write(
            self.style.SUCCESS(
                f"Starting periodic task runner with {interval}s interval"
                + (" (single shot)" if once else "")
            )
        )

        while True:
            run_scheduled_tasks(stdout_writer=self.stdout.write)
            self.stdout.write(self.style.SUCCESS("Scheduled jobs completed"))
            if once:
                return
            time.sleep(interval)
