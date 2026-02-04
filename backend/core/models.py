from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class Profile(models.Model):
    ROLE_CHOICES = [
        ("landlord", "Landlord"),
        ("tenant", "Tenant"),
        ("manager", "Manager"),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="tenant")

    def __str__(self):
        return f"{self.user.username} ({self.role})"


# 🧍‍♂️ Manager model — manages properties on behalf of landlords
class Manager(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="manager_profile")
    landlord = models.ForeignKey(User, on_delete=models.CASCADE, related_name="landlord_managers")

    def __str__(self):
        return f"{self.user.username} (Manager for {self.landlord.username})"


# 🏠 Property model
class Property(models.Model):
    title = models.CharField(max_length=100)
    address = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    landlord = models.ForeignKey(User, on_delete=models.CASCADE, related_name="properties")
    manager = models.ForeignKey(Manager, on_delete=models.SET_NULL, null=True, blank=True, related_name="managed_properties")

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # if no manager assigned, landlord manages it themselves
        if not self.manager:
            existing_manager = Manager.objects.filter(user=self.landlord).first()
            if existing_manager:
                self.manager = existing_manager
        super().save(*args, **kwargs)


# 👨‍💼 Tenant model
class Tenant(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="tenant_profile")
    phone = models.CharField(max_length=20, blank=True, null=True)
    national_id = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return self.user.username


# 📜 Lease model
class Lease(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="leases")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="leases")
    rent_amount = models.DecimalField(max_digits=10, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    agreement = models.FileField(upload_to="agreements/", blank=True, null=True)

    def __str__(self):
        return f"Lease for {self.tenant.user.username} at {self.property.title}"


# 💸 Payment model
class Payment(models.Model):
    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=20, default="Pending")
    reference = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"Payment {self.amount} for {self.lease}"


# 🧰 Maintenance model
class Maintenance(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="maintenance_requests")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="maintenance_requests")
    issue = models.TextField()
    status = models.CharField(max_length=20, default="Pending")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Issue: {self.issue[:20]} ({self.status})"


class Document(models.Model):
    DOC_TYPES = [
        ("lease", "Lease"),
        ("receipt", "Receipt"),
        ("other", "Other"),
    ]
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="documents")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="documents")
    lease = models.ForeignKey(Lease, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents")
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents")
    doc_type = models.CharField(max_length=20, choices=DOC_TYPES, default="other")
    file = models.FileField(upload_to="documents/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.doc_type} for {self.property.title}"


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.user.username})"


# 🔄 Auto-create Manager for landlord when needed
@receiver(post_save, sender=User)
def create_manager_for_landlord(sender, instance, created, **kwargs):
    if created:
        profile, _ = Profile.objects.get_or_create(user=instance)
        if instance.is_staff:  # mark landlords as staff users
            profile.role = "landlord"
            profile.save(update_fields=["role"])
            Manager.objects.get_or_create(user=instance, landlord=instance)
        else:
            Tenant.objects.get_or_create(user=instance)
