import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CreditCard, Send } from "lucide-react";
import api from "../services/api";
import StatCards from "./StatCards";
import StatusBadge from "./StatusBadge";

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
    } catch {
      setError("Failed to load tenant dashboard");
      setSummary({ active_lease: null, payments: [], rent: {}, show_overdue_banner: false });
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
      await api.post("/api/maintenance/", { lease_id: summary.active_lease.id, issue });
      setIssue("");
      await load();
    } catch (err) {
      setError(JSON.stringify(err.response?.data || "Failed to create maintenance issue"));
    }
  };

  return (
    <div className="dashboard-container">
      <p className="subtitle"><Link to="/profile">Manage profile</Link></p>

      {error && <p className="error">{error}</p>}
      {summary.show_overdue_banner && <p className="error">Your rent is overdue.</p>}

      <StatCards
        expected={summary.rent.rent_due}
        collected={summary.rent.paid_sum}
        outstanding={summary.rent.balance}
      />

      <div className="card">
        <h3>{summary.active_lease.unit.property.name} - Unit {summary.active_lease.unit.unit_number}</h3>
        <p className="subtitle">Current status: <StatusBadge status={summary.rent.status} /></p>
      </div>

      <div className="card">
        <h3>Pay Rent</h3>
        <div className="form-stack">
          <input placeholder="Phone (e.g., 2547...)" value={phone} onChange={(e) => setPhone(e.target.value)} />
          <input placeholder="Amount" type="number" value={amount} onChange={(e) => setAmount(e.target.value)} />
          <button onClick={pay}><CreditCard size={16} /> Initiate STK Push</button>
        </div>
      </div>

      <div className="card">
        <h3>Report Maintenance Issue</h3>
        <div className="form-stack">
          <textarea value={issue} onChange={(e) => setIssue(e.target.value)} placeholder="Describe the issue..." rows="3" />
          <button onClick={createIssue}><Send size={16} /> Submit Request</button>
        </div>
      </div>

      <div className="card">
        <h3>Your Maintenance Requests</h3>
        {maintenance.length === 0 ? <p>No maintenance requests found.</p> : (
          <ul className="clean-list">
            {maintenance.map((m) => (
              <li key={m.id}>
                <strong>{m.issue}</strong> <StatusBadge status={m.status} />
                {m.created_at && <span> • Submitted: {new Date(m.created_at).toLocaleDateString()}</span>}
              </li>
            ))}
          </ul>
        )}
        <Link to="/maintenance/new" className="action-link">Report via Form</Link>
      </div>

      <div className="card">
        <h3>Payment History</h3>
        {summary.payments?.length === 0 ? <p>No payment history found.</p> : (
          <ul className="clean-list">
            {summary.payments?.map((p) => (
              <li key={p.id}>
                ${Number(p.amount).toFixed(2)} <StatusBadge status={p.status} />
                {p.created_at && <span> • {new Date(p.created_at).toLocaleDateString()}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
