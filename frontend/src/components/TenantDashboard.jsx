import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../services/api";
import BackButton from "./BackButton";

export default function TenantDashboard() {
  const [summary, setSummary] = useState(null);
  const [phone, setPhone] = useState("");
  const [amount, setAmount] = useState("");
  const [issue, setIssue] = useState("");
  const [maintenance, setMaintenance] = useState([]);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const [sumRes, maintRes] = await Promise.all([
        api.get("/api/dashboard/summary/"),
        api.get("/api/maintenance/"),
      ]);
      setSummary(sumRes.data);
      setMaintenance(maintRes.data || []);
    } catch (err) {
      setError("Failed to load tenant dashboard");
      setSummary({
        active_lease: null,
        payments: [],
        rent: {},
        show_overdue_banner: false
      });
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (!summary) return <p>Loading...</p>;
  if (!summary.active_lease) return <p>No active lease yet.</p>;

  const pay = async () => {
    setError("");
    try {
      await api.post("/api/payments/stk/initiate/", {
        lease_id: summary.active_lease.id,
        phone_number: phone,
        amount,
      });
      setPhone("");
      setAmount("");
      await load();
    } catch (err) {
      setError(JSON.stringify(err.response?.data || "Failed to initiate payment"));
    }
  };

  const createIssue = async () => {
    setError("");
    try {
      await api.post("/api/maintenance/", {
        lease_id: summary.active_lease.id,
        issue,
      });
      setIssue("");
      await load();
    } catch (err) {
      setError(JSON.stringify(err.response?.data || "Failed to create maintenance issue"));
    }
  };

  return (
    <div className="dashboard-container">
      <BackButton />
      <h2>Tenant Dashboard</h2>
      <p><Link to="/profile">Profile</Link></p>

      {error && <p className="error">{error}</p>}
      {summary.show_overdue_banner && <p className="error">Your rent is overdue.</p>}

      {/* Active Lease Info */}
      <div className="card">
        <h3>
          {summary.active_lease.unit.property.name} - Unit {summary.active_lease.unit.unit_number}
        </h3>
        <p>Status: {summary.rent.status}</p>
        <p>
          Due: ${Number(summary.rent.rent_due || 0).toFixed(2)} |
          Paid: ${Number(summary.rent.paid_sum || 0).toFixed(2)} |
          Balance: ${Number(summary.rent.balance || 0).toFixed(2)}
        </p>
      </div>

      {/* Pay Rent Section */}
      <div className="card">
        <h3>Pay Rent</h3>
        <div style={{ display: "flex", gap: "10px", flexDirection: "column", maxWidth: "300px" }}>
          <input
            placeholder="Phone (e.g., 2547...)"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
          <input
            placeholder="Amount"
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
          <button onClick={pay}>Initiate STK Push</button>
        </div>
      </div>

      {/* Report Maintenance Issue */}
      <div className="card">
        <h3>Report Maintenance Issue</h3>
        <div style={{ display: "flex", gap: "10px", flexDirection: "column", maxWidth: "300px" }}>
          <textarea
            value={issue}
            onChange={(e) => setIssue(e.target.value)}
            placeholder="Describe the issue..."
            rows="3"
          />
          <button onClick={createIssue}>Submit Request</button>
        </div>
      </div>

      {/* Maintenance Queue */}
      <div className="card">
        <h3>Your Maintenance Requests</h3>
        {maintenance.length === 0 ? (
          <p>No maintenance requests found.</p>
        ) : (
          <ul>
            {maintenance.map((m) => (
              <li key={m.id}>
                <strong>{m.issue}</strong> - Status: {m.status}
                {m.created_at && <span> (Submitted: {new Date(m.created_at).toLocaleDateString()})</span>}
              </li>
            ))}
          </ul>
        )}
        <Link to="/maintenance/new">
          <button style={{ marginTop: "10px" }}>Report via Form</button>
        </Link>
      </div>

      {/* Payment History */}
      <div className="card">
        <h3>Payment History</h3>
        {summary.payments?.length === 0 ? (
          <p>No payment history found.</p>
        ) : (
          <ul>
            {summary.payments?.map((p) => (
              <li key={p.id}>
                ${Number(p.amount).toFixed(2)} - {p.status}
                {p.created_at && <span> ({new Date(p.created_at).toLocaleDateString()})</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
