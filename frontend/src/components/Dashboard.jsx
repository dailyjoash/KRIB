import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../services/api";
import BackButton from "./BackButton";

const SECTIONS = ["PAID", "PARTIAL", "UNPAID", "OVERDUE"];

const formatCurrency = (amount) => {
  return Number(amount || 0).toFixed(2);
};

const PaymentTable = ({ section, rows }) => (
  <div className="card">
    <h3 className={`status-${section.toLowerCase()}`}>{section}</h3>
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
          <tr>
            <td colSpan={5} style={{ opacity: 0.7, textAlign: 'center' }}>
              No records
            </td>
          </tr>
        ) : (
          rows.map((row) => (
            <tr key={row.lease_id}>
              <td>{row.tenant}</td>
              <td>{row.unit}</td>
              <td>${formatCurrency(row.rent_due)}</td>
              <td>${formatCurrency(row.paid_sum)}</td>
              <td>${formatCurrency(row.balance)}</td>
            </tr>
          ))
        )}
      </tbody>
    </table>
  </div>
);

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        const res = await api.get("/api/dashboard/summary/");
        setData(res.data);
      } catch (e) {
        setError("Failed to load dashboard");
        setData({
          period: "-",
          totals: { expected: 0, collected: 0, outstanding: 0 },
          lists: { PAID: [], PARTIAL: [], UNPAID: [], OVERDUE: [] },
        });
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  if (loading) return <div className="loading">Loading dashboard...</div>;
  if (!data) return <div className="error">No data available</div>;

  return (
    <div className="dashboard-container">
      <BackButton />
      <h2>Landlord Dashboard ({data.period})</h2>

      {error && <p className="error">{error}</p>}

      <div className="card">
        <h3>Quick Actions</h3>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <Link to="/properties/new">Add Property</Link>
          <Link to="/units/new">Add Unit</Link>
          <Link to="/invites/new">Invite Tenant</Link>
          <Link to="/managers/invite">Invite Manager</Link>
          <Link to="/leases/new">Create Lease</Link>
          <Link to="/profile">Profile</Link>
        </div>
      </div>

      <div className="summary-stats">
        <p>
          Expected: ${formatCurrency(data.totals?.expected)} |
          Collected: ${formatCurrency(data.totals?.collected)} |
          Outstanding: ${formatCurrency(data.totals?.outstanding)}
        </p>
      </div>

      {SECTIONS.map((section) => (
        <PaymentTable
          key={section}
          section={section}
          rows={data.lists?.[section] || []}
        />
      ))}
    </div>
  );
}
