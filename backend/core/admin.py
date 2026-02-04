
from django.contrib import admin
from .models import Property, Tenant, Lease, Payment, Maintenance, Manager, Profile, Document, Notification

admin.site.register(Property)
admin.site.register(Tenant)
admin.site.register(Lease)
admin.site.register(Payment)
admin.site.register(Maintenance)
admin.site.register(Manager)
admin.site.register(Profile)
admin.site.register(Document)
admin.site.register(Notification)
