import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";

import Login from "./components/Login";
import Dashboard from "./components/Dashboard";
import ManagerDashboard from "./components/ManagerDashboard";
import TenantDashboard from "./components/TenantDashboard";
import AddProperty from "./components/AddProperty";
import ProtectedRoute from "./components/ProtectedRoute";

import "./styles.css";

const App = () => (
  <Routes>
    {/* Public route */}
    <Route path="/" element={<Login />} />

    {/* Landlord-only route */}
    <Route
      path="/dashboard"
      element={
        <ProtectedRoute allowedRoles={["landlord"]}>
          <Dashboard />
        </ProtectedRoute>
      }
    />

    {/* Manager-only route */}
    <Route
      path="/manager-dashboard"
      element={
        <ProtectedRoute allowedRoles={["manager"]}>
          <ManagerDashboard />
        </ProtectedRoute>
      }
    />

    {/* Tenant-only route */}
    <Route
      path="/tenant-dashboard"
      element={
        <ProtectedRoute allowedRoles={["tenant"]}>
          <TenantDashboard />
        </ProtectedRoute>
      }
    />

    {/* Add property (landlord only) */}
    <Route
      path="/properties/new"
      element={
        <ProtectedRoute allowedRoles={["landlord"]}>
          <AddProperty />
        </ProtectedRoute>
      }
    />
  </Routes>
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
