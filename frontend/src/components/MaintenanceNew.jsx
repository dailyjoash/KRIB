import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../services/api";
import BackButton from "./BackButton";

export default function MaintenanceNew() {
  const [leaseId, setLeaseId] = useState("");
  const [issue, setIssue] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    api
      .get("/api/dashboard/summary/")
      .then((res) => {
        if (res.data?.active_lease?.id) {
          setLeaseId(String(res.data.active_lease.id));
        }
      })
      .catch(() => {
        // If it fails, user can still type lease id manually
      });
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError("");

    try {
      await api.post("/api/maintenance/", { lease_id: leaseId, issue });
      setIssue("");
      navigate("/tenant-dashboard");
    } catch (err) {
      setError(
        typeof err.response?.data === "string"
          ? err.response.data
          : JSON.stringify(err.response?.data || "Failed to submit maintenance")
      );
    }
  };

  return (
    <div className="dashboard-container">
      <div className="card">
      <BackButton />
      <h3>Report Maintenance</h3>

      {error && <p className="error">{error}</p>}

      <form onSubmit={submit}>
        <input
          value={leaseId}
          onChange={(e) => setLeaseId(e.target.value)}
          placeholder="Active lease ID"
          required
        />

        <textarea
          value={issue}
          onChange={(e) => setIssue(e.target.value)}
          placeholder="Describe the issue"
          required
        />

        <button type="submit">Submit</button>
      </form>
    </div>
    </div>
  );
}
