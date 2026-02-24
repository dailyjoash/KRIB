import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../services/api";

const sections = ["PAID", "PARTIAL", "UNPAID", "OVERDUE"];

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const res = await api.get("/api/dashboard/summary/");
      setData(res.data);
    } catch {
      setError("Failed to load dashboard");
      setData({ period: "-", totals: { expected: 0, collected: 0, outstanding: 0 }, lists: { PAID: [], PARTIAL: [], UNPAID: [], OVERDUE: [] } });
    }
  };

  useEffect(() => { load(); }, []);

  if (!data) return <p>Loading...</p>;

  return (
    <div className="dashboard-container">
      <h2>Landlord Dashboard ({data.period})</h2>
      {error && <p className="error">{error}</p>}
      <div className="card">
        <h3>Quick Actions</h3>
        <Link to="/properties/new">Add Property</Link> | <Link to="/units/new">Add Unit</Link> | <Link to="/invites/new">Invite Tenant</Link> | <Link to="/leases/new">Create Lease</Link>
      </div>
      <p>
        Expected: {data.totals.expected.toFixed(2)} | Collected: {data.totals.collected.toFixed(2)} |
        Outstanding: {data.totals.outstanding.toFixed(2)}
      </p>
      {sections.map((section) => (
        <div className="card" key={section}>
          <h3>{section}</h3>
          <table>
            <thead><tr><th>Tenant</th><th>Unit</th><th>Due</th><th>Paid</th><th>Balance</th></tr></thead>
            <tbody>
              {(data.lists[section] || []).map((row) => (
                <tr key={row.lease_id}>
                  <td>{row.tenant}</td><td>{row.unit}</td><td>{row.rent_due}</td><td>{row.paid_sum}</td><td>{row.balance}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
