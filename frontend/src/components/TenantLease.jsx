import React, { useEffect, useState } from "react";
import { Building2, Home } from "lucide-react";
import api from "../services/api";
import GlassCard from "./GlassCard";
import StatusBadge from "./StatusBadge";

const formatCurrency = (amount) => Number(amount || 0).toFixed(2);

export default function TenantLease() {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get("/api/dashboard/summary/");
        setSummary(res.data);
      } catch {
        setError("Failed to load lease details");
        setSummary({ active_lease: null, rent: {} });
      }
    };
    load();
  }, []);

  if (!summary) return <p className="loading">Loading...</p>;

  return (
    <div className="dashboard-container">
      {error ? <p className="error">{error}</p> : null}
      <GlassCard title="Active Lease">
        {!summary.active_lease ? (
          <p>No active lease yet.</p>
        ) : (
          <div className="detail-grid">
            <p><Building2 size={18} /> Property: <strong>{summary.active_lease.unit?.property?.name || "-"}</strong></p>
            <p><Home size={18} /> Unit: <strong>{summary.active_lease.unit?.unit_number || "-"}</strong></p>
            <p>Monthly Rent: <strong>{formatCurrency(summary.active_lease.monthly_rent)}</strong></p>
            <p>Start: <strong>{summary.active_lease.start_date || "-"}</strong></p>
            <p>End: <strong>{summary.active_lease.end_date || "-"}</strong></p>
          </div>
        )}
      </GlassCard>

      <GlassCard title="Rent Status">
        <div className="detail-grid">
          <p>Status: <StatusBadge status={summary.rent?.status || "pending"} /></p>
          <p>Rent Due: <strong>{formatCurrency(summary.rent?.rent_due)}</strong></p>
          <p>Paid: <strong>{formatCurrency(summary.rent?.paid_sum)}</strong></p>
          <p>Balance: <strong>{formatCurrency(summary.rent?.balance)}</strong></p>
        </div>
      </GlassCard>
    </div>
  );
}
