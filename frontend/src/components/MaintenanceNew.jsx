 codex/implement-full-krib-rental-workflow-prps6l
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import React, { useState } from "react";
 master
import api from "../services/api";

export default function MaintenanceNew() {
  const [leaseId, setLeaseId] = useState("");
  const [issue, setIssue] = useState("");
 codex/implement-full-krib-rental-workflow-prps6l
  const [error, setError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    api.get('/api/dashboard/summary/').then((res) => {
      if (res.data?.active_lease?.id) setLeaseId(String(res.data.active_lease.id));
    });
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await api.post("/api/maintenance/", { lease_id: leaseId, issue });
      navigate('/tenant-dashboard');
    } catch (err) {
      setError(JSON.stringify(err.response?.data || "Failed to submit maintenance"));
    }

  const submit = async (e) => {
    e.preventDefault();
    await api.post("/api/maintenance/", { lease_id: leaseId, issue });
    setIssue("");
master
  };

  return (
    <div className="card">
      <h3>Report Maintenance</h3>
      {error && <p className="error">{error}</p>}
      <form onSubmit={submit}>
        <input value={leaseId} onChange={(e) => setLeaseId(e.target.value)} placeholder="Active lease ID" required />
        <textarea value={issue} onChange={(e) => setIssue(e.target.value)} placeholder="Issue" required />
        <button type="submit">Submit</button>
      </form>
    </div>
  );
}
