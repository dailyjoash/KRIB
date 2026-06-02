import React, { useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import AcceptInvite from "./components/AcceptInvite";
import AcceptTenantInvite from "./components/AcceptTenantInvite";
import Dashboard from "./components/Dashboard";
import DocumentsCenter from "./components/DocumentsCenter";
import ForgotPassword from "./components/ForgotPassword";
import InviteManager from "./components/InviteManager";
import InviteResolver from "./components/InviteResolver";
import InvitesNew from "./components/InvitesNew";
import LandlordInvites from "./components/LandlordInvites";
import Layout from "./components/Layout";
import LeasesNew from "./components/LeasesNew";
import LandlordFollowUp from "./components/LandlordFollowUp";
import LandlordPayments from "./components/LandlordPayments";
import LandlordReceipts from "./components/LandlordReceipts";
import LandlordReports from "./components/LandlordReports";
import LandlordRevenue from "./components/LandlordRevenue";
import LandlordSetup from "./components/LandlordSetup";
import LandlordSignup from "./components/LandlordSignup";
import Login from "./components/Login";
import ManagerDashboard from "./components/ManagerDashboard";
import ManagerAction from "./components/ManagerAction";
import ManagerOverview from "./components/ManagerOverview";
import ManagerPayments from "./components/ManagerPayments";
import ManagerReview from "./components/ManagerReview";
import NotificationsCenter from "./components/NotificationsCenter";
import Profile from "./components/Profile";
import ProfileContact from "./components/ProfileContact";
import ProtectedRoute from "./components/ProtectedRoute";
import Register from "./components/Register";
import ResetPassword from "./components/ResetPassword";
import AddProperty from "./components/AddProperty";
import TenantDashboard from "./components/TenantDashboard";
import TenantFinance from "./components/TenantFinance";
import TenantLease from "./components/TenantLease";
import TenantMaintenance from "./components/TenantMaintenance";
import TenantPayRent from "./components/TenantPayRent";
import UnitsNew from "./components/UnitsNew";

const ProtectedPage = ({ allowedRoles, title, subtitle, children }) => (
  <ProtectedRoute allowedRoles={allowedRoles}>
    <Layout title={title} subtitle={subtitle}>
      {children}
    </Layout>
  </ProtectedRoute>
);

function ScrollToTop() {
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [pathname]);

  return null;
}

