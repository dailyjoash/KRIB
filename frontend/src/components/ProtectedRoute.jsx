import React from "react";
import { Navigate } from "react-router-dom";

const rolePath = {
  landlord: "/dashboard",
  manager: "/manager",
  tenant: "/tenant",
};

const ProtectedRoute = ({ children, allowedRoles }) => {
  const token = localStorage.getItem("access");
  const role = localStorage.getItem("role");

  if (!token) {
    return <Navigate to="/" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(role)) {
    return <Navigate to={rolePath[role] || "/"} replace />;
  }

  return children;
};

export default ProtectedRoute;
