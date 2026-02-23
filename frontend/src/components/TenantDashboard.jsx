import React, { useEffect, useState } from "react";
import api from "../services/api";

export default function TenantDashboard() {
  const [summary, setSummary] = useState(null);
  const [phone, setPhone] = useState("");
  const [amount, setAmount] = useState("");
  const [issue, setIssue] = useState("");
  const [maintenance, setMaintenance] = useState([]);

  const load = async () => {
    const [sumRes, maintRes] = await Promise.all([
      api.get("/api/dashboard/summary/"),
      api.get("/api/maintenance/"),
    ]);
    setSummary(sumRes.data);
    setMaintenance(maintRes.data);
  };

  useEffect(() => {
    load();
  }, []);

  if (!summary) return <p>Loading...</p>;
  if (!summary.active_lease) return <p>No active lease yet.</p>;

  const pay = async () => {
    await api.post("/api/payments/stk/initiate/", {
      lease_id: summary.active_lease.id,
      phone_number: phone,
      amount,
    });
    await load();
  };

  const createIssue = async () => {
    await api.post("/api/maintenance/", {
      lease_id: summary.active_lease.id,
      issue,
    });
    setIssue("");
    await load();
  };

  return (
    <div className="dashboard-container">
      <h2>Tenant Dashboard</h2>
      {summary.show_overdue_banner && <p className="error">Your rent is overdue.</p>}
      <div className="card">
        <h3>{summary.active_lease.unit.property.name} - Unit {summary.active_lease.unit.unit_number}</h3>
        <p>Status: {summary.rent.status}</p>
        <p>Due: {summary.rent.rent_due} Paid: {summary.rent.paid_sum} Balance: {summary.rent.balance}</p>
      </div>
      <div className="card">
        <h3>Pay Rent</h3>
        <input placeholder="2547..." value={phone} onChange={(e) => setPhone(e.target.value)} />
        <input placeholder="Amount" value={amount} onChange={(e) => setAmount(e.target.value)} />
        <button onClick={pay}>Initiate STK Push</button>
      </div>
      <div className="card">
        <h3>Payment History</h3>
        <ul>{summary.payments.map((p) => <li key={p.id}>{p.amount} - {p.status}</li>)}</ul>
      </div>
      <div className="card">
        <h3>Maintenance</h3>
        <textarea value={issue} onChange={(e) => setIssue(e.target.value)} />
        <button onClick={createIssue}>Submit Request</button>
        <ul>{maintenance.map((m) => <li key={m.id}>{m.issue} - {m.status}</li>)}</ul>
      </div>
    </div>
  );
}
