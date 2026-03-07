import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Banknote, Building2, CirclePlus, Coins, FilePlus2, Send, ShieldCheck, UserPlus } from "lucide-react";
import api from "../services/api";
import GradientCard from "./GradientCard";
import GlassCard from "./GlassCard";
import Greeting from "./Greeting";
import StatusBadge from "./StatusBadge";
import WelcomeBanner from "./WelcomeBanner";

const formatCurrency = (amount) => Number(amount || 0).toFixed(2);

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get("/api/dashboard/summary/");
        setData(res.data);
      } catch {
        setError("Failed to load dashboard");
        setData({ period: "-", totals: { expected: 0, collected: 0, outstanding: 0 }, maintenance: [] });
      }
    };
    load();
  }, []);

  if (!data) return <div className="loading">Loading dashboard...</div>;

  return (
    <div className="dashboard-container">
      <WelcomeBanner title={<Greeting />} subtitle="Landlord view" />
      {error && <p className="error">{error}</p>}

      <section className="gradient-card-row">
        <GradientCard variant="blue" icon={Banknote} title="Expected" subtitle={`Period: ${data.period}`} value={formatCurrency(data.totals?.expected)} ctaLabel="Revenue" />
        <GradientCard variant="indigo" icon={Coins} title="Collected" subtitle="Successfully paid" value={formatCurrency(data.totals?.collected)} ctaLabel="Receipts" />
        <GradientCard variant="violet" icon={ShieldCheck} title="Outstanding" subtitle="Pending collection" value={formatCurrency(data.totals?.outstanding)} ctaLabel="Follow-up" />
      </section>

      <GlassCard title="Quick Actions">
        <div className="action-links">
          <Link to="/properties/new" className="action-link"><Building2 size={18} /> Add Property</Link>
          <Link to="/units/new" className="action-link"><CirclePlus size={18} /> Add Unit</Link>
          <Link to="/invites/new" className="action-link"><Send size={18} /> Invite Tenant</Link>
          <Link to="/managers/invite" className="action-link"><UserPlus size={18} /> Invite Manager</Link>
          <Link to="/leases/new" className="action-link"><FilePlus2 size={18} /> Create Lease</Link>
        </div>
      </GlassCard>

      <GlassCard title="Maintenance Preview" actions={<Link to="/leases/new">View all</Link>}>
        <table>
          <thead>
            <tr>
              <th>Tenant</th>
              <th>Unit</th>
              <th>Issue</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {(data.maintenance || []).slice(0, 5).map((m) => (
              <tr key={m.id}>
                <td>{m.tenant?.username || "-"}</td>
                <td>{m.lease?.unit ? `${m.lease.unit.property?.name || "-"} / ${m.lease.unit.unit_number}` : "-"}</td>
                <td>{m.issue}</td>
                <td><StatusBadge status={m.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </GlassCard>
    </div>
  );
}
