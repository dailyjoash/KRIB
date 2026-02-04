from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'core'

router = DefaultRouter()
router.register(r"properties", views.PropertyViewSet, basename="properties")
router.register(r"leases", views.LeaseViewSet, basename="leases")
router.register(r"payments", views.PaymentViewSet, basename="payments")
router.register(r"maintenance", views.MaintenanceViewSet, basename="maintenance")
router.register(r"documents", views.DocumentViewSet, basename="documents")
router.register(r"notifications", views.NotificationViewSet, basename="notifications")
router.register(r"invites", views.TenantInviteViewSet, basename="invites")

urlpatterns = [
    path('auth/me/', views.get_me, name='get_me'),
    path('leases/my-lease/', views.my_lease, name='my_lease'),
    path('', include(router.urls)),
]
