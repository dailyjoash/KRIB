import React, { useEffect, useMemo, useState } from "react";
import { Banknote, CalendarDays, CircleDollarSign, ShieldAlert } from "lucide-react";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { formatKES } from "../utils/format";
import StatusBadge from "./StatusBadge";
import { PageLayout, SectionCard, StatCard } from "./ui";

const STATUS_ORDER = ["PAID", "PARTIAL", "UNPAID", "OVERDUE"];

export default function ManagerOverview() {
  const [data, setData] = useState(null);
  const [period, setPeriod] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get("/api/dashboard/summary/", { params: period ? { period } : {} });
        setData(res.data);
        if (!period && res.data?.period) {
          setPeriod(res.data.period);
        }
      } catch (err) {
        setError(getErrorMessage(err, "Failed to load overview."));
      }
    };
    load();
  }, [period]);

  const statusBreakdown = useMemo(() => {
    if (!data?.lists) return [];
    return STATUS_ORDER.map((status) => {
      const rows = data.lists?.[status] || [];
      const balance = rows.reduce((sum, row) => sum + Number(row.balance || 0), 0);
      return { status, count: rows.length, balance };
    });
  }, [data]);

  const leaseRows = useMemo(() => {
    if (!data?.lists) return [];
    return STATUS_ORDER.flatMap((status) => (data.lists?.[status] || []).map((row) => ({ ...row, status })));
  }, [data]);

  if (!data) {
    return <div className="loading">Loading overview...</div>;
  }

  return (
    <PageLayout variant="executive" kicker="Manager Insights" title="Overview" chip={data.period || "-"}>
      {error ? <p className="error">{error}</p> : null}

      <section className="resident-hero-grid">
        <StatCard variant="blue" title="Expected" subtitle={`Period: ${data.period}`} value={formatKES(data.totals?.expected)} />
        <StatCard variant="purple" title="Collected" subtitle="Settled payments" value={formatKES(data.totals?.collected)} />
        <StatCard variant="mint" title="Outstanding" subtitle="Open balances" value={formatKES(data.totals?.outstanding)} />
      </section>

      <SectionCard icon={CalendarDays} title="Reporting Period">
        <div className="resident-toolbar">
          <label className="resident-inline-control">
            <CalendarDays size={16} />
            <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
          </label>
        </div>
      </SectionCard>

      <SectionCard icon={ShieldAlert} title="Rent Status Breakdown">
        <div className="resident-card-grid">
          {statusBreakdown.map((row) => (
            <article className="resident-row-card" key={row.status}>
              <div className="resident-row-id">
                {row.count}
              </div>
              <div className="resident-row-main">
                <h4>{row.status}</h4>
                <p>{formatKES(row.balance)} outstanding across this status bucket.</p>
              </div>
              <div className="resident-row-meta">
                <StatusBadge status={row.status} />
              </div>
            </article>
          ))}
        </div>
      </SectionCard>

      <SectionCard icon={CircleDollarSign} title="Lease and Unit Status">
        <div className="resident-table-list">
          {leaseRows.map((row) => (
            <article className="resident-row-card" key={row.lease_id}>
              <div className="resident-row-id">
                {row.lease_id}
              </div>
              <div className="resident-row-main">
                <h4>{row.tenant || "-"}</h4>
                <p>{row.unit || "-"}</p>
                <p>Expected {formatKES(row.rent_due)} / Collected {formatKES(row.paid_sum)} / Outstanding {formatKES(row.balance)}</p>
              </div>
              <div className="resident-row-meta">
                <StatusBadge status={row.status} />
              </div>
            </article>
          ))}
        </div>
      </SectionCard>
    </PageLayout>
  );
}
