import React, { useState } from "react";
import api from "../services/api";

export default function MaintenanceNew() {
  const [leaseId, setLeaseId] = useState("");
  const [issue, setIssue] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    await api.post("/api/maintenance/", { lease_id: leaseId, issue });
    setIssue("");
  };

  return (
    <div className="card">
      <h3>Report Maintenance</h3>
      <form onSubmit={submit}>
        <input value={leaseId} onChange={(e) => setLeaseId(e.target.value)} placeholder="Active lease ID" required />
        <textarea value={issue} onChange={(e) => setIssue(e.target.value)} placeholder="Issue" required />
        <button type="submit">Submit</button>
      </form>
    </div>
  );
}
