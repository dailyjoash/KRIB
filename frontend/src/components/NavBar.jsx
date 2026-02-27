import React, { useContext } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthContext } from "../context/AuthContext";

export default function NavBar() {
  const { user, logout } = useContext(AuthContext);
  const navigate = useNavigate();

  if (!user) return null;

  const doLogout = () => {
    logout();
    navigate("/");
  };

  return (
    <nav style={{ display: "flex", gap: 12, padding: 12, background: "#111", color: "#fff", flexWrap: "wrap" }}>
      <Link to={user.role === "landlord" ? "/dashboard" : user.role === "manager" ? "/manager" : "/tenant"} style={{ color: "#fff" }}>KRIB</Link>

      {user.role === "landlord" && (
        <>
          <Link to="/properties/new" style={{ color: "#fff" }}>Properties</Link>
          <Link to="/units/new" style={{ color: "#fff" }}>Units</Link>
          <Link to="/invites/new" style={{ color: "#fff" }}>Invites</Link>
          <Link to="/leases/new" style={{ color: "#fff" }}>Leases</Link>
        </>
      )}

      {user.role === "manager" && (
        <>
          <Link to="/invites/new" style={{ color: "#fff" }}>Invites</Link>
          <Link to="/leases/new" style={{ color: "#fff" }}>Leases</Link>
          <Link to="/manager" style={{ color: "#fff" }}>Maintenance Queue</Link>
        </>
      )}

      {user.role === "tenant" && (
        <>
          <Link to="/tenant" style={{ color: "#fff" }}>Dashboard</Link>
          <Link to="/maintenance/new" style={{ color: "#fff" }}>Report Maintenance</Link>
        </>
      )}

      <Link to="/profile" style={{ color: "#fff" }}>Profile</Link>

      <button onClick={doLogout} style={{ marginLeft: "auto" }}>Logout</button>
    </nav>
  );
}
