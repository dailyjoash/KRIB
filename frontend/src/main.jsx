import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";

import Login from "./components/Login";
import Dashboard from "./components/Dashboard";
import ManagerDashboard from "./components/ManagerDashboard";
import TenantDashboard from "./components/TenantDashboard";
import AddProperty from "./components/AddProperty";
import UnitsNew from "./components/UnitsNew";
import InvitesNew from "./components/InvitesNew";
import LeasesNew from "./components/LeasesNew";
import MaintenanceNew from "./components/MaintenanceNew";
import ProtectedRoute from "./components/ProtectedRoute";
import NavBar from "./components/NavBar";

import "./styles.css";

const App = () => (
  <>
    <NavBar />
    <Routes>
      <Route path="/" element={<Login />} />

      <Route path="/dashboard" element={<ProtectedRoute allowedRoles={["landlord"]}><Dashboard /></ProtectedRoute>} />
      <Route path="/manager-dashboard" element={<ProtectedRoute allowedRoles={["manager"]}><ManagerDashboard /></ProtectedRoute>} />
      <Route path="/tenant-dashboard" element={<ProtectedRoute allowedRoles={["tenant"]}><TenantDashboard /></ProtectedRoute>} />

      <Route path="/properties/new" element={<ProtectedRoute allowedRoles={["landlord"]}><AddProperty /></ProtectedRoute>} />
      <Route path="/units/new" element={<ProtectedRoute allowedRoles={["landlord"]}><UnitsNew /></ProtectedRoute>} />
      <Route path="/invites/new" element={<ProtectedRoute allowedRoles={["landlord", "manager"]}><InvitesNew /></ProtectedRoute>} />
      <Route path="/leases/new" element={<ProtectedRoute allowedRoles={["landlord", "manager"]}><LeasesNew /></ProtectedRoute>} />
      <Route path="/maintenance/new" element={<ProtectedRoute allowedRoles={["tenant"]}><MaintenanceNew /></ProtectedRoute>} />
    </Routes>
  </>
);

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AuthProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </AuthProvider>
  </React.StrictMode>
);