export default function App() {
  return (
    <>
      <ScrollToTop />
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password/:uid/:token" element={<ResetPassword />} />
        <Route path="/invite/:token" element={<InviteResolver />} />
        <Route path="/invite/manager/:token" element={<AcceptInvite />} />
        <Route path="/invite/tenant/:token" element={<AcceptTenantInvite />} />
        <Route path="/signup-landlord" element={<LandlordSignup />} />
        <Route
          path="/documents"
          element={(
            <ProtectedPage allowedRoles={["landlord", "manager", "tenant"]} title="Documents" subtitle="Access lease and receipt records">
              <DocumentsCenter />
            </ProtectedPage>
          )}
        />
        <Route
          path="/notifications"
          element={(
            <ProtectedPage allowedRoles={["landlord", "manager", "tenant"]} title="Notifications" subtitle="Send updates and review activity">
              <NotificationsCenter />
            </ProtectedPage>
          )}
        />

        <Route
          path="/dashboard"
          element={(
            <ProtectedPage allowedRoles={["landlord"]} title={null} subtitle={null}>
              <Dashboard />
            </ProtectedPage>
          )}
        />
        <Route
          path="/manager"
          element={(
            <ProtectedPage allowedRoles={["manager"]} title={null} subtitle={null}>
              <ManagerDashboard />
            </ProtectedPage>
          )}
        />
        <Route
          path="/manager/overview"
          element={(
            <ProtectedPage allowedRoles={["manager"]} title="Overview" subtitle="Manager view">
              <ManagerOverview />
            </ProtectedPage>
          )}
        />
        <Route
          path="/manager/review"
          element={(
            <ProtectedPage allowedRoles={["manager"]} title="Review" subtitle="Manager view">
              <ManagerReview />
            </ProtectedPage>
          )}
        />
        <Route
          path="/manager/action"
          element={(
            <ProtectedPage allowedRoles={["manager"]} title="Action" subtitle="Manager view">
              <ManagerAction />
            </ProtectedPage>
          )}
        />
        <Route
          path="/manager/payments"
          element={(
            <ProtectedPage allowedRoles={["manager"]} title={null} subtitle={null}>
              <ManagerPayments />
            </ProtectedPage>
          )}
        />
        <Route
          path="/tenant"
          element={(
            <ProtectedPage allowedRoles={["tenant"]} title={null} subtitle={null}>
              <TenantDashboard />
            </ProtectedPage>
          )}
        />
        <Route path="/tenant/home" element={<Navigate to="/tenant" replace />} />

        <Route
          path="/tenant/lease"
          element={(
            <ProtectedPage allowedRoles={["tenant"]} title="Current Lease" subtitle="Tenant view">
              <TenantLease />
            </ProtectedPage>
          )}
        />
        <Route
          path="/tenant/finance"
          element={(
            <ProtectedPage allowedRoles={["tenant"]} title="Financials" subtitle="Tenant view">
              <TenantFinance />
            </ProtectedPage>
          )}
        />
        <Route
          path="/tenant/pay"
          element={(
            <ProtectedPage allowedRoles={["tenant"]} title="Pay Rent" subtitle="Tenant view">
              <TenantPayRent />
            </ProtectedPage>
          )}
        />
        <Route
          path="/tenant/wallet"
          element={<Navigate to="/tenant/finance?tab=wallet" replace />}
        />
        <Route
          path="/tenant/financials"
          element={<Navigate to="/tenant/finance?tab=wallet" replace />}
        />
        <Route
          path="/tenant/payments"
          element={<Navigate to="/tenant/finance?tab=payments" replace />}
        />
        <Route
          path="/tenant/maintenance"
          element={(
            <ProtectedPage allowedRoles={["tenant"]} title="Maintenance" subtitle="Tenant view">
              <TenantMaintenance />
            </ProtectedPage>
          )}
        />
        <Route path="/tenant/notices" element={<Navigate to="/notifications" replace />} />
        <Route path="/tenant/notifications" element={<Navigate to="/notifications" replace />} />
        <Route path="/tenant/documents" element={<Navigate to="/documents" replace />} />
        <Route path="/tenant/profile" element={<Navigate to="/profile" replace />} />
        <Route path="/tenant/community" element={<Navigate to="/notifications" replace />} />
        <Route
          path="/manager-dashboard"
          element={(
            <ProtectedPage allowedRoles={["manager"]} title={null} subtitle={null}>
              <ManagerDashboard />
            </ProtectedPage>
          )}
        />
        <Route path="/manager/home" element={<Navigate to="/manager" replace />} />
        <Route path="/manager/invites" element={<Navigate to="/invites/new" replace />} />
        <Route path="/manager/leases" element={<Navigate to="/leases/new" replace />} />
        <Route path="/manager/notifications" element={<Navigate to="/notifications" replace />} />
        <Route path="/manager/documents" element={<Navigate to="/documents" replace />} />
        <Route path="/manager/profile" element={<Navigate to="/profile" replace />} />
        <Route
          path="/tenant-dashboard"
          element={(
            <ProtectedPage allowedRoles={["tenant"]} title={null} subtitle={null}>
              <TenantDashboard />
            </ProtectedPage>
          )}
        />

        <Route
          path="/landlord/payments"
          element={(
            <ProtectedPage allowedRoles={["landlord"]} title={null} subtitle={null}>
              <LandlordPayments />
            </ProtectedPage>
          )}
        />
        <Route path="/landlord" element={<Navigate to="/dashboard" replace />} />
        <Route path="/landlord/home" element={<Navigate to="/dashboard" replace />} />
        <Route path="/landlord/properties" element={<Navigate to="/landlord/setup" replace />} />
        <Route path="/landlord/leases" element={<Navigate to="/leases/new" replace />} />
        <Route path="/landlord/notifications" element={<Navigate to="/notifications" replace />} />
        <Route path="/landlord/documents" element={<Navigate to="/documents" replace />} />
        <Route path="/landlord/profile" element={<Navigate to="/profile" replace />} />
        <Route
          path="/landlord/reports"
          element={(
            <ProtectedPage allowedRoles={["landlord"]} title={null} subtitle={null}>
              <LandlordReports />
            </ProtectedPage>
          )}
        />
        <Route
          path="/landlord/revenue"
          element={(
            <ProtectedPage allowedRoles={["landlord"]} title="Revenue" subtitle="Collected and net landlord earnings">
              <LandlordRevenue />
            </ProtectedPage>
          )}
        />
        <Route
          path="/landlord/receipts"
          element={(
            <ProtectedPage allowedRoles={["landlord"]} title="Receipts" subtitle="Successful rent collections">
              <LandlordReceipts />
            </ProtectedPage>
          )}
        />
        <Route
          path="/landlord/follow-up"
          element={(
            <ProtectedPage allowedRoles={["landlord"]} title="Follow-up" subtitle="Unpaid and partial rent reminders">
              <LandlordFollowUp />
            </ProtectedPage>
          )}
        />

        <Route
          path="/landlord/setup"
          element={(
            <ProtectedPage allowedRoles={["landlord"]} title="Properties" subtitle="Create properties, units, and assignments">
              <LandlordSetup />
            </ProtectedPage>
          )}
        />
        <Route
          path="/setup"
          element={(
            <ProtectedPage allowedRoles={["landlord"]} title="Properties" subtitle="Create properties, units, and assignments">
              <LandlordSetup />
            </ProtectedPage>
          )}
        />
        <Route
          path="/landlord/invites"
          element={(
            <ProtectedPage allowedRoles={["landlord"]} title="Invite Manager" subtitle="Send manager and tenant onboarding links">
              <LandlordInvites />
            </ProtectedPage>
          )}
        />
        <Route
          path="/properties/new"
          element={(
            <ProtectedPage allowedRoles={["landlord"]} title="Properties" subtitle="Create and manage your portfolio">
              <AddProperty />
            </ProtectedPage>
          )}
        />
        <Route
          path="/units/new"
          element={(
            <ProtectedPage allowedRoles={["landlord"]} title="Units" subtitle="Manage available units">
              <UnitsNew />
            </ProtectedPage>
          )}
        />
        <Route
          path="/invites/new"
          element={(
            <ProtectedPage allowedRoles={["landlord", "manager"]} title="Invites" subtitle="Invite and onboard tenants">
              <InvitesNew />
            </ProtectedPage>
          )}
        />
        <Route
          path="/managers/invite"
          element={(
            <ProtectedPage allowedRoles={["landlord"]} title="Invite Manager" subtitle="Assign management access">
              <InviteManager />
            </ProtectedPage>
          )}
        />
        <Route
          path="/leases/new"
          element={(
            <ProtectedPage allowedRoles={["landlord", "manager"]} title="Leases" subtitle="Create and track leases">
              <LeasesNew />
            </ProtectedPage>
          )}
        />
        <Route
          path="/maintenance/new"
          element={<Navigate to="/tenant/maintenance" replace />}
        />
        <Route
          path="/profile"
          element={(
            <ProtectedPage allowedRoles={["landlord", "manager", "tenant"]} title="Profile" subtitle="Manage your account settings">
              <Profile />
            </ProtectedPage>
          )}
        />
        <Route
          path="/profile/contact"
          element={(
            <ProtectedPage allowedRoles={["landlord", "manager", "tenant"]} title="Contact Details" subtitle="Update your phone number and email">
              <ProfileContact />
            </ProtectedPage>
          )}
        />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </>
  );
}
