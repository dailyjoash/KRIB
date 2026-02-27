from django.urls import include, path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"properties", views.PropertyViewSet, basename="properties")
router.register(r"units", views.UnitViewSet, basename="units")
router.register(r"leases", views.LeaseViewSet, basename="leases")
router.register(r"invites", views.InviteViewSet, basename="invites")
router.register(r"tenants", views.TenantViewSet, basename="tenants")
router.register(r"payments", views.PaymentViewSet, basename="payments")
router.register(r"maintenance", views.MaintenanceViewSet,
                basename="maintenance")
router.register(r"notifications", views.NotificationViewSet,
                basename="notifications")
router.register(r"users", views.UserViewSet, basename="users")

urlpatterns = [
    path("auth/me/", views.get_me, name="get_me"),
    path("me/", views.get_me, name="me"),
    path("auth/change-password/", views.change_password, name="change-password"),
    path("manager-invites/", views.ManagerInviteCreateView.as_view(), name="manager-invite-create"),
    path("manager-invites/accept/", views.ManagerInviteAcceptView.as_view(), name="manager-invite-accept"),
    path("dashboard/summary/", views.dashboard_summary, name="dashboard-summary"),
    path("payments/stk/initiate/",
         views.STKInitiateView.as_view(), name="stk-initiate"),
    path("payments/stk/callback/",
         views.STKCallbackView.as_view(), name="stk-callback"),
    path("", include(router.urls)),
]
