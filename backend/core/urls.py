from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"properties", views.PropertyViewSet, basename="properties")
router.register(r"units", views.UnitViewSet, basename="units")
router.register(r"leases", views.LeaseViewSet, basename="leases")
router.register(r"invites", views.InviteViewSet, basename="invites")
router.register(r"payments", views.PaymentViewSet, basename="payments")
router.register(r"maintenance", views.MaintenanceViewSet, basename="maintenance")
router.register(r"notifications", views.NotificationViewSet, basename="notifications")

urlpatterns = [
    path("auth/me/", views.get_me, name="get_me"),
    path("dashboard/summary/", views.dashboard_summary, name="dashboard-summary"),
    path("payments/stk/initiate/", views.STKInitiateView.as_view(), name="stk-initiate"),
    path("payments/stk/callback/", views.STKCallbackView.as_view(), name="stk-callback"),
    path("", include(router.urls)),
]
