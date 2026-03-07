import React from "react";
import { Route, Routes } from "react-router-dom";
import AcceptInvite from "./components/AcceptInvite";
import Dashboard from "./components/Dashboard";
import Greeting from "./components/Greeting";
import InviteManager from "./components/InviteManager";
import InvitesNew from "./components/InvitesNew";
import Layout from "./components/Layout";
import LeasesNew from "./components/LeasesNew";
import Login from "./components/Login";
import MaintenanceNew from "./components/MaintenanceNew";
import ManagerDashboard from "./components/ManagerDashboard";
import Profile from "./components/Profile";
import ProtectedRoute from "./components/ProtectedRoute";
import AddProperty from "./components/AddProperty";
import TenantDashboard from "./components/TenantDashboard";
import TenantLease from "./components/TenantLease";
import TenantMaintenance from "./components/TenantMaintenance";
import TenantPayments from "./components/TenantPayments";
import TenantPayRent from "./components/TenantPayRent";
import TenantWallet from "./components/TenantWallet";
import UnitsNew from "./components/UnitsNew";

const ProtectedPage = ({ allowedRoles, title, subtitle, children }) => (
  <ProtectedRoute allowedRoles={allowedRoles}>
    <Layout title={title} subtitle={subtitle}>
      {children}
    </Layout>
  </ProtectedRoute>
);

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Login />} />
      <Route path="/login" element={<Login />} />
      <Route path="/invite/:token" element={<AcceptInvite />} />

      <Route
        path="/dashboard"
        element={(
          <ProtectedPage allowedRoles={["landlord"]} title={<Greeting />} subtitle="Landlord view">
            <Dashboard />
          </ProtectedPage>
        )}
      />
      <Route
        path="/manager"
        element={(
          <ProtectedPage allowedRoles={["manager"]} title={<Greeting />} subtitle="Manager view">
            <ManagerDashboard />
          </ProtectedPage>
        )}
      />
      <Route
        path="/tenant"
        element={(
          <ProtectedPage allowedRoles={["tenant"]} title={<Greeting />} subtitle="Tenant view">
            <TenantDashboard />
          </ProtectedPage>
        )}
      />

      <Route
        path="/tenant/lease"
        element={(
          <ProtectedPage allowedRoles={["tenant"]} title="Current Lease" subtitle="Tenant view">
            <TenantLease />
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
        element={(
          <ProtectedPage allowedRoles={["tenant"]} title="Wallet" subtitle="Tenant view">
            <TenantWallet />
          </ProtectedPage>
        )}
      />
      <Route
        path="/tenant/payments"
        element={(
          <ProtectedPage allowedRoles={["tenant"]} title="Payments" subtitle="Tenant view">
            <TenantPayments />
          </ProtectedPage>
        )}
      />
      <Route
        path="/tenant/maintenance"
        element={(
          <ProtectedPage allowedRoles={["tenant"]} title="Maintenance" subtitle="Tenant view">
            <TenantMaintenance />
          </ProtectedPage>
        )}
      />

      <Route
        path="/manager-dashboard"
        element={(
          <ProtectedPage allowedRoles={["manager"]} title={<Greeting />} subtitle="Manager view">
            <ManagerDashboard />
          </ProtectedPage>
        )}
      />
      <Route
        path="/tenant-dashboard"
        element={(
          <ProtectedPage allowedRoles={["tenant"]} title={<Greeting />} subtitle="Tenant view">
            <TenantDashboard />
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
        element={(
          <ProtectedPage allowedRoles={["tenant"]} title="Maintenance" subtitle="Report a new issue">
            <MaintenanceNew />
          </ProtectedPage>
        )}
      />
      <Route
        path="/profile"
        element={(
          <ProtectedPage allowedRoles={["landlord", "manager", "tenant"]} title="Profile" subtitle="Manage your account settings">
            <Profile />
          </ProtectedPage>
        )}
      />
    </Routes>
  );
}
