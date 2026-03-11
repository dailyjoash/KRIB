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
router.register(r"maintenance", views.MaintenanceViewSet, basename="maintenance")
router.register(r"notifications", views.NotificationViewSet, basename="notifications")
router.register(r"users", views.UserViewSet, basename="users")

urlpatterns = [
    path("auth/me/", views.get_me, name="get_me"),
    path("me/", views.get_me, name="me"),
    path("auth/change-password/", views.change_password, name="change-password"),
    path("auth/signup-landlord/", views.signup_landlord, name="signup-landlord"),
    path("manager-invites/", views.ManagerInviteCreateView.as_view(), name="manager-invite-create"),
    path("manager-invites/accept/", views.ManagerInviteAcceptView.as_view(), name="manager-invite-accept"),
    path("dashboard/summary/", views.dashboard_summary, name="dashboard-summary"),
    path("payments/stk/initiate/", views.STKInitiateView.as_view(), name="stk-initiate"),
    path("payments/stk/callback/", views.STKCallbackView.as_view(), name="stk-callback"),
    path("wallet/", views.WalletView.as_view(), name="wallet"),
    path("wallet/withdraw/", views.WalletWithdrawView.as_view(), name="wallet-withdraw"),
    path("wallet/withdrawals/<int:pk>/mark-paid/", views.WalletWithdrawalMarkPaidView.as_view(), name="wallet-withdraw-mark-paid"),
    path("landlord/revenue/", views.landlord_revenue, name="landlord-revenue"),
    path("landlord/receipts/", views.landlord_receipts, name="landlord-receipts"),
    path("landlord/followups/", views.landlord_followups, name="landlord-followups"),
    path("landlord/payouts/", views.LandlordPayoutsView.as_view(), name="landlord-payouts"),
    path("landlord/payouts/request/", views.LandlordPayoutRequestView.as_view(), name="landlord-payout-request"),
    path("landlord/payouts/<int:pk>/mark-paid/", views.LandlordPayoutMarkPaidView.as_view(), name="landlord-payout-mark-paid"),
    path("", include(router.urls)),
]
