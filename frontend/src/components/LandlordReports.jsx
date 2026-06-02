import React, { useEffect, useMemo, useState } from "react";
import { BarChart3, CalendarDays, Download } from "lucide-react";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { downloadCsv } from "../utils/files";
import { formatDate, formatKES } from "../utils/format";
import StatusBadge from "./StatusBadge";
import { PageLayout, SectionCard, StatCard } from "./ui";

const monthKey = (value) => {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
};

const monthLabel = (key) => {
  if (!key) return "-";
  const [year, month] = key.split("-");
  return new Date(Number(year), Number(month) - 1, 1).toLocaleDateString("en-KE", {
    month: "short",
    year: "numeric",
  });
};

export default function LandlordReports() {
  const [payments, setPayments] = useState([]);
  const [directPayments, setDirectPayments] = useState([]);
  const [dashboard, setDashboard] = useState(null);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const [paymentsRes, directPaymentsRes, dashboardRes] = await Promise.all([
          api.get("/api/payments/"),
          api.get("/api/payments/direct/"),
          api.get("/api/dashboard/landlord/"),
        ]);
        setPayments(paymentsRes.data || []);
        setDirectPayments(directPaymentsRes.data || []);
        setDashboard(dashboardRes.data);
      } catch (err) {
        setError(getErrorMessage(err, "Failed to load reports."));
      }
    };
    load();
  }, []);

  const allReportPayments = useMemo(() => [
    ...payments.map((payment) => ({
      ...payment,
      report_source: "legacy",
      source_label: "KRIB-collected",
      report_status: payment.status,
    })),
    ...directPayments.map((payment) => ({
      ...payment,
      report_source: "direct",
      source_label: payment.verification_label === "verified_landlord_collected" ? "Verified landlord-collected" : "Tenant-reported / unverified",
      payment_method: "direct_paybill",
      report_status: payment.status,
    })),
  ], [directPayments, payments]);

  const filteredPayments = useMemo(() => {
    return allReportPayments.filter((payment) => {
      const value = payment.transaction_date || payment.created_at;
      if (!value) return false;
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return false;
      if (dateFrom && date < new Date(dateFrom)) return false;
      if (dateTo) {
        const end = new Date(dateTo);
        end.setHours(23, 59, 59, 999);
        if (date > end) return false;
      }
      return true;
    });
  }, [allReportPayments, dateFrom, dateTo]);

  const successfulPayments = useMemo(
    () => filteredPayments.filter((payment) => payment.status === "success" || payment.status === "confirmed"),
    [filteredPayments]
  );

  const monthlySeries = useMemo(() => {
    const totals = new Map();
    successfulPayments.forEach((payment) => {
      const key = monthKey(payment.billing_period || payment.transaction_date || payment.created_at);
      if (!key) return;
      totals.set(key, (totals.get(key) || 0) + Number(payment.amount || 0));
    });
    return Array.from(totals.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(-6)
      .map(([key, amount]) => ({ key, label: monthLabel(key), amount }));
  }, [successfulPayments]);

  const trendChart = useMemo(() => {
    if (monthlySeries.length === 0) return null;

    const width = 720;
    const height = 260;
    const padding = { top: 22, right: 26, bottom: 44, left: 26 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    const maxValue = Math.max(...monthlySeries.map((row) => row.amount), 1);
    const step = monthlySeries.length === 1 ? 0 : chartWidth / (monthlySeries.length - 1);
    const baseline = height - padding.bottom;
    const points = monthlySeries.map((row, index) => {
      const x = monthlySeries.length === 1 ? padding.left + chartWidth / 2 : padding.left + step * index;
      const y = padding.top + ((maxValue - row.amount) / maxValue) * chartHeight;
      return { ...row, x, y };
    });

    return {
      width,
      height,
      baseline,
      guideLines: [0, 0.25, 0.5, 0.75, 1].map((ratio) => padding.top + chartHeight * ratio),
      polylinePoints: points.map((point) => `${point.x},${point.y}`).join(" "),
      areaPoints: `${points[0].x},${baseline} ${points.map((point) => `${point.x},${point.y}`).join(" ")} ${points[points.length - 1].x},${baseline}`,
      points,
    };
  }, [monthlySeries]);

  const kpis = useMemo(() => ({
    collected: successfulPayments.reduce((sum, payment) => sum + Number(payment.amount || 0), 0),
    paymentCount: successfulPayments.length,
    arrears: Number(dashboard?.total_arrears || 0),
  }), [dashboard?.total_arrears, successfulPayments]);

  const paymentsByMonth = useMemo(() => {
    const groups = new Map();

    filteredPayments
      .slice()
      .sort((left, right) => {
        const leftTime = new Date(left.transaction_date || left.created_at || 0).getTime();
        const rightTime = new Date(right.transaction_date || right.created_at || 0).getTime();
        return rightTime - leftTime;
      })
      .forEach((payment) => {
        const key = monthKey(payment.transaction_date || payment.created_at || payment.billing_period);
        const resolvedKey = key || "unknown";
        if (!groups.has(resolvedKey)) {
          groups.set(resolvedKey, []);
        }
        groups.get(resolvedKey).push(payment);
      });

    return Array.from(groups.entries())
      .sort(([left], [right]) => right.localeCompare(left))
      .map(([key, rows]) => ({
        key,
        label: key === "unknown" ? "Unscheduled" : monthLabel(key),
        rows,
      }));
  }, [filteredPayments]);

  const exportCsv = () => {
    downloadCsv(
      "krib-report-payments.csv",
      ["Tenant", "Property", "Unit", "Amount", "Source", "Method", "Status", "Billing Period", "Processed"],
      filteredPayments.map((payment) => [
        payment.tenant?.username || payment.tenant?.email || "-",
        payment.lease?.unit?.property?.name || "-",
        payment.lease?.unit?.unit_number || "-",
        payment.amount,
        payment.source_label || "-",
        payment.payment_method,
        payment.status,
        payment.period,
        payment.transaction_date || payment.created_at,
      ])
    );
  };

  return (
    <PageLayout
      variant="executive"
      kicker="Landlord Reports"
      title="Portfolio reporting"
    >
      {error ? <p className="error">{error}</p> : null}

      <section className="resident-hero-grid">
        <StatCard variant="blue" title="Collected" subtitle="Legacy and direct records" value={formatKES(kpis.collected)} />
        <StatCard variant="purple" title="Payments" subtitle="Settled records" value={String(kpis.paymentCount).padStart(2, "0")} />
        <StatCard variant="mint" title="Arrears" subtitle="Current open balance" value={formatKES(kpis.arrears)} />
      </section>

      <SectionCard
        icon={BarChart3}
        title="Monthly Income Trend"
        action={(
          <button className="resident-link-btn" type="button" onClick={exportCsv}>
            <Download size={16} />
            <span>Export CSV</span>
          </button>
        )}
      >
        <div className="resident-toolbar">
          <label className="resident-inline-control">
            <CalendarDays size={16} />
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label className="resident-inline-control">
            <CalendarDays size={16} />
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
        </div>

        {monthlySeries.length === 0 ? (
          <p className="subtitle">No successful payments in the selected range yet.</p>
        ) : (
          <div className="report-line-chart">
            <svg
              className="report-line-svg"
              viewBox={`0 0 ${trendChart.width} ${trendChart.height}`}
              role="img"
              aria-label="Monthly income trend"
            >
              {trendChart.guideLines.map((y) => (
                <line key={y} x1="0" x2={trendChart.width} y1={y} y2={y} className="report-line-guide" />
              ))}
              <polygon points={trendChart.areaPoints} className="report-line-area" />
              <polyline points={trendChart.polylinePoints} className="report-line-path" />
              {trendChart.points.map((point) => (
                <g key={point.key}>
                  <circle cx={point.x} cy={point.y} r="6" className="report-line-dot" />
                </g>
              ))}
            </svg>

            <div className="report-line-labels">
              {monthlySeries.map((row) => (
                <div key={row.key} className="report-line-label-card">
                  <span>{row.label}</span>
                  <strong>{formatKES(row.amount)}</strong>
                </div>
              ))}
            </div>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Payments Table">
        {paymentsByMonth.length === 0 ? (
          <p className="subtitle">No payments available for the selected filters.</p>
        ) : (
          <div className="report-month-groups">
            {paymentsByMonth.map((group) => (
              <section key={group.key} className="report-month-group">
                <div className="report-month-group-head">
                  <h3>{group.label}</h3>
                </div>
                <div className="resident-table-list">
                  {group.rows.map((payment) => (
                    <article className="resident-row-card" key={`${payment.report_source}-${payment.id}`}>
                      <div className="resident-row-id">{payment.id}</div>
                      <div className="resident-row-main">
                        <h4>{payment.tenant?.username || payment.tenant?.email || "Tenant"}</h4>
                        <p>{payment.lease?.unit?.property?.name || "-"} / {payment.lease?.unit?.unit_number || "-"}</p>
                        <p>{formatKES(payment.amount)} / {payment.source_label || (payment.payment_method || "mpesa").toUpperCase()} / {payment.period || "-"}</p>
                      </div>
                      <div className="resident-row-meta">
                        <span>{formatDate(payment.transaction_date || payment.created_at)}</span>
                        <StatusBadge status={payment.status} />
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </SectionCard>
    </PageLayout>
  );
}
