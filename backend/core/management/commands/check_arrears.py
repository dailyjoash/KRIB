from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Lease, Notification, compute_lease_rent_status


class Command(BaseCommand):
    help = "Checks active leases for unpaid rent after the arrears threshold and creates notifications."

    def handle(self, *args, **options):
        today = timezone.localdate()
        if today.day <= 5:
            self.stdout.write("Arrears threshold not reached yet.")
            return

        period = today.strftime("%Y-%m")
        active_leases = Lease.objects.filter(status=Lease.STATUS_ACTIVE).select_related("tenant", "unit", "unit__property")
        created = 0

        for lease in active_leases:
            rent = compute_lease_rent_status(lease, period=period, today=today)
            if rent["status"] != "OVERDUE":
                continue

            landlord_notice, landlord_created = Notification.objects.get_or_create(
                user=lease.unit.property.landlord,
                type=Notification.TYPE_OVERDUE,
                lease=lease,
                period=period,
                defaults={
                    "title": "Tenant in arrears",
                    "message": f"{lease.tenant.username} has overdue rent for {lease.unit.property.name} / {lease.unit.unit_number}.",
                },
            )
            created += int(landlord_created)

            manager = lease.unit.property.manager
            if manager:
                _, manager_created = Notification.objects.get_or_create(
                    user=manager,
                    type=Notification.TYPE_OVERDUE,
                    lease=lease,
                    period=period,
                    defaults={
                        "title": landlord_notice.title,
                        "message": landlord_notice.message,
                    },
                )
                created += int(manager_created)

        self.stdout.write(self.style.SUCCESS(f"Arrears check complete. Notifications created: {created}"))
