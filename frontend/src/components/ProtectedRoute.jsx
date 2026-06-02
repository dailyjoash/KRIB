import React, { useContext } from "react";
import { Navigate } from "react-router-dom";
import { AuthContext } from "../context/AuthContext";

const rolePath = {
  landlord: "/dashboard",
  manager: "/manager",
  tenant: "/tenant",
};

const ProtectedRoute = ({ children, allowedRoles }) => {
  const { authReady, isAuthenticated, role } = useContext(AuthContext);

  if (!authReady) {
    return null;
  }

  if (!isAuthenticated || !role) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(role)) {
    return <Navigate to={rolePath[role] || "/"} replace />;
  }

  return children;
};

export default ProtectedRoute;
