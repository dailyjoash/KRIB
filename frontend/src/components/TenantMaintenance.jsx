import React, { useEffect, useState } from "react";
import { Send } from "lucide-react";
import api from "../services/api";
import GlassCard from "./GlassCard";
import StatusBadge from "./StatusBadge";

export default function TenantMaintenance() {
  const [leaseId, setLeaseId] = useState(null);
  const [issue, setIssue] = useState("");
  const [maintenance, setMaintenance] = useState([]);
  const [error, setError] = useState("");

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

  const createIssue = async () => {
    if (!leaseId) {
      setError("No active lease available for maintenance requests.");
      return;
    }
    try {
      await api.post("/api/maintenance/", { lease_id: leaseId, issue });
      setIssue("");
      await load();
    } catch (err) {
      setError(JSON.stringify(err.response?.data || "Failed to create maintenance issue"));
    }
  };

  return (
    <div className="dashboard-container">
      {error ? <p className="error">{error}</p> : null}
      <GlassCard title="Create Maintenance Request">
        <div className="form-stack">
          <textarea value={issue} onChange={(e) => setIssue(e.target.value)} placeholder="Describe the issue..." rows="3" />
          <button className="btn btn-primary" type="button" onClick={createIssue}>
            <Send size={18} />
            <span>Submit Request</span>
          </button>
        </div>
      </GlassCard>

      <GlassCard title="Your Maintenance Requests">
        {maintenance.length === 0 ? (
          <p>No maintenance requests found.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Issue</th>
                <th>Status</th>
                <th>Submitted</th>
              </tr>
            </thead>
            <tbody>
              {maintenance.map((item) => (
                <tr key={item.id}>
                  <td>{item.issue}</td>
                  <td><StatusBadge status={item.status} /></td>
                  <td>{item.created_at ? new Date(item.created_at).toLocaleDateString() : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </GlassCard>
    </div>
  );
}
