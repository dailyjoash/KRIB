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
    path("health/", views.health_check, name="health-check"),
    path("auth/register/", views.register, name="auth-register"),
    path("auth/login/", views.login, name="auth-login"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", views.get_me, name="get_me"),
    path("me/", views.get_me, name="me"),
    path("auth/change-password/", views.change_password, name="change-password"),
    path("auth/password-reset/", views.password_reset_request, name="password-reset-request"),
    path("auth/password-reset/confirm/", views.password_reset_confirm, name="password-reset-confirm"),
    path("auth/signup-landlord/", views.signup_landlord, name="signup-landlord"),
    path("manager-invites/", views.ManagerInviteCreateView.as_view(), name="manager-invite-create"),
    path("manager-invites/accept/", views.ManagerInviteAcceptView.as_view(), name="manager-invite-accept"),
    path("dashboard/tenant/", views.tenant_dashboard, name="dashboard-tenant"),
    path("dashboard/landlord/", views.landlord_dashboard, name="dashboard-landlord"),
    path("dashboard/summary/", views.dashboard_summary, name="dashboard-summary"),
    path("payments/mpesa/initiate/", views.STKInitiateView.as_view(), name="payments-mpesa-initiate"),
    path("payments/mpesa/status/<str:checkout_id>/", views.MPesaPaymentStatusView.as_view(), name="payments-mpesa-status"),
    path("payments/mpesa/callback/", views.STKCallbackView.as_view(), name="payments-mpesa-callback"),
    path("mpesa/callback/", views.STKCallbackView.as_view(), name="mpesa-callback"),
    path("payments/stk/initiate/", views.STKInitiateView.as_view(), name="stk-initiate"),
    path("payments/stk/callback/", views.STKCallbackView.as_view(), name="stk-callback"),
    path("payments/direct/instructions/", views.DirectPaymentInstructionsView.as_view(), name="payments-direct-instructions"),
    path("payments/direct/", views.DirectPaymentListSubmitView.as_view(), name="payments-direct-list-submit"),
    path("payments/direct/<int:pk>/attach/", views.DirectPaymentAttachView.as_view(), name="payments-direct-attach"),
    path("payments/direct/<int:pk>/<str:action>/", views.DirectPaymentActionView.as_view(), name="payments-direct-action"),
    path("payments/paypal/create-order/", views.PayPalCreateOrderView.as_view(), name="payments-paypal-create-order"),
    path("payments/paypal/capture/", views.PayPalCaptureView.as_view(), name="payments-paypal-capture"),
    path("payments/stripe/create-intent/", views.StripeCreateIntentView.as_view(), name="payments-stripe-create-intent"),
    path("payments/stripe/webhook/", views.StripeWebhookView.as_view(), name="payments-stripe-webhook"),
    path("payments/arrears/", views.payments_arrears, name="payments-arrears"),
    path("payments/receipt/<int:pk>/", views.PaymentReceiptView.as_view(), name="payments-receipt"),
    path("documents/", views.DocumentListView.as_view(), name="documents-list"),
    path("documents/upload/", views.DocumentUploadView.as_view(), name="documents-upload"),
    path("documents/<int:pk>/download/", views.DocumentDownloadView.as_view(), name="documents-download"),
    path("notifications/read-all/", views.notifications_read_all, name="notifications-read-all"),
    path("wallet/", views.WalletView.as_view(), name="wallet"),
    path("wallet/withdraw/", views.WalletWithdrawView.as_view(), name="wallet-withdraw"),
    path("wallet/withdrawals/<int:pk>/mark-paid/", views.WalletWithdrawalMarkPaidView.as_view(), name="wallet-withdraw-mark-paid"),
    path("landlord/revenue/", views.landlord_revenue, name="landlord-revenue"),
    path("landlord/receipts/", views.landlord_receipts, name="landlord-receipts"),
    path("landlord/followups/", views.landlord_followups, name="landlord-followups"),
    path("landlord/settings/", views.LandlordSettingsView.as_view(), name="landlord-settings"),
    path("landlord/collection-account/", views.LandlordCollectionAccountView.as_view(), name="landlord-collection-account"),
    path("staff/collection-accounts/<int:pk>/verify/", views.LandlordCollectionAccountVerifyView.as_view(), name="staff-collection-account-verify"),
    path("landlord/payouts/", views.LandlordPayoutsView.as_view(), name="landlord-payouts"),
    path("landlord/payouts/request/", views.LandlordPayoutRequestView.as_view(), name="landlord-payout-request"),
    path("landlord/payouts/<int:pk>/mark-paid/", views.LandlordPayoutMarkPaidView.as_view(), name="landlord-payout-mark-paid"),
    path("landlord/payouts/<int:pk>/reverse/", views.LandlordPayoutReverseView.as_view(), name="landlord-payout-reverse"),
    path("staff/custody/landlords/", views.CustodyLandlordListView.as_view(), name="staff-custody-landlords"),
    path("staff/custody/landlords/<int:pk>/", views.CustodyLandlordDetailView.as_view(), name="staff-custody-landlord-detail"),
    path("staff/custody/landlords/<int:pk>/settle/", views.CustodySettleView.as_view(), name="staff-custody-settle"),
    path("staff/custody/landlords/<int:pk>/cutover/", views.CustodyCutoverView.as_view(), name="staff-custody-cutover"),
    path("landlord/subscription/current/", views.LandlordSubscriptionCurrentView.as_view(), name="landlord-subscription-current"),
    path("landlord/subscription/invoices/", views.LandlordSubscriptionListView.as_view(), name="landlord-subscription-invoices"),
    path("landlord/subscription/invoices/<int:pk>/pay/", views.LandlordSubscriptionPayView.as_view(), name="landlord-subscription-pay"),
    path("", include(router.urls)),
]
