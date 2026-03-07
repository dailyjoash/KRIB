import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CircleDollarSign, FilePlus2, Landmark, Send, ShieldAlert, Wrench } from "lucide-react";
import api from "../services/api";
import Greeting from "./Greeting";
import GradientCard from "./GradientCard";
import GlassCard from "./GlassCard";
import StatusBadge from "./StatusBadge";
import WelcomeBanner from "./WelcomeBanner";

const formatCurrency = (amount) => Number(amount || 0).toFixed(2);

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

  useEffect(() => { load(); }, []);

  const updateStatus = async (id, status) => {
    await api.patch(`/api/maintenance/${id}/`, { status });
    await load();
  };

  if (!summary) return <p>Loading...</p>;

  return (
    <div className="dashboard-container">
      <WelcomeBanner title={<Greeting />} subtitle="Manager view" />
      <p className="subtitle">Reporting period: {summary.period}</p>
      {error && <p className="error">{error}</p>}

      <section className="gradient-card-row">
        <GradientCard variant="blue" icon={Landmark} title="Expected" subtitle="Scheduled revenue" value={formatCurrency(summary.totals?.expected)} ctaLabel="Overview" />
        <GradientCard variant="indigo" icon={CircleDollarSign} title="Collected" subtitle="Settled payments" value={formatCurrency(summary.totals?.collected)} ctaLabel="Review" />
        <GradientCard variant="violet" icon={ShieldAlert} title="Outstanding" subtitle="Open balances" value={formatCurrency(summary.totals?.outstanding)} ctaLabel="Action" />
      </section>

      <GlassCard>
        <h3>Quick Actions</h3>
        <div className="action-links">
          <Link to="/invites/new" className="action-link"><Send size={16} /> Invite Tenant</Link>
          <Link to="/leases/new" className="action-link"><FilePlus2 size={16} /> Create Lease</Link>
        </div>
      </GlassCard>

      <GlassCard>
        <h3><Wrench size={16} /> Maintenance Queue</h3>
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
                <td>{m.lease?.unit ? `${m.lease.unit.property?.name || "-"} / ${m.lease.unit.unit_number}` : "-"}</td>
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
      </GlassCard>

      <GlassCard>
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
                <td>{p.lease?.unit ? `${p.lease.unit.property?.name || ""} / ${p.lease.unit.unit_number}` : "-"}</td>
                <td>{p.period}</td>
                <td>{p.amount}</td>
                <td><StatusBadge status={p.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </GlassCard>
    </div>
  );
}
