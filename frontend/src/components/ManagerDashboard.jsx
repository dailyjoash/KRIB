import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { FilePlus2, Send } from "lucide-react";
import api from "../services/api";
import StatCards from "./StatCards";
import StatusBadge from "./StatusBadge";

export default function ManagerDashboard() {
  const [summary, setSummary] = useState(null);
  const [maintenance, setMaintenance] = useState([]);
  const [payments, setPayments] = useState([]);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const [sRes, mRes, pRes] = await Promise.all([
        api.get("/api/dashboard/summary/"),
        api.get("/api/maintenance/"),
        api.get("/api/payments/"),
      ]);
      setSummary(sRes.data);
      setMaintenance(mRes.data || []);
      setPayments(pRes.data || []);
    } catch {
      setError("Failed to load manager data");
      setSummary({ period: "-", totals: { expected: 0, collected: 0, outstanding: 0 } });
    }
  };

  useEffect(() => {
    load();
  }, []);

  const updateStatus = async (id, status) => {
    await api.patch(`/api/maintenance/${id}/`, { status });
    await load();
  };

  if (!summary) return <p>Loading...</p>;

  return (
    <div className="dashboard-container">
      <p className="subtitle">Reporting period: {summary.period}</p>
      {error && <p className="error">{error}</p>}

      <StatCards
        expected={summary.totals.expected}
        collected={summary.totals.collected}
        outstanding={summary.totals.outstanding}
      />

      <div className="card">
        <h3>Quick Actions</h3>
        <div className="action-links">
          <Link to="/invites/new" className="action-link"><Send size={16} /> Invite Tenant</Link>
          <Link to="/leases/new" className="action-link"><FilePlus2 size={16} /> Create Lease</Link>
        </div>
      </div>

      <div className="card">
        <h3>Maintenance Queue</h3>
        <table>
          <thead>
            <tr>
              <th>Tenant</th>
              <th>Unit</th>
              <th>Issue</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {maintenance.map((m) => (
              <tr key={m.id}>
                <td>{m.tenant?.username}</td>
                <td>{m.lease?.unit?.unit_number || "-"}</td>
                <td>{m.issue}</td>
                <td><StatusBadge status={m.status} /></td>
                <td>
                  <select onChange={(e) => updateStatus(m.id, e.target.value)} defaultValue="">
                    <option value="" disabled>Update</option>
                    <option value="open">Open</option>
                    <option value="in_progress">In Progress</option>
                    <option value="resolved">Resolved</option>
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>Payments (assigned properties)</h3>
        <table>
          <thead>
            <tr>
              <th>Tenant</th>
              <th>Unit</th>
              <th>Period</th>
              <th>Amount</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {payments.map((p) => (
              <tr key={p.id}>
                <td>{p.tenant?.username}</td>
                <td>{p.lease?.unit?.unit_number || "-"}</td>
                <td>{p.period}</td>
                <td>{p.amount}</td>
                <td><StatusBadge status={p.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
