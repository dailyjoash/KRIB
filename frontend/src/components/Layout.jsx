import React, { useContext, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  Building2,
  ChevronLeft,
  ClipboardList,
  Hammer,
  Home,
  LogOut,
  Menu,
  Moon,
  ShieldCheck,
  Sun,
  UserCircle,
  Users,
} from "lucide-react";
import { AuthContext } from "../context/AuthContext";

const getHomePath = (role) => (role === "landlord" ? "/dashboard" : role === "manager" ? "/manager" : "/tenant");

export default function Layout({ title, subtitle, children }) {
  const { user, logout } = useContext(AuthContext);
  const navigate = useNavigate();
  const location = useLocation();
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "dark");
  const [open, setOpen] = useState(false);

  const links = useMemo(
    () => [
      { to: getHomePath(user?.role), label: "Dashboard", icon: Home, roles: ["landlord", "manager", "tenant"] },
      { to: "/properties/new", label: "Properties", icon: Building2, roles: ["landlord"] },
      { to: "/units/new", label: "Units", icon: ClipboardList, roles: ["landlord"] },
      { to: "/invites/new", label: "Invites", icon: Users, roles: ["landlord", "manager"] },
      { to: "/managers/invite", label: "Invite Manager", icon: ShieldCheck, roles: ["landlord"] },
      { to: "/leases/new", label: "Leases", icon: ClipboardList, roles: ["landlord", "manager"] },
      { to: "/maintenance/new", label: "Maintenance", icon: Hammer, roles: ["tenant"] },
      { to: "/profile", label: "Profile", icon: UserCircle, roles: ["landlord", "manager", "tenant"] },
    ].filter((item) => item.roles.includes(user?.role)),
    [user?.role]
  );

  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  const toggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    localStorage.setItem("theme", nextTheme);
    document.documentElement.classList.toggle("theme-dark", nextTheme === "dark");
  };

  const doLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="layout-root">
      <div className={`sidebar-backdrop ${open ? "show" : ""}`} onClick={() => setOpen(false)} />

      <aside className={`app-sidebar ${open ? "open" : ""}`}>
        <div className="sidebar-header">
          <Link to={getHomePath(user?.role)} className="sidebar-brand" onClick={() => setOpen(false)}>
            KRIB
          </Link>
          <button className="icon-btn mobile-only" onClick={() => setOpen(false)}>
            <ChevronLeft size={18} />
          </button>
        </div>

        <p className="sidebar-role">{user?.role} workspace</p>

        <nav className="sidebar-nav">
          {links.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.to}
                to={item.to}
                className={`sidebar-link ${location.pathname === item.to ? "active" : ""}`}
                onClick={() => setOpen(false)}
              >
                <Icon size={16} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-actions">
          <button className="btn-muted" onClick={toggleTheme}>
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            <span>{theme === "dark" ? "Light mode" : "Dark mode"}</span>
          </button>
          <button className="btn-secondary" onClick={doLogout}>
            <LogOut size={16} />
            <span>Logout</span>
          </button>
        </div>
      </aside>

      <div className="layout-main">
        <header className="topbar card">
          <div className="topbar-row">
            <button className="icon-btn mobile-only" onClick={() => setOpen(true)}>
              <Menu size={18} />
            </button>
            <div>
              <h1 className="topbar-title">{title}</h1>
              {subtitle ? <p className="subtitle">{subtitle}</p> : null}
            </div>
          </div>
        </header>

        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}
