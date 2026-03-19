import React, { useContext, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  Boxes,
  Building2,
  ClipboardList,
  Hammer,
  Home,
  LogOut,
  Menu,
  Moon,
  Receipt,
  ShieldCheck,
  Sun,
  UserCircle,
  Wallet,
  Users,
  X,
} from "lucide-react";
import { AuthContext } from "../context/AuthContext";
import logo from "../assets/krib-logo.png";

const getHomePath = (role) => (role === "landlord" ? "/dashboard" : role === "manager" ? "/manager" : "/tenant");

export default function Layout({ title, children }) {
  const { user, logout } = useContext(AuthContext);
  const navigate = useNavigate();
  const location = useLocation();

  const [mobileOpen, setMobileOpen] = useState(false);
  const [isCompactView, setIsCompactView] = useState(() => window.matchMedia("(max-width: 900px)").matches);
  const [theme, setTheme] = useState(() => (localStorage.getItem("theme") === "dark" ? "dark" : "light"));

  const links = useMemo(
    () =>
      [
        { to: getHomePath(user?.role), label: "Home", icon: Home, roles: ["landlord", "manager", "tenant"] },
        { to: "/profile", label: "Profile", icon: UserCircle, roles: ["landlord", "manager", "tenant"] },
        { to: "/properties/new", label: "Properties", icon: Building2, roles: ["landlord"] },
        { to: "/units/new", label: "Units", icon: Boxes, roles: ["landlord"] },
        { to: "/invites/new", label: "Invites", icon: Users, roles: ["landlord", "manager"] },
        { to: "/managers/invite", label: "Invite Manager", icon: ShieldCheck, roles: ["landlord"] },
        { to: "/leases/new", label: "Leases", icon: ClipboardList, roles: ["landlord", "manager"] },
        { to: "/maintenance/new", label: "Maintenance", icon: Hammer, roles: ["tenant"] },
        { to: "/tenant/payments", label: "Payments", icon: Receipt, roles: ["tenant"] },
        { to: "/tenant/wallet", label: "Wallet", icon: Wallet, roles: ["tenant"] },
      ].filter((item) => item.roles.includes(user?.role)),
    [user?.role]
  );

  useEffect(() => {
    const mediaQuery = window.matchMedia("(max-width: 900px)");
    const handleChange = (event) => {
      setIsCompactView(event.matches);
      if (!event.matches) setMobileOpen(false);
    };

    setIsCompactView(mediaQuery.matches);
    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    localStorage.setItem("theme", theme);
    document.documentElement.classList.toggle("theme-light", theme === "light");
  }, [theme]);

  const doLogout = () => {
    logout();
    navigate("/login");
  };

  const onNavClick = () => {
    if (isCompactView) setMobileOpen(false);
  };

  const toggleTheme = () => {
    setTheme((prev) => (prev === "light" ? "dark" : "light"));
  };

  const topbarLabel = typeof title === "string" ? title : null;

  return (
    <div className={`layout-root ${isCompactView ? "mobile-view" : "desktop-view"}`}>
      <div className={`sidebar-backdrop ${mobileOpen && isCompactView ? "show" : ""}`} onClick={() => setMobileOpen(false)} />

      <aside className={`app-sidebar ${mobileOpen && isCompactView ? "open" : ""}`}>
        <div className="sidebar-header">
          <Link to={getHomePath(user?.role)} className="sidebar-brand" onClick={onNavClick}>
            <img src={logo} alt="KRIB logo" className="sidebar-logo" />
            <span className="sidebar-brand-text">KRIB</span>
          </Link>
          {isCompactView ? (
            <button className="icon-btn mobile-only" onClick={() => setMobileOpen(false)} type="button" aria-label="Close menu">
              <X size={18} />
            </button>
          ) : null}
        </div>

        <nav className="sidebar-nav">
          {links.map((item) => {
            const Icon = item.icon;
            const active = location.pathname === item.to;
            return (
              <Link key={item.to} to={item.to} className={`sidebar-link ${active ? "active" : ""}`} onClick={onNavClick}>
                <Icon size={19} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-actions">
          <button className="btn btn-primary" onClick={doLogout} type="button">
            <LogOut size={18} />
            <span>Logout</span>
          </button>
        </div>
      </aside>

      <div className="layout-main">
        <header className="topbar glass-card is-visible">
          <div className="topbar-row">
            <div className="topbar-left">
              <button className="icon-btn mobile-only" onClick={() => setMobileOpen(true)} type="button" aria-label="Open menu">
                <Menu size={18} />
              </button>
              {topbarLabel ? <span className="topbar-label">{topbarLabel}</span> : null}
            </div>
            <div className="topbar-right">
              <button className="theme-toggle" onClick={toggleTheme} type="button" aria-label="Toggle theme">
                {theme === "light" ? <Moon size={16} /> : <Sun size={16} />}
                <span>{theme === "light" ? "Dark" : "Light"}</span>
              </button>
            </div>
          </div>
        </header>

        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}
