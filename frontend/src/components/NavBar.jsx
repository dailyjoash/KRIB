import React, { useContext, useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { AuthContext } from "../context/AuthContext";

const getHomePath = (role) => (
  role === "landlord" ? "/dashboard" : role === "manager" ? "/manager" : "/tenant"
);

export default function NavBar() {
  const { user, logout } = useContext(AuthContext);
  const navigate = useNavigate();
  const location = useLocation();
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "dark");

  if (!user) return null;

  const doLogout = () => {
    logout();
    navigate("/");
  };

  const links = [
    ...(user.role === "landlord"
      ? [
        { to: "/properties/new", label: "Properties" },
        { to: "/units/new", label: "Units" },
        { to: "/invites/new", label: "Invites" },
        { to: "/leases/new", label: "Leases" },
      ]
      : []),
    ...(user.role === "manager"
      ? [
        { to: "/invites/new", label: "Invites" },
        { to: "/leases/new", label: "Leases" },
        { to: "/manager", label: "Maintenance" },
      ]
      : []),
    ...(user.role === "tenant"
      ? [
        { to: "/tenant", label: "Dashboard" },
        { to: "/maintenance/new", label: "Report Issue" },
      ]
      : []),
    { to: "/profile", label: "Profile" },
  ];

  const toggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    localStorage.setItem("theme", nextTheme);
    document.documentElement.classList.toggle("theme-dark", nextTheme === "dark");
  };

  return (
    <aside className="sidebar">
      <Link to={getHomePath(user.role)} className="sidebar-brand">
        KRIB
      </Link>
      <p className="sidebar-role">{user.role} workspace</p>

      <nav className="sidebar-nav">
        {links.map((item) => (
          <Link
            key={item.to}
            to={item.to}
            className={`sidebar-link ${location.pathname === item.to ? "active" : ""}`}
          >
            {item.label}
          </Link>
        ))}
      </nav>

      <div className="sidebar-actions">
        <button className="btn-muted" onClick={toggleTheme}>
          {theme === "dark" ? "Switch to light" : "Switch to dark"}
        </button>
        <button className="btn-secondary" onClick={doLogout}>Logout</button>
      </div>
    </aside>
  );
}
