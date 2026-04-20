import React, { useEffect, useMemo, useState } from "react";
import { CalendarDays, Plus, Search, Wrench } from "lucide-react";
import api from "../services/api";
import { formatDate } from "../utils/format";
import StatusBadge from "./StatusBadge";

export default function TenantMaintenance() {
  const [leaseId, setLeaseId] = useState(null);
  const [issue, setIssue] = useState("");
  const [urgency, setUrgency] = useState("");
  const [photo, setPhoto] = useState(null);
  const [search, setSearch] = useState("");
  const [month, setMonth] = useState("");
  const [showComposer, setShowComposer] = useState(false);
  const [maintenance, setMaintenance] = useState([]);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const load = async () => {
    try {
      const [summaryRes, maintRes] = await Promise.all([api.get("/api/dashboard/summary/"), api.get("/api/maintenance/")]);
      setLeaseId(summaryRes.data?.active_lease?.id || null);
      setMaintenance(maintRes.data || []);
    } catch {
      setError("Failed to load maintenance");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const rows = useMemo(
    () =>
      maintenance.filter((item) => {
        const matchesSearch = !search || JSON.stringify(item).toLowerCase().includes(search.toLowerCase());
        const matchesMonth = !month || String(item.created_at || "").includes(month);
        return matchesSearch && matchesMonth;
      }),
    [maintenance, month, search]
  );

  const hasActiveLease = Boolean(leaseId);
  const openTickets = useMemo(
    () => maintenance.filter((item) => item.status !== "resolved" && item.status !== "closed"),
    [maintenance]
  );
  const closedTickets = useMemo(
    () => maintenance.filter((item) => item.status === "resolved" || item.status === "closed"),
    [maintenance]
  );

  const createIssue = async () => {
    if (!leaseId) {
      setError("No active lease available for maintenance requests.");
      return;
    }
    try {
      const payload = new FormData();
      payload.append("lease_id", leaseId);
      payload.append("issue", issue);
      payload.append("urgency", urgency || "medium");
      if (photo) payload.append("photo_path", photo);
      await api.post("/api/maintenance/", payload, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setIssue("");
      setUrgency("");
      setPhoto(null);
      setShowComposer(false);
      setSuccess("Maintenance ticket submitted.");
      await load();
    } catch (err) {
      setError(JSON.stringify(err.response?.data || "Failed to create maintenance issue"));
    }
  };

  return (
    <div className="resident-page">
      {error ? <p className="error">{error}</p> : null}
      {success ? <p className="success">{success}</p> : null}

      <section className="resident-section-card">
        <div className="resident-section-head">
          <div className="resident-title-row">
            <Wrench size={20} />
            <h2>Maintenance Tickets</h2>
          </div>
        </div>

        <div className="resident-profile-columns">
          <div className="resident-profile-item">
            <span>Open</span>
            <strong>{String(openTickets.length).padStart(2, "0")}</strong>
          </div>
          <div className="resident-profile-item">
            <span>Closed</span>
            <strong>{String(closedTickets.length).padStart(2, "0")}</strong>
          </div>
          <div className="resident-profile-item">
            <span>Ticket Access</span>
            <strong>{hasActiveLease ? "Available" : "Move in first"}</strong>
          </div>
        </div>

        <div className="resident-toolbar">
          <label className="resident-search">
            <Search size={16} />
            <input value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search maintenance tickets" />
          </label>
          <div className="resident-calendar-wrap">
            <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
            <CalendarDays size={16} />
          </div>
          <button className="resident-primary-btn" type="button" disabled={!hasActiveLease} onClick={() => setShowComposer((prev) => !prev)}>
            <Plus size={16} />
            <span>{hasActiveLease ? "Raise a Ticket" : "Unavailable"}</span>
          </button>
        </div>

        {!hasActiveLease ? (
          <p className="resident-helper-text">
            Maintenance requests become available once a tenant has an active checked-in stay.
          </p>
        ) : null}

        {showComposer ? (
          <div className="resident-composer">
            <textarea value={issue} onChange={(e) => setIssue(e.target.value)} rows={4} aria-label="Issue description" />
            <select value={urgency} onChange={(e) => setUrgency(e.target.value)} aria-label="Urgency">
              <option value="" hidden></option>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
            <label className="resident-field">
              <span>Attach photo (optional)</span>
              <input type="file" accept=".jpg,.jpeg,.png" onChange={(e) => setPhoto(e.target.files?.[0] || null)} />
            </label>
            <button className="resident-primary-btn" type="button" onClick={createIssue}>Submit Ticket</button>
          </div>
        ) : null}

        <div className="resident-table-list">
          {rows.length === 0 ? (
            <p className="subtitle">No maintenance tickets found.</p>
          ) : (
            rows.map((item, index) => (
              <article className="resident-row-card" key={item.id}>
                <div className="resident-row-id">{index + 1}</div>
                <div className="resident-row-main">
                  <h4>{item.urgency === "high" ? "Urgent Issue" : "Maintenance Request"}</h4>
                  <p>{item.issue}</p>
                  {item.photo_path ? <p>Photo attached</p> : null}
                </div>
                <div className="resident-row-meta">
                  <span>{formatDate(item.created_at)}</span>
                  <StatusBadge status={item.status} />
                </div>
              </article>
            ))
          )}
        </div>
      </section>
    </div>
  );
}
