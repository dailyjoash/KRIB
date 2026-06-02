import React, { useContext, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  Bell,
  Boxes,
  Building2,
  ClipboardList,
  FolderOpen,
  Hammer,
  Home,
  LogOut,
  Menu,
  ShieldCheck,
  UserCircle,
  Wallet,
  Users,
  X,
} from "lucide-react";
import { AuthContext } from "../context/AuthContext";
import api from "../services/api";
import { formatDateTime } from "../utils/format";
import brandImage from "../assets/Gemini_Generated_Image_2trnue2trnue2trn (1).png";

const getHomePath = (role) => (role === "landlord" ? "/dashboard" : role === "manager" ? "/manager" : "/tenant");

export default function Layout({ title, children }) {
  const { user, logout } = useContext(AuthContext);
  const navigate = useNavigate();
  const location = useLocation();

  const [mobileOpen, setMobileOpen] = useState(false);
  const [isCompactView, setIsCompactView] = useState(() => window.matchMedia("(max-width: 900px)").matches);
  const [tenantHasActiveLease, setTenantHasActiveLease] = useState(null);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [notificationsError, setNotificationsError] = useState("");
  const notificationMenuRef = useRef(null);
  const isTenant = user?.role === "tenant";
  const isExecutive = ["landlord", "manager"].includes(user?.role);

  useEffect(() => {
    if (user?.role !== "tenant") {
      setTenantHasActiveLease(null);
      return;
    }

    let cancelled = false;

    api.get("/api/dashboard/summary/")
      .then((res) => {
        if (!cancelled) {
          setTenantHasActiveLease(Boolean(res.data?.active_lease));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setTenantHasActiveLease(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [user?.role]);

  const links = useMemo(
    () => {
      if (user?.role === "tenant") {
        const tenantLinks = [
          { to: "/tenant", label: "Home", icon: Home },
        ];

        if (tenantHasActiveLease !== false) {
          tenantLinks.push({ to: "/tenant/maintenance", label: "Maintenance", icon: Hammer });
        }

        tenantLinks.push(
          { to: "/notifications", label: "Notices", icon: Bell },
          { to: "/tenant/finance?tab=wallet", label: "Financials", icon: Wallet },
          { to: "/documents", label: "Documents", icon: FolderOpen },
          { to: "/profile", label: "My Profile", icon: UserCircle },
        );

        return tenantLinks;
      }

      if (user?.role === "landlord") {
        return [
          { to: "/dashboard", label: "Home", icon: Home },
          { to: "/landlord/setup", label: "Properties", icon: Building2 },
          { to: "/landlord/invites", label: "Invite Manager", icon: ShieldCheck },
          { to: "/leases/new", label: "Create Lease", icon: ClipboardList },
          { to: "/landlord/payments", label: "Payments", icon: Wallet },
          { to: "/documents", label: "Documents", icon: FolderOpen },
          { to: "/profile", label: "Profile", icon: UserCircle },
        ];
      }

      if (user?.role === "manager") {
        return [
          { to: "/manager", label: "Home", icon: Home },
          { to: "/invites/new", label: "Invite Tenant", icon: Users },
          { to: "/leases/new", label: "Create Lease", icon: ClipboardList },
          { to: "/manager/payments", label: "Payments", icon: Wallet },
          { to: "/documents", label: "Documents", icon: FolderOpen },
          { to: "/profile", label: "Profile", icon: UserCircle },
        ];
      }

      return [
        { to: getHomePath(user?.role), label: "Home", icon: Home, roles: ["landlord", "manager", "tenant"] },
        { to: "/notifications", label: "Notifications", icon: Bell, roles: ["landlord", "manager", "tenant"] },
        { to: "/documents", label: "Documents", icon: FolderOpen, roles: ["landlord", "manager", "tenant"] },
        { to: "/profile", label: "Profile", icon: UserCircle, roles: ["landlord", "manager", "tenant"] },
        { to: "/landlord/payments", label: "Payments", icon: Wallet, roles: ["landlord"] },
        { to: "/properties/new", label: "Properties", icon: Building2, roles: ["landlord"] },
        { to: "/units/new", label: "Units", icon: Boxes, roles: ["landlord"] },
        { to: "/invites/new", label: "Invites", icon: Users, roles: ["landlord", "manager"] },
        { to: "/managers/invite", label: "Invite Manager", icon: ShieldCheck, roles: ["landlord"] },
        { to: "/leases/new", label: "Leases", icon: ClipboardList, roles: ["landlord", "manager"] },
      ].filter((item) => item.roles.includes(user?.role));
    },
    [tenantHasActiveLease, user?.role]
  );

  const mobilePrimaryLinks = useMemo(() => {
      if (user?.role === "tenant") {
        const tenantPrimaryLinks = [
          { to: "/tenant", label: "Home", icon: Home },
        ];

      if (tenantHasActiveLease !== false) {
        tenantPrimaryLinks.push({ to: "/tenant/maintenance", label: "Maintenance", icon: Hammer });
      }

        tenantPrimaryLinks.push(
          { to: "/tenant/finance?tab=wallet", label: "Financials", icon: Wallet },
          { to: "/profile", label: "Profile", icon: UserCircle },
        );

      return tenantPrimaryLinks;
    }

    if (user?.role === "manager") {
      return [
        { to: "/manager", label: "Home", icon: Home },
        { to: "/invites/new", label: "Invite", icon: Users },
        { to: "/manager/payments", label: "Payments", icon: Wallet },
        { to: "/profile", label: "Profile", icon: UserCircle },
      ];
    }

    return [
      { to: "/dashboard", label: "Home", icon: Home },
      { to: "/landlord/setup", label: "Properties", icon: Building2 },
      { to: "/landlord/payments", label: "Payments", icon: Wallet },
      { to: "/profile", label: "Profile", icon: UserCircle },
    ];
  }, [tenantHasActiveLease, user?.role]);

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
    setNotificationOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!notificationOpen) return;

    let cancelled = false;

    setNotificationsLoading(true);
    setNotificationsError("");

    api.get("/api/notifications/")
      .then((res) => {
        if (cancelled) return;
        const data = Array.isArray(res.data) ? res.data : res.data?.results || [];
        setNotifications(data);
      })
      .catch(() => {
        if (!cancelled) {
          setNotificationsError(isTenant ? "Unable to load notices." : "Unable to load notifications.");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setNotificationsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isTenant, notificationOpen]);

  useEffect(() => {
    if (!notificationOpen) return;

    const handlePointerDown = (event) => {
      if (!notificationMenuRef.current?.contains(event.target)) {
        setNotificationOpen(false);
      }
    };

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setNotificationOpen(false);
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [notificationOpen]);

  const doLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  const onNavClick = () => {
    if (isCompactView) setMobileOpen(false);
  };

  const isNavActive = (targetPath) => {
    const targetBase = targetPath.split("?")[0];

    if (targetBase === "/profile") {
      return location.pathname === "/profile" || location.pathname.startsWith("/profile/");
    }

    if (targetBase === "/dashboard") {
      return ["/dashboard", "/landlord", "/landlord/home"].includes(location.pathname);
    }

    if (targetBase === "/landlord/setup") {
      return ["/landlord/setup", "/properties/new", "/units/new", "/landlord/properties"].includes(location.pathname);
    }

    if (targetBase === "/landlord/invites") {
      return ["/landlord/invites", "/managers/invite"].includes(location.pathname);
    }

    if (targetBase === "/landlord/payments") {
      return ["/landlord/payments", "/landlord/reports", "/landlord/revenue", "/landlord/receipts", "/landlord/follow-up"].includes(location.pathname);
    }

    if (targetBase === "/manager") {
      return ["/manager", "/manager/home", "/manager-dashboard"].includes(location.pathname);
    }

    if (targetBase === "/manager/payments") {
      return ["/manager/payments", "/manager/overview", "/manager/review", "/manager/action"].includes(location.pathname);
    }

    if (targetBase === "/tenant") {
      return ["/tenant", "/tenant-dashboard", "/tenant/home"].includes(location.pathname);
    }

    if (targetBase === "/tenant/maintenance") {
      return ["/tenant/maintenance", "/maintenance/new"].includes(location.pathname);
    }

    if (targetBase === "/tenant/finance") {
      return ["/tenant/finance", "/tenant/pay", "/tenant/wallet", "/tenant/payments", "/tenant/financials"].includes(location.pathname);
    }

    return location.pathname === targetBase;
  };

  const topbarTitle = useMemo(() => {
    if (typeof title !== "string") return null;
    if (isExecutive) return null;
    if (title === "Notifications") return isTenant ? "Notices" : "Notifications";
    if (title === "Documents") return "Documents";
    if (title === "Units" && user?.role === "landlord") return "Add Unit";
    return title;
  }, [isExecutive, isTenant, title, user?.role]);

  const topbarLabel = isTenant && isCompactView ? null : topbarTitle;
  const minimalTopbar = !isCompactView && !isTenant && !topbarLabel;
  const notificationLabel = isTenant ? "notices" : "notifications";
  const unreadCount = useMemo(() => notifications.filter((item) => !item.is_read).length, [notifications]);
  const notificationPreview = useMemo(() => notifications.slice(0, 8), [notifications]);

  return (
    <div className={`layout-root ${isCompactView ? "mobile-view" : "desktop-view"} ${isTenant ? "tenant-shell" : ""} ${isExecutive ? "executive-shell" : ""}`}>
      <div className={`sidebar-backdrop ${mobileOpen && isCompactView ? "show" : ""}`} onClick={() => setMobileOpen(false)} />

      <aside className={`app-sidebar ${mobileOpen && isCompactView ? "open" : ""}`}>
        <div className="sidebar-header">
          <Link to={getHomePath(user?.role)} className="sidebar-brand" onClick={onNavClick}>
            <img src={brandImage} alt="KRIB" className="sidebar-brand-image" />
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
            const active = isNavActive(item.to);
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
        <header className={`topbar glass-card is-visible ${minimalTopbar ? "topbar-minimal" : ""}`.trim()}>
          <div className="topbar-row">
            <div className="topbar-left">
              <button className="icon-btn mobile-only" onClick={() => setMobileOpen(true)} type="button" aria-label="Open menu">
                <Menu size={18} />
              </button>
              {topbarLabel ? <span className="topbar-label">{topbarLabel}</span> : null}
            </div>
            <div className="topbar-right">
              <div className="notification-menu" ref={notificationMenuRef}>
                <button
                  className={`icon-btn ${isTenant ? "tenant-bell-btn" : ""}`.trim()}
                  type="button"
                  aria-label={notificationOpen ? `Close ${notificationLabel}` : `Open ${notificationLabel}`}
                  aria-haspopup="dialog"
                  aria-expanded={notificationOpen}
                  onClick={() => setNotificationOpen((open) => !open)}
                >
                  <Bell size={18} />
                  {unreadCount > 0 ? <span className="notification-badge">{unreadCount > 9 ? "9+" : unreadCount}</span> : null}
                </button>

                {notificationOpen ? (
                  <div className="notification-dropdown" role="dialog" aria-label={isTenant ? "Notices" : "Notifications"}>
                    <div className="notification-dropdown-head">
                      <div>
                        <strong>{isTenant ? "Notices" : "Notifications"}</strong>
                        <span>{unreadCount} unread</span>
                      </div>
                      <Link className="resident-link-btn notification-view-all" to="/notifications" onClick={() => setNotificationOpen(false)}>
                        View all
                      </Link>
                    </div>

                    <div className="notification-dropdown-list">
                      {notificationsLoading ? <p className="notification-dropdown-state">Loading...</p> : null}
                      {!notificationsLoading && notificationsError ? <p className="notification-dropdown-state">{notificationsError}</p> : null}
                      {!notificationsLoading && !notificationsError && notificationPreview.length === 0 ? (
                        <p className="notification-dropdown-state">{isTenant ? "No notices yet." : "No notifications yet."}</p>
                      ) : null}

                      {!notificationsLoading && !notificationsError
                        ? notificationPreview.map((item) => (
                            <Link
                              className={`notification-dropdown-item ${item.is_read ? "" : "unread"}`.trim()}
                              key={item.id}
                              to="/notifications"
                              onClick={() => setNotificationOpen(false)}
                            >
                              <span className="notification-dot" aria-hidden="true" />
                              <span className="notification-dropdown-copy">
                                <strong>{item.title || (isTenant ? "Notice" : "Notification")}</strong>
                                <span>{item.message || "Open notification center for details."}</span>
                                <small>{formatDateTime(item.created_at)}</small>
                              </span>
                            </Link>
                          ))
                        : null}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </header>

        <main className="page-content">{children}</main>
      </div>

      {isCompactView ? (
        <nav
          className="mobile-tabbar"
          aria-label="Primary"
          style={{ gridTemplateColumns: `repeat(${Math.max(mobilePrimaryLinks.length, 1)}, minmax(0, 1fr))` }}
        >
          {mobilePrimaryLinks.map((item) => {
            const Icon = item.icon;
            const active = isNavActive(item.to);
            return (
              <Link key={item.to} to={item.to} className={`mobile-tab ${active ? "active" : ""}`}>
                <span className="mobile-tab-icon">
                  <Icon size={18} />
                </span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      ) : null}
    </div>
  );
}
