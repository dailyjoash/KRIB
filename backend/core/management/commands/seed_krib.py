import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO

from django.conf import settings as django_settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from reportlab.pdfgen import canvas

from core.models import (
    Document,
    LandlordBalance,
    LandlordSettings,
    Lease,
    MaintenanceRequest,
    Notification,
    PaymentTransaction,
    Profile,
    Property,
    Tenant,
    Unit,
)
from core.services import save_payment_receipt


DEFAULT_PASSWORD = "KribDemoStrongPass!42"


def month_start(months_ago=0):
    today = timezone.localdate()
    year = today.year
    month = today.month - months_ago
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def month_period(months_ago=0):
    return month_start(months_ago).strftime("%Y-%m")


def build_pdf(name, rows):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    y = 800
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(72, y, name)
    y -= 28
    pdf.setFont("Helvetica", 11)
    for row in rows:
        pdf.drawString(72, y, row)
        y -= 18
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.read()


class Command(BaseCommand):
    help = "Seeds KRIB with landlords, tenants, properties, leases, payments, maintenance requests, and documents."

    @transaction.atomic
    def handle(self, *args, **options):
        # Demo data ships with a known password. Refuse to create it whenever
        # we look like we are in production (DEBUG=0). The override env var
        # gives an operator one explicit way to opt back in for a staging
        # restore, but the default protects against an accidental boot-time
        # seed in prod.
        if not django_settings.DEBUG and os.getenv("KRIB_ALLOW_PROD_SEED", "0") != "1":
            raise CommandError(
                "seed_krib refuses to run with DJANGO_DEBUG=0. "
                "Set KRIB_ALLOW_PROD_SEED=1 only if you really intend to seed demo data in production."
            )

        landlords = [
            self.ensure_user(
                username="landlord_alpha",
                email="landlord1@krib.co.ke",
                full_name="Amina Mwangi",
                phone="+254700111111",
                role=Profile.ROLE_LANDLORD,
            ),
            self.ensure_user(
                username="landlord_beta",
                email="landlord2@krib.co.ke",
                full_name="David Kiptoo",
                phone="+254700222222",
                role=Profile.ROLE_LANDLORD,
            ),
        ]

        tenants = [
            self.ensure_user(
                username="tenant_joy",
                email="tenant1@krib.co.ke",
                full_name="Joy Wanjiru",
                phone="+254711000001",
                role=Profile.ROLE_TENANT,
            ),
            self.ensure_user(
                username="tenant_brian",
                email="tenant2@krib.co.ke",
                full_name="Brian Otieno",
                phone="+254711000002",
                role=Profile.ROLE_TENANT,
            ),
            self.ensure_user(
                username="tenant_faith",
                email="tenant3@krib.co.ke",
                full_name="Faith Njeri",
                phone="+254711000003",
                role=Profile.ROLE_TENANT,
            ),
            self.ensure_user(
                username="tenant_mark",
                email="tenant4@krib.co.ke",
                full_name="Mark Cheruiyot",
                phone="+254711000004",
                role=Profile.ROLE_TENANT,
            ),
        ]

        property_specs = [
            (landlords[0], "KRIB Heights", "Westlands, Nairobi", "A modern apartment block near Waiyaki Way.", "A1", Decimal("18500.00")),
            (landlords[0], "KRIB Residency", "Kilimani, Nairobi", "Quiet residential units close to Yaya Centre.", "B2", Decimal("22000.00")),
            (landlords[1], "KRIB Gardens", "Ruiru, Kiambu", "Secure compound with generous parking and water storage.", "C3", Decimal("16500.00")),
            (landlords[1], "KRIB Court", "Syokimau, Machakos", "Commuter-friendly rental homes near the SGR terminus.", "D4", Decimal("24000.00")),
        ]

        leases = []
        for index, spec in enumerate(property_specs):
            landlord, property_name, location, description, unit_number, rent_amount = spec
            property_obj, _ = Property.objects.get_or_create(
                landlord=landlord,
                name=property_name,
                defaults={"location": location, "description": description},
            )
            if property_obj.location != location or property_obj.description != description:
                property_obj.location = location
                property_obj.description = description
                property_obj.save(update_fields=["location", "description"])

            unit, _ = Unit.objects.get_or_create(
                property=property_obj,
                unit_number=unit_number,
                defaults={
                    "unit_type": Unit.TYPE_1BR,
                    "rent_amount": rent_amount,
                    "deposit": rent_amount,
                    "status": Unit.STATUS_OCCUPIED,
                },
            )
            if unit.rent_amount != rent_amount or unit.deposit != rent_amount:
                unit.rent_amount = rent_amount
                unit.deposit = rent_amount
                unit.save(update_fields=["rent_amount", "deposit"])

            lease, _ = Lease.objects.get_or_create(
                unit=unit,
                tenant=tenants[index],
                defaults={
                    "rent_amount": rent_amount,
                    "start_date": month_start(5),
                    "due_day": 5,
                    "status": Lease.STATUS_ACTIVE,
                },
            )
            if lease.status != Lease.STATUS_ACTIVE:
                lease.status = Lease.STATUS_ACTIVE
                lease.save(update_fields=["status"])
            if not lease.end_date:
                lease.end_date = date(month_start().year + 1, month_start().month, 1) - timedelta(days=1)
                lease.save(update_fields=["end_date"])
            leases.append(lease)

        payment_specs = [
            (leases[0], 1, PaymentTransaction.METHOD_MPESA, PaymentTransaction.STATUS_SUCCESS),
            (leases[0], 0, PaymentTransaction.METHOD_PAYPAL, PaymentTransaction.STATUS_SUCCESS),
            (leases[1], 1, PaymentTransaction.METHOD_CARD, PaymentTransaction.STATUS_SUCCESS),
            (leases[1], 0, PaymentTransaction.METHOD_MPESA, PaymentTransaction.STATUS_SUCCESS),
            (leases[2], 1, PaymentTransaction.METHOD_PAYPAL, PaymentTransaction.STATUS_SUCCESS),
            (leases[2], 0, PaymentTransaction.METHOD_CARD, PaymentTransaction.STATUS_FAILED),
            (leases[3], 1, PaymentTransaction.METHOD_MPESA, PaymentTransaction.STATUS_SUCCESS),
            (leases[3], 2, PaymentTransaction.METHOD_CARD, PaymentTransaction.STATUS_SUCCESS),
        ]
        for index, (lease, months_ago, method, payment_status) in enumerate(payment_specs, start=1):
            billing_period = month_start(months_ago)
            period = month_period(months_ago)
            transaction_code = f"KRIB-TXN-{index:03d}"
            payment, created = PaymentTransaction.objects.get_or_create(
                transaction_code=transaction_code,
                defaults={
                    "lease": lease,
                    "tenant": lease.tenant,
                    "period": period,
                    "billing_period": billing_period,
                    "phone_number": lease.tenant.profile.phone_number or "254700000000",
                    "amount": lease.rent_amount,
                    "payment_method": method,
                    "checkout_request_id": f"CHK-{index:03d}",
                    "status": payment_status,
                    "result_desc": payment_status.upper(),
                    "transaction_date": timezone.make_aware(datetime.combine(billing_period + timedelta(days=4), datetime.min.time())),
                    "allocation_done": payment_status == PaymentTransaction.STATUS_SUCCESS,
                },
            )
            if not created:
                changed = False
                for field, value in {
                    "lease": lease,
                    "tenant": lease.tenant,
                    "period": period,
                    "billing_period": billing_period,
                    "phone_number": lease.tenant.profile.phone_number or "254700000000",
                    "amount": lease.rent_amount,
                    "payment_method": method,
                    "status": payment_status,
                }.items():
                    if getattr(payment, field) != value:
                        setattr(payment, field, value)
                        changed = True
                if changed:
                    payment.save()
            if payment.status == PaymentTransaction.STATUS_SUCCESS and not payment.receipt_file:
                save_payment_receipt(payment)

        maintenance_specs = [
            (leases[0], "Leaking kitchen tap", MaintenanceRequest.URGENCY_LOW, MaintenanceRequest.STATUS_OPEN),
            (leases[1], "Power outage in bedroom socket", MaintenanceRequest.URGENCY_HIGH, MaintenanceRequest.STATUS_IN_PROGRESS),
            (leases[2], "Broken bathroom lock", MaintenanceRequest.URGENCY_MEDIUM, MaintenanceRequest.STATUS_RESOLVED),
        ]
        for lease, issue, urgency, status_value in maintenance_specs:
            MaintenanceRequest.objects.get_or_create(
                lease=lease,
                tenant=lease.tenant,
                issue=issue,
                defaults={"urgency": urgency, "status": status_value},
            )

        lease_doc = Document.objects.filter(property=leases[0].unit.property, document_type=Document.TYPE_LEASE).first()
        if not lease_doc:
            lease_doc = Document(
                property=leases[0].unit.property,
                lease=leases[0],
                uploaded_by=landlords[0],
                document_type=Document.TYPE_LEASE,
            )
            lease_doc.file_path.save(
                "krib-sample-lease.pdf",
                ContentFile(
                    build_pdf(
                        "KRIB Lease Agreement",
                        [
                            f"Tenant: {leases[0].tenant.first_name}",
                            f"Property: {leases[0].unit.property.name}",
                            f"Unit: {leases[0].unit.unit_number}",
                            f"Rent: KES {leases[0].rent_amount}",
                        ],
                    )
                ),
                save=True,
            )

        receipt_payment = PaymentTransaction.objects.filter(status=PaymentTransaction.STATUS_SUCCESS).order_by("id").first()
        if receipt_payment:
            if not receipt_payment.receipt_file:
                save_payment_receipt(receipt_payment)
            receipt_doc = Document.objects.filter(property=receipt_payment.lease.unit.property, document_type=Document.TYPE_RECEIPT).first()
            if not receipt_doc:
                receipt_doc = Document(
                    property=receipt_payment.lease.unit.property,
                    lease=receipt_payment.lease,
                    uploaded_by=receipt_payment.tenant,
                    document_type=Document.TYPE_RECEIPT,
                )
                receipt_doc.file_path.save(
                    "krib-sample-receipt.pdf",
                    ContentFile(
                        build_pdf(
                            "KRIB Receipt Archive",
                            [
                                f"Tenant: {receipt_payment.tenant.first_name}",
                                f"Property: {receipt_payment.lease.unit.property.name}",
                                f"Method: {receipt_payment.payment_method.upper()}",
                                f"Reference: {receipt_payment.transaction_code}",
                            ],
                        )
                    ),
                    save=True,
                )

        for lease in leases:
            Notification.objects.get_or_create(
                user=lease.tenant,
                type=Notification.TYPE_GENERIC,
                lease=lease,
                period=month_period(),
                defaults={
                    "title": "Welcome to KRIB",
                    "message": f"Your lease for {lease.unit.property.name} / {lease.unit.unit_number} is active.",
                },
            )

        self.stdout.write(self.style.SUCCESS("KRIB seed data is ready."))
        self.stdout.write(f"Demo password for seeded users: {DEFAULT_PASSWORD}")

    def ensure_user(self, username, email, full_name, phone, role):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "first_name": full_name},
        )
        if created:
            user.set_password(DEFAULT_PASSWORD)
            user.save(update_fields=["password"])
        else:
            changed = False
            if user.email != email:
                user.email = email
                changed = True
            if user.first_name != full_name:
                user.first_name = full_name
                changed = True
            if changed:
                user.save(update_fields=["email", "first_name"])

        profile, _ = Profile.objects.get_or_create(user=user)
        updates = []
        if profile.role != role:
            profile.role = role
            updates.append("role")
        if profile.phone_number != phone:
            profile.phone_number = phone
            updates.append("phone_number")
        if updates:
            profile.save(update_fields=updates)

        tenant_profile, _ = Tenant.objects.get_or_create(user=user)
        if tenant_profile.phone != phone:
            tenant_profile.phone = phone
            tenant_profile.save(update_fields=["phone"])

        if role == Profile.ROLE_LANDLORD:
            LandlordSettings.objects.get_or_create(user=user, defaults={"business_name": f"{full_name} Properties"})
            LandlordBalance.objects.get_or_create(landlord=user)

        return user
