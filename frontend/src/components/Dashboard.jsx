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
          <tr>
            <td colSpan={5} style={{ opacity: 0.7, textAlign: "center" }}>No records</td>
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
      } catch {
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

      <StatCards
        expected={data.totals?.expected}
        collected={data.totals?.collected}
        outstanding={data.totals?.outstanding}
      />

      <div className="card">
        <h3>Maintenance Overview</h3>
        <p className="subtitle">Track payment progress and pending actions by lease status.</p>
      </div>

      {SECTIONS.map((section) => (
        <PaymentTable key={section} section={section} rows={data.lists?.[section] || []} />
      ))}
    </div>
  );
}
