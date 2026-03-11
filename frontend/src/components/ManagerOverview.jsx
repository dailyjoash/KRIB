import React, { useEffect, useMemo, useState } from "react";
import { Banknote, CircleDollarSign, ShieldAlert } from "lucide-react";
import api from "../services/api";
import { formatKES } from "../utils/format";
import GlassCard from "./GlassCard";
import GradientCard from "./GradientCard";
import StatusBadge from "./StatusBadge";

const STATUS_ORDER = ["PAID", "PARTIAL", "UNPAID", "OVERDUE"];

export default function ManagerOverview() {
  const [data, setData] = useState(null);
  const [period, setPeriod] = useState("");

  useEffect(() => {
    const load = async () => {
      const res = await api.get("/api/dashboard/summary/", { params: period ? { period } : {} });
      setData(res.data);
      if (!period && res.data?.period) {
        setPeriod(res.data.period);
      }
    };
    load();
  }, [period]);

  const statusBreakdown = useMemo(() => {
    if (!data?.lists) {
      return [];
    }

    return STATUS_ORDER.map((status) => {
      const rows = data.lists?.[status] || [];
      const balance = rows.reduce((sum, row) => sum + Number(row.balance || 0), 0);
      return { status, count: rows.length, balance };
    });
  }, [data]);

  const leaseRows = useMemo(() => {
    if (!data?.lists) {
      return [];
    }
    return STATUS_ORDER.flatMap((status) => (data.lists?.[status] || []).map((row) => ({ ...row, status })));
  }, [data]);

  if (!data) {
    return <div className="loading">Loading overview...</div>;
  }

  return (
    <div className="dashboard-container">
      <GlassCard title="Period Selector" actions={<span className="subtitle">Manager overview snapshot</span>}>
        <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
      </GlassCard>

      <section className="gradient-card-row">
        <GradientCard variant="blue" icon={Banknote} title="Expected" subtitle={`Period: ${data.period}`} value={formatKES(data.totals?.expected)} />
        <GradientCard variant="indigo" icon={CircleDollarSign} title="Collected" subtitle="Settled payments" value={formatKES(data.totals?.collected)} />
        <GradientCard variant="violet" icon={ShieldAlert} title="Outstanding" subtitle="Open balances" value={formatKES(data.totals?.outstanding)} />
      </section>

      <GlassCard title="Rent Status Breakdown" actions={<span className="subtitle">Counts and balances</span>}>
        <table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Leases</th>
              <th>Balance (KES)</th>
            </tr>
          </thead>
          <tbody>
            {statusBreakdown.map((row) => (
              <tr key={row.status}>
                <td><StatusBadge status={row.status} /></td>
                <td>{row.count}</td>
                <td>{formatKES(row.balance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </GlassCard>

      <GlassCard title="Lease / Unit Status" actions={<span className="subtitle">Current period by unit</span>}>
        <table>
          <thead>
            <tr>
              <th>Tenant</th>
              <th>Unit</th>
              <th>Status</th>
              <th>Expected</th>
              <th>Collected</th>
              <th>Outstanding</th>
            </tr>
          </thead>
          <tbody>
            {leaseRows.map((row) => (
              <tr key={row.lease_id}>
                <td>{row.tenant || "-"}</td>
                <td>{row.unit || "-"}</td>
                <td><StatusBadge status={row.status} /></td>
                <td>{formatKES(row.rent_due)}</td>
                <td>{formatKES(row.paid_sum)}</td>
                <td>{formatKES(row.balance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </GlassCard>
    </div>
  );
}
