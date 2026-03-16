import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CircleDollarSign, FilePlus2, Landmark, Send, ShieldAlert } from "lucide-react";
import api from "../services/api";
import { formatKES } from "../utils/format";
import GradientCard from "./GradientCard";
import GlassCard from "./GlassCard";
import Greeting from "./Greeting";
import StatusBadge from "./StatusBadge";
import WelcomeBanner from "./WelcomeBanner";

export default function ManagerDashboard() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [maintenance, setMaintenance] = useState([]);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const [sRes, mRes] = await Promise.all([api.get("/api/dashboard/summary/"), api.get("/api/maintenance/")]);
      setSummary(sRes.data);
      setMaintenance(mRes.data || []);
    } catch {
      setError("Failed to load manager data");
      setSummary({ period: "-", totals: { expected: 0, collected: 0, outstanding: 0 } });
      setMaintenance([]);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const updateStatus = async (id, status) => {
    await api.patch(`/api/maintenance/${id}/`, { status });
    await load();
  };

  if (!summary) return <p className="loading">Loading...</p>;

  return (
    <div className="dashboard-container dashboard-balanced">
      <WelcomeBanner title={<Greeting />} />
      {error && <p className="error">{error}</p>}

      <section className="gradient-card-row">
        <GradientCard variant="blue" icon={Landmark} title="Expected" subtitle={`Period: ${summary.period}`} value={formatKES(summary.totals?.expected)} ctaLabel="Overview" onCta={() => navigate("/manager/overview")} />
        <GradientCard variant="indigo" icon={CircleDollarSign} title="Collected" subtitle="Settled payments" value={formatKES(summary.totals?.collected)} ctaLabel="Review" onCta={() => navigate("/manager/review")} />
        <GradientCard variant="violet" icon={ShieldAlert} title="Outstanding" subtitle="Open balances" value={formatKES(summary.totals?.outstanding)} ctaLabel="Action" onCta={() => navigate("/manager/action")} />
      </section>

      <GlassCard title="Quick Actions" actions={<span className="subtitle">Tenant operations</span>}>
        <div className="action-links">
          <Link to="/invites/new" className="action-link"><Send size={18} /> Invite Tenant</Link>
          <Link to="/leases/new" className="action-link"><FilePlus2 size={18} /> Create Lease</Link>
        </div>
      </GlassCard>

      <GlassCard title="Maintenance Queue" actions={<span className="subtitle">Latest requests</span>}>
        <div className="table-scroll">
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
            {maintenance.slice(0, 5).map((m) => (
              <tr key={m.id}>
                <td>{m.tenant?.username || "-"}</td>
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
        </div>
      </GlassCard>
    </div>
  );
}
