
from django.contrib import admin
from .models import Property, Tenant, Lease, Payment, Maintenance

admin.site.register(Property)
admin.site.register(Tenant)
admin.site.register(Lease)
admin.site.register(Payment)
admin.site.register(Maintenance)
