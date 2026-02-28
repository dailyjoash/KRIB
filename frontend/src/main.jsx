import React, { useContext } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider, AuthContext } from "./context/AuthContext";

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
import NavBar from "./components/NavBar";

import "./styles.css";

const savedTheme = localStorage.getItem("theme") || "dark";
if (savedTheme === "dark") {
  document.documentElement.classList.add("theme-dark");
}

const App = () => {
  const { user } = useContext(AuthContext);

  return (
    <div className="app-shell">
      <NavBar />
      <main className={`app-content ${user ? "with-sidebar" : ""}`}>
        <Routes>
          <Route path="/" element={<Login />} />
          <Route path="/invite/:token" element={<AcceptInvite />} />

          <Route path="/dashboard" element={<ProtectedRoute allowedRoles={["landlord"]}><Dashboard /></ProtectedRoute>} />
          <Route path="/manager" element={<ProtectedRoute allowedRoles={["manager"]}><ManagerDashboard /></ProtectedRoute>} />
          <Route path="/tenant" element={<ProtectedRoute allowedRoles={["tenant"]}><TenantDashboard /></ProtectedRoute>} />
          <Route path="/manager-dashboard" element={<ProtectedRoute allowedRoles={["manager"]}><ManagerDashboard /></ProtectedRoute>} />
          <Route path="/tenant-dashboard" element={<ProtectedRoute allowedRoles={["tenant"]}><TenantDashboard /></ProtectedRoute>} />

          <Route path="/properties/new" element={<ProtectedRoute allowedRoles={["landlord"]}><AddProperty /></ProtectedRoute>} />
          <Route path="/units/new" element={<ProtectedRoute allowedRoles={["landlord"]}><UnitsNew /></ProtectedRoute>} />
          <Route path="/invites/new" element={<ProtectedRoute allowedRoles={["landlord", "manager"]}><InvitesNew /></ProtectedRoute>} />
          <Route path="/managers/invite" element={<ProtectedRoute allowedRoles={["landlord"]}><InviteManager /></ProtectedRoute>} />
          <Route path="/leases/new" element={<ProtectedRoute allowedRoles={["landlord", "manager"]}><LeasesNew /></ProtectedRoute>} />
          <Route path="/maintenance/new" element={<ProtectedRoute allowedRoles={["tenant"]}><MaintenanceNew /></ProtectedRoute>} />
          <Route path="/profile" element={<ProtectedRoute allowedRoles={["landlord", "manager", "tenant"]}><Profile /></ProtectedRoute>} />
        </Routes>
      </main>
    </div>
  );
};

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AuthProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </AuthProvider>
  </React.StrictMode>
);
