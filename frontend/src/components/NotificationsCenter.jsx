import React, { useContext, useEffect, useMemo, useState } from "react";
import { BellRing, CheckCheck, Search, Send, Trash2 } from "lucide-react";
import api from "../services/api";
import { AuthContext } from "../context/AuthContext";
import { getErrorMessage } from "../utils/errors";
import { formatDateTime } from "../utils/format";
import StatusBadge from "./StatusBadge";
import { PageLayout, SectionCard } from "./ui";

const createDefaultForm = () => ({
  title: "",
  message: "",
  audience: "",
  property_id: "",
  send_in_app: false,
  send_email: false,
  send_sms: false,
});

const NOTICE_TEMPLATES = [
  {
    label: "Water Outage",
    title: "Water outage notice",
    message: "There will be a planned water interruption today. Please store enough water in advance.",
  },
  {
    label: "Rent Reminder",
    title: "Rent payment reminder",
    message: "This is a reminder to clear the current rent balance as soon as possible to avoid penalties.",
  },
];

const matchesQuery = (item, query) => {
  if (!query) return true;
  const haystack = [item.title, item.message, item.type, item.period].filter(Boolean).join(" ").toLowerCase();
  return haystack.includes(query);
};

const matchesStatus = (item, status) => {
  if (status === "unread") return !item.is_read;
  if (status === "read") return item.is_read;
  return true;
};

function NotificationRow({ item, onMarkRead, onDelete }) {
  return (
    <article className="stack-item" key={item.id}>
      <div className="stack-item-main">
        <div className="stack-item-icon"><BellRing size={18} /></div>
        <div>
          <h4>{item.title}</h4>
          <p className="subtitle">{item.message}</p>
          <p className="subtitle">{formatDateTime(item.created_at)}</p>
        </div>
      </div>
      <div className="stack-item-side notification-row-actions">
        <StatusBadge status={item.type} />
        {!item.is_read ? (
          <button className="btn" type="button" onClick={() => onMarkRead(item.id)}>
            <CheckCheck size={16} />
            <span>Mark read</span>
          </button>
        ) : null}
        <button className="btn btn-glass" type="button" onClick={() => onDelete(item.id)}>
          <Trash2 size={16} />
          <span>Dismiss</span>
        </button>
      </div>
    </article>
  );
}

