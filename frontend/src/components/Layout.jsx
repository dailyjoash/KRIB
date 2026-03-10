import React, { useContext, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  Building2,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Hammer,
  Home,
  LogOut,
  Menu,
  Moon,
  Receipt,
  Send,
  ShieldCheck,
  Sun,
  UserCircle,
  Wallet,
  Users,
} from "lucide-react";
import { AuthContext } from "../context/AuthContext";

const getHomePath = (role) => (role === "landlord" ? "/dashboard" : role === "manager" ? "/manager" : "/tenant");

const MAIN_LANDING_PATHS = new Set(["/dashboard", "/manager", "/tenant", "/manager-dashboard", "/tenant-dashboard"]);

export default function Layout({ title, children }) {
  const { user, logout } = useContext(AuthContext);
  const navigate = useNavigate();
  const location = useLocation();

  const [mobileOpen, setMobileOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(localStorage.getItem("sidebarCollapsed") === "1");
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "light");

  const links = useMemo(
    () => [
      { to: getHomePath(user?.role), label: "Home", icon: Home, roles: ["landlord", "manager", "tenant"] },
      { to: "/properties/new", label: "Properties", icon: Building2, roles: ["landlord"] },
      { to: "/units/new", label: "Units", icon: ClipboardList, roles: ["landlord"] },
      { to: "/invites/new", label: "Invites", icon: Users, roles: ["landlord", "manager"] },
      { to: "/managers/invite", label: "Invite Manager", icon: ShieldCheck, roles: ["landlord"] },
      { to: "/leases/new", label: "Leases", icon: ClipboardList, roles: ["landlord", "manager"] },
      { to: "/maintenance/new", label: "Maintenance", icon: Hammer, roles: ["tenant"] },
      { to: "/tenant/payments", label: "Payments", icon: Receipt, roles: ["tenant"] },
      { to: "/tenant/wallet", label: "Wallet", icon: Wallet, roles: ["tenant"] },
      { to: "/profile", label: "Profile", icon: UserCircle, roles: ["landlord", "manager", "tenant"] },
    ].filter((item) => item.roles.includes(user?.role)),
    [user?.role]
  );

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    localStorage.setItem("sidebarCollapsed", sidebarCollapsed ? "1" : "0");
  }, [sidebarCollapsed]);

  useEffect(() => {
    localStorage.setItem("theme", theme);
    if (theme === "light") {
      document.documentElement.classList.add("theme-light");
    } else {
      document.documentElement.classList.remove("theme-light");
    }
  }, [theme]);

  const doLogout = () => {
    logout();
    navigate("/login");
  };

  const toggleTheme = () => {
    setTheme((current) => (current === "light" ? "dark" : "light"));
  };

  const topbarLabel = typeof title === "string" ? title : null;
  const showBackButton = !MAIN_LANDING_PATHS.has(location.pathname);

  return (
    <div className={`layout-root ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <div className={`sidebar-backdrop ${mobileOpen ? "show" : ""}`} onClick={() => setMobileOpen(false)} />

      <aside className={`app-sidebar ${mobileOpen ? "open" : ""} ${sidebarCollapsed ? "collapsed" : ""}`}>
        <div className="sidebar-header">
          <Link to={getHomePath(user?.role)} className="sidebar-brand" onClick={() => setMobileOpen(false)}>
            <span className="sidebar-brand-mark">K</span>
            {!sidebarCollapsed ? <span>KRIB</span> : null}
          </Link>

          <div className="sidebar-header-actions">
            <button className="icon-btn desktop-only" onClick={() => setSidebarCollapsed((s) => !s)} type="button">
              {sidebarCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
            </button>
            <button className="icon-btn mobile-only" onClick={() => setMobileOpen(false)} type="button">
              <ChevronLeft size={18} />
            </button>
          </div>
        </div>

        {!sidebarCollapsed ? <p className="sidebar-role">{user?.role} workspace</p> : null}

        <nav className="sidebar-nav">
          {links.map((item) => {
            const Icon = item.icon;
            const active = location.pathname === item.to;
            return (
              <Link
                key={item.to}
                to={item.to}
                className={`sidebar-link ${active ? "active" : ""}`}
                onClick={() => setMobileOpen(false)}
                title={sidebarCollapsed ? item.label : ""}
              >
                <Icon size={19} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-actions">
          <button className="btn btn-primary" onClick={doLogout} type="button">
            <LogOut size={18} />
            {!sidebarCollapsed ? <span>Logout</span> : null}
          </button>
        </div>
      </aside>

      <div className="layout-main">
        <header className="topbar glass-card">
          <div className="topbar-row">
            <div className="topbar-left">
              <button className="icon-btn mobile-only" onClick={() => setMobileOpen(true)} type="button">
                <Menu size={18} />
              </button>
              {topbarLabel ? <span className="topbar-label">{topbarLabel}</span> : null}
            </div>
            <div className="topbar-right">
              <button className="icon-btn" onClick={toggleTheme} type="button" aria-label="Toggle color theme">
                {theme === "light" ? <Moon size={18} /> : <Sun size={18} />}
              </button>
            </div>
          </div>
        </header>

        <main className="page-content">
          {showBackButton ? (
            <button className="floating-back-btn" onClick={() => navigate(-1)} type="button" aria-label="Go back">
              <ChevronLeft size={18} />
            </button>
          ) : null}
          {children}
        </main>
      </div>
    </div>
  );
}
