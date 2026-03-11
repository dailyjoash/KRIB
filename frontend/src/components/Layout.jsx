import React, { useContext, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  Boxes,
  Building2,
  ClipboardList,
  ChevronLeft,
  ChevronRight,
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
  const [headerVisible, setHeaderVisible] = useState(true);
  const [profilePhoto, setProfilePhoto] = useState(localStorage.getItem("profilePhoto") || "");
  const [isCompactView, setIsCompactView] = useState(() => window.matchMedia("(max-width: 900px)").matches);

  const links = useMemo(
    () =>
      [
        { to: getHomePath(user?.role), label: "Home", icon: Home, roles: ["landlord", "manager", "tenant"] },
        { to: "/properties/new", label: "Properties", icon: Building2, roles: ["landlord"] },
        { to: "/units/new", label: "Units", icon: Boxes, roles: ["landlord"] },
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
    const mediaQuery = window.matchMedia("(max-width: 900px)");
    const handleChange = (event) => {
      setIsCompactView(event.matches);
      if (!event.matches) {
        setMobileOpen(false);
      }
    };

    setIsCompactView(mediaQuery.matches);
    mediaQuery.addEventListener("change", handleChange);

    return () => mediaQuery.removeEventListener("change", handleChange);
  }, []);

  useEffect(() => {
    const onStorage = () => {
      setProfilePhoto(localStorage.getItem("profilePhoto") || "");
    };

    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  useEffect(() => {
    const onProfilePhotoChanged = () => {
      setProfilePhoto(localStorage.getItem("profilePhoto") || "");
    };

    window.addEventListener("profile-photo-updated", onProfilePhotoChanged);
    return () => window.removeEventListener("profile-photo-updated", onProfilePhotoChanged);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (isCompactView) {
      setHeaderVisible(true);
      return undefined;
    }

    let lastY = window.scrollY;

    const onScroll = () => {
      const y = window.scrollY;

      if (y <= 40) {
        setHeaderVisible(true);
      } else if (y < lastY) {
        setHeaderVisible(true);
      } else if (y > lastY) {
        setHeaderVisible(false);
      }

      lastY = y;
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [isCompactView]);

  useEffect(() => {
    localStorage.setItem("sidebarCollapsed", sidebarCollapsed ? "1" : "0");
  }, [sidebarCollapsed]);

  useEffect(() => {
    localStorage.setItem("theme", theme);
    document.documentElement.classList.toggle("theme-light", theme === "light");
  }, [theme]);

  const doLogout = () => {
    logout();
    navigate("/login");
  };

  const toggleTheme = () => {
    setTheme((current) => (current === "light" ? "dark" : "light"));
  };

  const onNavClick = () => {
    if (isCompactView) {
      setMobileOpen(false);
    }
  };

  const topbarLabel = typeof title === "string" ? title : null;
  const showBackButton = !MAIN_LANDING_PATHS.has(location.pathname);
  const displayIdentity = user?.name || user?.email || user?.role || "KRIB User";
  const initials =
    displayIdentity
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("") || "K";

  return (
    <div className={`layout-root ${sidebarCollapsed ? "sidebar-collapsed" : ""} ${isCompactView ? "mobile-view" : "desktop-view"}`}>
      <div className={`sidebar-backdrop ${mobileOpen && isCompactView ? "show" : ""}`} onClick={() => setMobileOpen(false)} />

      <aside className={`app-sidebar ${mobileOpen && isCompactView ? "open" : ""} ${sidebarCollapsed && !isCompactView ? "collapsed" : ""}`}>
        <div className="sidebar-header">
          <Link to={getHomePath(user?.role)} className="sidebar-brand" onClick={onNavClick}>
            <span className="sidebar-brand-mark">K</span>
            {sidebarCollapsed && !isCompactView ? null : <span>KRIB</span>}
          </Link>

          <div className="sidebar-header-actions">
            <button className="icon-btn desktop-only" onClick={() => setSidebarCollapsed((s) => !s)} type="button">
              {sidebarCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
            </button>
            <button className="icon-btn mobile-only" onClick={() => setMobileOpen(false)} type="button" aria-label="Close menu">
              <ChevronLeft size={18} />
            </button>
          </div>
        </div>

        {sidebarCollapsed && !isCompactView ? null : <p className="sidebar-role">{user?.role} workspace</p>}

        <nav className="sidebar-nav">
          {links.map((item) => {
            const Icon = item.icon;
            const active = location.pathname === item.to;
            return (
              <Link
                key={item.to}
                to={item.to}
                className={`sidebar-link ${active ? "active" : ""}`}
                onClick={onNavClick}
                title={sidebarCollapsed && !isCompactView ? item.label : ""}
              >
                <Icon size={19} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-actions">
          {sidebarCollapsed && !isCompactView ? null : (
            <div className="sidebar-profile-chip">
              {profilePhoto ? <img src={profilePhoto} alt="Profile" className="user-avatar" /> : <span className="user-avatar user-avatar-fallback">{initials}</span>}
              <div>
                <p className="sidebar-profile-name">{displayIdentity}</p>
                <p className="sidebar-profile-role">{user?.role}</p>
              </div>
            </div>
          )}
          <button className="btn btn-primary" onClick={doLogout} type="button">
            <LogOut size={18} />
            {sidebarCollapsed && !isCompactView ? null : <span>Logout</span>}
          </button>
        </div>
      </aside>

      <div className="layout-main">
        <header className={`topbar glass-card ${headerVisible ? "is-visible" : "is-hidden"}`}>
          <div className="topbar-row">
            <div className="topbar-left">
              {showBackButton ? (
                <button className="icon-btn topbar-back-btn" onClick={() => navigate(-1)} type="button" aria-label="Go back">
                  <ChevronLeft size={16} />
                </button>
              ) : null}
              <button className="icon-btn mobile-only" onClick={() => setMobileOpen(true)} type="button" aria-label="Open menu">
                <Menu size={18} />
              </button>
              {topbarLabel ? <span className="topbar-label">{topbarLabel}</span> : null}
            </div>
            <div className="topbar-right">
              {profilePhoto ? <img src={profilePhoto} alt="Profile" className="user-avatar" /> : <span className="user-avatar user-avatar-fallback">{initials}</span>}
              <button className="icon-btn" onClick={toggleTheme} type="button" aria-label="Toggle color theme">
                {theme === "light" ? <Moon size={18} /> : <Sun size={18} />}
              </button>
            </div>
          </div>
        </header>

        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}
