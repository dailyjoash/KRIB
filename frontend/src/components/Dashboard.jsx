import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Building2, CirclePlus, FilePlus2, Send, UserPlus } from "lucide-react";
import api from "../services/api";
import StatCards from "./StatCards";
import StatusBadge from "./StatusBadge";

const SECTIONS = ["PAID", "PARTIAL", "UNPAID", "OVERDUE"];
const formatCurrency = (amount) => Number(amount || 0).toFixed(2);

const PaymentTable = ({ section, rows }) => (
  <div className="card">
    <div className="card-head">
      <h3>{section} Payments</h3>
      <StatusBadge status={section} />
    </div>
    <table>
      <thead>
        <tr>
          <th>Tenant</th>
          <th>Unit</th>
          <th>Due</th>
          <th>Paid</th>
          <th>Balance</th>
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 ? (
          <tr><td colSpan={5} style={{ opacity: 0.7, textAlign: "center" }}>No records</td></tr>
        ) : rows.map((row) => (
          <tr key={row.lease_id}>
            <td>{row.tenant}</td>
            <td>{row.unit}</td>
            <td>{formatCurrency(row.rent_due)}</td>
            <td>{formatCurrency(row.paid_sum)}</td>
            <td>{formatCurrency(row.balance)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [payouts, setPayouts] = useState(null);
  const [form, setForm] = useState({ amount: "", method: "MPESA", destination: "" });
  const [isStaff, setIsStaff] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const [summaryRes, payoutRes, meRes] = await Promise.all([
        api.get("/api/dashboard/summary/"),
        api.get("/api/landlord/payouts/"),
        api.get("/api/me/"),
      ]);
      setData(summaryRes.data);
      setPayouts(payoutRes.data);
      setIsStaff(Boolean(meRes.data?.is_staff));
    } catch {
      setError("Failed to load dashboard");
      setData({ period: "-", totals: { expected: 0, collected: 0, outstanding: 0 }, lists: {} });
      setPayouts({ available_balance: 0, locked_balance: 0, payout_requests: [] });
    }
  };

  useEffect(() => { load(); }, []);

  const requestPayout = async () => {
    try {
      await api.post("/api/landlord/payouts/request/", form);
      setForm({ amount: "", method: "MPESA", destination: "" });
      await load();
    } catch (err) {
      setError(JSON.stringify(err.response?.data || "Failed to request payout"));
    }
  };

  const markPaid = async (id) => {
    try {
      await api.post(`/api/landlord/payouts/${id}/mark-paid/`);
      await load();
    } catch (err) {
      setError(JSON.stringify(err.response?.data || "Failed to mark paid"));
    }
  };

  if (!data || !payouts) return <div className="loading">Loading dashboard...</div>;

  return (
    <div className="dashboard-container">
      <p className="subtitle">Reporting period: {data.period}</p>
      {error && <p className="error">{error}</p>}

      <div className="card">
        <h3>Quick Actions</h3>
        <div className="action-links">
          <Link to="/properties/new" className="action-link"><Building2 size={16} /> Add Property</Link>
          <Link to="/units/new" className="action-link"><CirclePlus size={16} /> Add Unit</Link>
          <Link to="/invites/new" className="action-link"><Send size={16} /> Invite Tenant</Link>
          <Link to="/managers/invite" className="action-link"><UserPlus size={16} /> Invite Manager</Link>
          <Link to="/leases/new" className="action-link"><FilePlus2 size={16} /> Create Lease</Link>
        </div>
      </div>

      <StatCards expected={data.totals?.expected} collected={data.totals?.collected} outstanding={data.totals?.outstanding} />

      <div className="card">
        <h3>Maintenance</h3>
        <table>
          <thead>
            <tr>
              <th>Tenant</th>
              <th>Unit</th>
              <th>Issue</th>
              <th>Status</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            {(data.maintenance || []).map((m) => (
              <tr key={m.id}>
                <td>{m.tenant?.username}</td>
                <td>{m.lease?.unit?.unit_number || "-"}</td>
                <td>{m.issue}</td>
                <td><StatusBadge status={m.status} /></td>
                <td>{m.updated_at ? new Date(m.updated_at).toLocaleDateString() : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>Payouts</h3>
        <p>Available: {formatCurrency(payouts.available_balance)}</p>
        <p>Locked: {formatCurrency(payouts.locked_balance)}</p>
        <div className="form-stack">
          <input type="number" placeholder="Amount" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
          <select value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })}>
            <option value="MPESA">MPESA</option>
            <option value="BANK">BANK</option>
          </select>
          <input placeholder="Destination" value={form.destination} onChange={(e) => setForm({ ...form, destination: e.target.value })} />
          <button onClick={requestPayout}>Request Payout</button>
        </div>
        <table>
          <thead>
            <tr>
              <th>Amount</th>
              <th>Method</th>
              <th>Destination</th>
              <th>Status</th>
              <th>Created</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {(payouts.payout_requests || []).map((p) => (
              <tr key={p.id}>
                <td>{formatCurrency(p.amount)}</td>
                <td>{p.method}</td>
                <td>{p.destination}</td>
                <td><StatusBadge status={p.status} /></td>
                <td>{p.created_at ? new Date(p.created_at).toLocaleDateString() : "-"}</td>
                <td>{isStaff && p.status !== "PAID" ? <button onClick={() => markPaid(p.id)}>Mark Paid</button> : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {SECTIONS.map((section) => <PaymentTable key={section} section={section} rows={data.lists?.[section] || []} />)}
    </div>
  );
}
