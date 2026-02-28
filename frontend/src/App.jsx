import React from "react";
import { Routes, Route } from "react-router-dom";

import Login from "./components/Login";
import Dashboard from "./components/Dashboard";
import ManagerDashboard from "./components/ManagerDashboard";
import TenantDashboard from "./components/TenantDashboard";
import AddProperty from "./components/AddProperty";
import UnitsNew from "./components/UnitsNew";
import InvitesNew from "./components/InvitesNew";
import LeasesNew from "./components/LeasesNew";
import MaintenanceNew from "./components/MaintenanceNew";
import InviteManager from "./components/InviteManager";
import AcceptInvite from "./components/AcceptInvite";
import Profile from "./components/Profile";
import ProtectedRoute from "./components/ProtectedRoute";
import Layout from "./components/Layout";
import Greeting from "./components/Greeting";

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
          <ProtectedPage
            allowedRoles={["landlord"]}
            title={<Greeting />}
            subtitle="Landlord view"
          >
            <Dashboard />
          </ProtectedPage>
        )}
      />
      <Route
        path="/manager"
        element={(
          <ProtectedPage
            allowedRoles={["manager"]}
            title={<Greeting />}
            subtitle="Manager view"
          >
            <ManagerDashboard />
          </ProtectedPage>
        )}
      />
      <Route
        path="/tenant"
        element={(
          <ProtectedPage
            allowedRoles={["tenant"]}
            title={<Greeting />}
            subtitle="Tenant view"
          >
            <TenantDashboard />
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
