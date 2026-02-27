import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../services/api";

export default function ManagerDashboard() {
  const [summary, setSummary] = useState(null);
  const [maintenance, setMaintenance] = useState([]);
  const [payments, setPayments] = useState([]);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const [sRes, mRes, pRes] = await Promise.all([
        api.get('/api/dashboard/summary/'),
        api.get('/api/maintenance/'),
        api.get('/api/payments/'),
      ]);
      setSummary(sRes.data);
      setMaintenance(mRes.data || []);
      setPayments(pRes.data || []);
    } catch (err) {
      setError("Failed to load manager data");
      setSummary({ period: "-", totals: { expected: 0, collected: 0, outstanding: 0 } });
    }
  };

  useEffect(() => { load(); }, []);

  const updateStatus = async (id, status) => {
    await api.patch(`/api/maintenance/${id}/`, { status });
    await load();
  };

  if (!summary) return <p>Loading...</p>;

  return (
    <div className="dashboard-container">
      <h2>Manager Dashboard ({summary.period})</h2>
      {error && <p className="error">{error}</p>}
      <p>
        Expected: {summary.totals.expected.toFixed(2)} | Collected: {summary.totals.collected.toFixed(2)} |
        Outstanding: {summary.totals.outstanding.toFixed(2)}
      </p>

      <div className="card">
        <h3>Quick Actions</h3>
        <Link to="/invites/new">Invite Tenant</Link> | <Link to="/leases/new">Create Lease</Link>
      </div>

      <div className="card">
        <h3>Maintenance Queue</h3>
        <table><thead><tr><th>Tenant</th><th>Issue</th><th>Status</th><th>Action</th></tr></thead>
          <tbody>
            {maintenance.map((m) => (
              <tr key={m.id}>
                <td>{m.tenant?.username}</td><td>{m.issue}</td><td>{m.status}</td>
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
        <table><thead><tr><th>Tenant</th><th>Period</th><th>Amount</th><th>Status</th></tr></thead>
          <tbody>{payments.map((p) => <tr key={p.id}><td>{p.tenant?.username}</td><td>{p.period}</td><td>{p.amount}</td><td>{p.status}</td></tr>)}</tbody>
        </table>
      </div>
    </div>
  );
}