export default function NotificationsCenter() {
  const { user } = useContext(AuthContext);
  const [notifications, setNotifications] = useState([]);
  const [properties, setProperties] = useState([]);
  const [form, setForm] = useState(createDefaultForm);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const canCompose = user?.role === "landlord" || user?.role === "manager" || user?.is_staff;
  const canSendNotification = Boolean(
    form.title.trim() &&
    form.message.trim() &&
    form.audience &&
    (form.send_in_app || form.send_email || form.send_sms)
  );

  const load = async () => {
    setError("");
    try {
      if (canCompose) {
        const [notificationRes, propertyRes] = await Promise.all([
          api.get("/api/notifications/"),
          api.get("/api/properties/"),
        ]);
        setNotifications(notificationRes.data || []);
        setProperties(propertyRes.data || []);
        return;
      }

      const res = await api.get("/api/notifications/");
      setNotifications(res.data || []);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load notifications."));
    }
  };

  useEffect(() => {
    load();
  }, [canCompose]);

  const counts = useMemo(
    () => ({
      unread: notifications.filter((item) => !item.is_read).length,
      read: notifications.filter((item) => item.is_read).length,
    }),
    [notifications]
  );

  const filteredNotifications = useMemo(() => {
    const lowered = query.trim().toLowerCase();
    return notifications.filter((item) => matchesQuery(item, lowered) && matchesStatus(item, statusFilter));
  }, [notifications, query, statusFilter]);

  const grouped = useMemo(
    () => ({
      unread: filteredNotifications.filter((item) => !item.is_read),
      history: filteredNotifications.filter((item) => item.is_read),
    }),
    [filteredNotifications]
  );

  const audienceOptions = useMemo(() => {
    const options = [
      { value: "everyone", label: canCompose && !user?.is_staff ? "Everyone in your portfolio" : "Everyone" },
      { value: "tenants", label: "Tenants" },
      { value: "managers", label: "Managers" },
    ];

    if (user?.is_staff) {
      options.push({ value: "landlords", label: "Landlords" });
    }

    return options;
  }, [canCompose, user?.is_staff]);

  const markRead = async (id) => {
    setError("");
    try {
      await api.patch(`/api/notifications/${id}/`, { is_read: true });
      setNotifications((prev) => prev.map((item) => (item.id === id ? { ...item, is_read: true } : item)));
    } catch (err) {
      setError(getErrorMessage(err, "Failed to update notification."));
    }
  };

  const markAllRead = async () => {
    setError("");
    try {
      await api.patch("/api/notifications/read-all/");
      setNotifications((prev) => prev.map((item) => ({ ...item, is_read: true })));
      setSuccess("Unread notifications marked as read.");
    } catch (err) {
      setError(getErrorMessage(err, "Failed to mark notifications as read."));
    }
  };

  const deleteNotification = async (id) => {
    setError("");
    try {
      await api.delete(`/api/notifications/${id}/`);
      setNotifications((prev) => prev.filter((item) => item.id !== id));
    } catch (err) {
      setError(getErrorMessage(err, "Failed to remove notification."));
    }
  };

  const clearRead = async () => {
    setError("");
    try {
      await api.delete("/api/notifications/clear-read/");
      setNotifications((prev) => prev.filter((item) => !item.is_read));
      setSuccess("Read notifications cleared.");
    } catch (err) {
      setError(getErrorMessage(err, "Failed to clear read notifications."));
    }
  };

  const applyTemplate = (template) => {
    setForm((prev) => ({
      ...prev,
      title: template.title,
      message: template.message,
    }));
  };

  const resetForm = () => {
    setForm(createDefaultForm());
  };

  const sendNotification = async (event) => {
    event.preventDefault();
    setSending(true);
    setError("");
    setSuccess("");

    try {
      const payload = { ...form };
      if (!payload.property_id || payload.property_id === "__all") delete payload.property_id;
      const response = await api.post("/api/notifications/send/", payload);
      setSuccess(response.data?.detail || "Notification sent successfully.");
      setForm(createDefaultForm());
      await load();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to send notification."));
    } finally {
      setSending(false);
    }
  };

  const toolbar = (
    <div className="resident-toolbar">
      <label className="resident-search">
        <Search size={16} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Search notifications" />
      </label>
      <label className="resident-inline-control">
        <BellRing size={16} />
        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          <option value="all">All</option>
          <option value="unread">Unread</option>
          <option value="read">Read</option>
        </select>
      </label>
      <div className="toolbar-action-group">
        {counts.unread ? (
          <button className="btn" type="button" onClick={markAllRead}>
            <CheckCheck size={16} />
            <span>Mark all read</span>
          </button>
        ) : null}
        {counts.read ? (
          <button className="btn btn-glass" type="button" onClick={clearRead}>
            <Trash2 size={16} />
            <span>Clear read</span>
          </button>
        ) : null}
      </div>
    </div>
  );

  if (user?.role === "tenant") {
    return (
      <div className="resident-page">
        {error ? <p className="error">{error}</p> : null}
        {success ? <p className="success">{success}</p> : null}

        <section className="resident-section-card">
          <div className="resident-section-head">
            <div className="resident-title-row">
              <BellRing size={20} />
              <h2>Notice Board</h2>
            </div>
            <span className="resident-chip">{counts.unread} unread / {notifications.length} total</span>
          </div>

          {toolbar}

          <div className="resident-notice-list">
            {filteredNotifications.length === 0 ? (
              <p className="subtitle">{notifications.length === 0 ? "No notices available." : "No notices match the current filter."}</p>
            ) : (
              grouped.unread.concat(grouped.history).map((item) => (
                <article className="resident-notice-card" key={item.id}>
                  <div className="resident-notice-top">
                    <div className="resident-title-row">
                      <span className="resident-mini-icon"><BellRing size={14} /></span>
                      <h4>{item.title}</h4>
                    </div>
                    <div className="resident-row-meta">
                      <StatusBadge status={item.type} />
                      {!item.is_read ? (
                        <button className="resident-link-btn" type="button" onClick={() => markRead(item.id)}>Mark read</button>
                      ) : null}
                      <button className="resident-link-btn" type="button" onClick={() => deleteNotification(item.id)}>Dismiss</button>
                    </div>
                  </div>
                  <p className="resident-notice-body expanded">{item.message}</p>
                  <div className="resident-notice-date">
                    <span>{formatDateTime(item.created_at)}</span>
                  </div>
                </article>
              ))
            )}
          </div>
        </section>
      </div>
    );
  }

  return (
    <PageLayout variant="executive" kicker="Notifications" title="Notification Center">
      {error ? <p className="error">{error}</p> : null}
      {success ? <p className="success">{success}</p> : null}

      {canCompose ? (
        <SectionCard
          icon={Send}
          title="Send Notification"
          action={<span className="subtitle">{properties.length} properties available</span>}
        >
          <div className="notification-template-list">
            {NOTICE_TEMPLATES.map((template) => (
              <button key={template.label} className="notification-template-btn" type="button" onClick={() => applyTemplate(template)}>
                {template.label}
              </button>
            ))}
          </div>

          <form className="resident-form-grid" onSubmit={sendNotification}>
            <label className="resident-field">
              <span>Title</span>
              <input
                value={form.title}
                onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))}
                required
              />
            </label>

            <label className="resident-field">
              <span>Audience</span>
              <select value={form.audience} onChange={(event) => setForm((prev) => ({ ...prev, audience: event.target.value }))} required>
                <option value="" hidden></option>
                {audienceOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="resident-field">
              <span>Property</span>
              <select value={form.property_id} onChange={(event) => setForm((prev) => ({ ...prev, property_id: event.target.value }))}>
                <option value="" hidden></option>
                <option value="__all">All properties</option>
                {properties.map((property) => (
                  <option key={property.id} value={property.id}>
                    {property.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="resident-field notification-message-field">
              <span>Message</span>
              <textarea
                value={form.message}
                onChange={(event) => setForm((prev) => ({ ...prev, message: event.target.value }))}
                rows="5"
                required
              />
            </label>

            <div className="notification-channel-list">
              <label className="notification-channel-option">
                <input
                  type="checkbox"
                  checked={form.send_in_app}
                  onChange={(event) => setForm((prev) => ({ ...prev, send_in_app: event.target.checked }))}
                />
                <span>In-app notice</span>
              </label>
              <label className="notification-channel-option">
                <input
                  type="checkbox"
                  checked={form.send_email}
                  onChange={(event) => setForm((prev) => ({ ...prev, send_email: event.target.checked }))}
                />
                <span>Email</span>
              </label>
              <label className="notification-channel-option">
                <input
                  type="checkbox"
                  checked={form.send_sms}
                  onChange={(event) => setForm((prev) => ({ ...prev, send_sms: event.target.checked }))}
                />
                <span>SMS</span>
              </label>
            </div>

            <p className="subtitle notification-helper">
              Choose one or more channels. Email needs SMTP configured, and SMS uses Africa&apos;s Talking.
            </p>

            <div className="resident-form-actions resident-profile-form-actions">
              <button className="resident-link-btn" type="button" onClick={resetForm} disabled={sending || (!form.title && !form.message && !form.property_id && !form.audience && !form.send_in_app && !form.send_email && !form.send_sms)}>
                Reset
              </button>
              <button className="resident-primary-btn" type="submit" disabled={sending || !canSendNotification}>
                <Send size={16} />
                <span>{sending ? "Sending..." : "Send Notification"}</span>
              </button>
            </div>
          </form>
        </SectionCard>
      ) : null}

      <SectionCard icon={BellRing} title="Notification Tools" action={<span className="subtitle">{counts.unread} unread / {counts.read} read</span>}>
        {toolbar}
      </SectionCard>

      <SectionCard title="Unread">
        {grouped.unread.length === 0 ? (
          <p>{filteredNotifications.length === 0 ? "No notifications match the current filter." : "No unread notifications."}</p>
        ) : (
          <div className="stack-list">
            {grouped.unread.map((item) => (
              <NotificationRow key={item.id} item={item} onMarkRead={markRead} onDelete={deleteNotification} />
            ))}
          </div>
        )}
      </SectionCard>

      <SectionCard title="Read">
        {grouped.history.length === 0 ? (
          <p>{notifications.length === 0 ? "No notifications yet." : "No read notifications match the current filter."}</p>
        ) : (
          <div className="stack-list">
            {grouped.history.map((item) => (
              <NotificationRow key={item.id} item={item} onMarkRead={markRead} onDelete={deleteNotification} />
            ))}
          </div>
        )}
      </SectionCard>
    </PageLayout>
  );
}
