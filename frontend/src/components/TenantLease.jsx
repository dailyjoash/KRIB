import React, { useEffect, useMemo, useState } from "react";
import { Building2, CalendarClock, Home, Wallet } from "lucide-react";
import api from "../services/api";
import { formatDate, formatKES } from "../utils/format";
import StatusBadge from "./StatusBadge";

export default function TenantLease() {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get("/api/dashboard/summary/");
        setSummary(res.data);
      } catch {
        setError("Failed to load current lease details.");
        setSummary({ active_lease: null, rent: {} });
      }
    };
    load();
  }, []);

  const bookingRows = useMemo(() => {
    const lease = summary?.active_lease;
    if (!lease) return [];

    return [
      { label: "Property", value: lease.unit?.property?.name || "-" },
      { label: "Room", value: lease.unit?.unit_number || "-" },
      { label: "Lease Start", value: formatDate(lease.start_date) },
      { label: "Monthly Rent", value: formatKES(lease.rent_amount) },
      { label: "Due Day", value: lease.due_day || "-" },
      { label: "Status", value: lease.status || "-" },
    ];
  }, [summary?.active_lease]);

  if (!summary) return <p className="loading">Loading...</p>;

  const lease = summary.active_lease;

  return (
    <div className="resident-page">
      {error ? <p className="error">{error}</p> : null}

      <section className="resident-section-card">
        <div className="resident-section-head">
          <div className="resident-title-row">
            <Building2 size={20} />
            <h2>Current Lease</h2>
          </div>
          {lease ? <StatusBadge status={lease.status} /> : null}
        </div>

        {!lease ? (
          <p className="subtitle">No active lease yet.</p>
        ) : (
          <div className="resident-profile-columns">
            {bookingRows.map((row) => (
              <div className="resident-profile-item" key={row.label}>
                <span>{row.label}</span>
                <strong>{row.value}</strong>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="resident-section-card">
        <div className="resident-section-head">
          <div className="resident-title-row">
            <CalendarClock size={20} />
            <h2>Stay Snapshot</h2>
          </div>
        </div>

        {!lease ? (
          <p className="subtitle">Move-in details will appear here once a lease is active.</p>
        ) : (
          <div className="resident-card-grid">
            <div className="resident-token-box">
              <div className="resident-title-row">
                <Home size={18} />
                <h3>Assigned Unit</h3>
              </div>
              <p className="resident-helper-text">
                {lease.unit?.property?.name || "KRIB Residence"} / Room {lease.unit?.unit_number || "-"}
              </p>
            </div>

            <div className="resident-token-box">
              <div className="resident-title-row">
                <Wallet size={18} />
                <h3>Rent Status</h3>
              </div>
              <p className="resident-helper-text">
                {summary.rent?.status || "Pending"} / Balance {formatKES(summary.rent?.balance || 0)}
              </p>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
