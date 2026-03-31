import React, { useEffect, useMemo, useState } from "react";
import { CalendarDays, Download, Mail, MessageSquare, Wallet } from "lucide-react";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { downloadBlob, downloadCsv } from "../utils/files";
import { formatDateTime, formatKES } from "../utils/format";
import { sendLeaseContactMessage } from "../utils/leaseContact";
import StatusBadge from "./StatusBadge";
import { PageLayout, SectionCard, StatCard } from "./ui";

const tabs = [
  { id: "payments", label: "Paid Rent" },
  { id: "arrears", label: "Arrears" },
];

const buildReminderMessage = (row) => {
  const label = row.status === "PARTIAL" ? "partially paid" : "unpaid";
  return `Hello ${row.tenant || "Tenant"}, your rent for ${row.unit || "-"} for ${row.period} is currently ${label}. Please clear the outstanding balance of ${formatKES(row.balance)} as soon as possible.`;
};

export default function ManagerPayments() {
  const [activeTab, setActiveTab] = useState("payments");
  const [payments, setPayments] = useState([]);
  const [summary, setSummary] = useState(null);
  const [period, setPeriod] = useState("");
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [sendingKey, setSendingKey] = useState("");
  const [amountsHidden, setAmountsHidden] = useState(() => {
    try {
      const stored = localStorage.getItem("krib-exec-amounts-hidden");
      return stored === null ? true : stored === "true";
    } catch {
      return true;
    }
  });

  const load = async (selectedPeriod = "") => {
    setError("");
    try {
      const params = selectedPeriod ? { period: selectedPeriod } : {};
      const [paymentsRes, summaryRes] = await Promise.all([
        api.get("/api/payments/", { params }),
        api.get("/api/dashboard/summary/", { params }),
      ]);
      setPayments(paymentsRes.data || []);
      setSummary(summaryRes.data);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load payments."));
      setPayments([]);
      setSummary({ period: selectedPeriod || "-", totals: { expected: 0, collected: 0, outstanding: 0 }, lists: {} });
    }
  };

  useEffect(() => {
    load(period);
  }, [period]);

  useEffect(() => {
    try {
      localStorage.setItem("krib-exec-amounts-hidden", String(amountsHidden));
    } catch {
      // Ignore storage failures and keep the in-memory state.
    }
  }, [amountsHidden]);

  const paidRows = useMemo(
    () => payments.filter((row) => row.status === "success"),
    [payments]
  );

  const arrearsRows = useMemo(() => {
    if (!summary?.lists) return [];

    const normalizedRows = ["UNPAID", "PARTIAL", "OVERDUE"].flatMap((status) =>
      (summary.lists?.[status] || []).map((row) => ({
        ...row,
        period: summary.period,
        status: status === "OVERDUE" ? (Number(row.cumulative_paid_sum || row.paid_sum || 0) > 0 ? "PARTIAL" : "UNPAID") : status,
      })),
    );

    const uniqueRows = new Map();
    normalizedRows.forEach((row) => {
      const existing = uniqueRows.get(row.lease_id);
      if (!existing || (existing.status === "UNPAID" && row.status === "PARTIAL")) {
        uniqueRows.set(row.lease_id, row);
      }
    });

    return Array.from(uniqueRows.values()).sort((left, right) => {
      const leftUnit = left.unit || "";
      const rightUnit = right.unit || "";
      const unitSort = leftUnit.localeCompare(rightUnit, undefined, { numeric: true, sensitivity: "base" });
      if (unitSort !== 0) return unitSort;
      return (left.tenant || "").localeCompare(right.tenant || "", undefined, { sensitivity: "base" });
    });
  }, [summary]);

  const filteredRows = useMemo(() => {
    const source = activeTab === "payments" ? paidRows : arrearsRows;
    if (!search) return source;
    const query = search.toLowerCase();
    return source.filter((row) => JSON.stringify(row).toLowerCase().includes(query));
  }, [activeTab, arrearsRows, paidRows, search]);

  const exportCurrentView = () => {
    if (activeTab === "arrears") {
      downloadCsv(
        "krib-manager-arrears.csv",
        ["Tenant", "Unit", "Balance", "Status", "Email", "Phone"],
        filteredRows.map((row) => [
          row.tenant,
          row.unit,
          row.balance,
          row.status,
          row.tenant_email || "",
          row.tenant_phone_number || "",
        ])
      );
      return;
    }

    downloadCsv(
      "krib-manager-paid-rent.csv",
      ["Tenant", "Unit", "Amount Paid", "Balance", "Transaction Time"],
      filteredRows.map((row) => [
        row.tenant?.username || row.tenant?.email || "-",
        row.lease?.unit?.unit_number || "-",
        row.amount,
        row.remaining_balance,
        formatDateTime(row.transaction_date || row.created_at),
      ])
    );
  };

  const deliverFollowUp = async (row, channel) => {
    if (channel === "email" && !row.tenant_email) return;
    if (channel === "sms" && !row.tenant_phone_number) return;

    const key = `${channel}-${row.lease_id}`;
    setSendingKey(key);
    setError("");
    setSuccess("");

    try {
      const response = await sendLeaseContactMessage({
        leaseId: row.lease_id,
        channel,
        subject: `Rent follow-up ${row.period}`,
        message: buildReminderMessage(row),
      });
      setSuccess(response?.detail || `${channel.toUpperCase()} sent.`);
    } catch (err) {
      setError(getErrorMessage(err, `Failed to send ${channel}.`));
    } finally {
      setSendingKey("");
    }
  };

  return (
    <PageLayout variant="executive" kicker="Manager Payments" title="Rent Tracking" chip={period || `Period ${summary?.period || "-"}`}>
      {error ? <p className="error">{error}</p> : null}
      {success ? <p className="success">{success}</p> : null}

      <section className="resident-hero-grid">
        <StatCard
          variant="blue"
          title="Expected"
          subtitle={`Period: ${summary?.period || period || "-"}`}
          value={formatKES(summary?.totals?.expected || 0)}
          blurValue
          isBlurred={amountsHidden}
          onToggleBlur={() => setAmountsHidden((prev) => !prev)}
        />
        <StatCard
          variant="purple"
          title="Collected"
          subtitle="Settled rent"
          value={formatKES(summary?.totals?.collected || 0)}
          ctaLabel="Review"
          onClick={() => setActiveTab("payments")}
          blurValue
          isBlurred={amountsHidden}
          onToggleBlur={() => setAmountsHidden((prev) => !prev)}
        />
        <StatCard
          variant="mint"
          title="Outstanding"
          subtitle="Open balances"
          value={formatKES(summary?.totals?.outstanding || 0)}
          ctaLabel="Action"
          onClick={() => setActiveTab("arrears")}
          blurValue
          isBlurred={amountsHidden}
          onToggleBlur={() => setAmountsHidden((prev) => !prev)}
        />
      </section>

      <SectionCard
        icon={Wallet}
        title="Payment Records"
        action={(
          <button className="resident-link-btn" type="button" onClick={exportCurrentView}>
            <Download size={16} />
            <span>Export CSV</span>
          </button>
        )}
      >
        <div className="resident-toolbar">
          <label className="resident-search">
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={`Search ${activeTab}`} />
          </label>
          <label className="resident-inline-control">
            <CalendarDays size={16} />
            <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
          </label>
        </div>

        <div className="resident-tabbar">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`resident-tab ${activeTab === tab.id ? "active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="resident-table-list">
          {filteredRows.length === 0 ? (
            <p className="subtitle">No records found for this view.</p>
          ) : activeTab === "payments" ? (
            filteredRows.map((row, index) => (
              <article className="resident-row-card" key={row.id}>
                <div className="resident-row-id">{index + 1}</div>
                <div className="resident-profile-columns landlord-payment-columns">
                  <div className="resident-profile-item">
                    <span>Tenant name</span>
                    <strong>{row.tenant?.username || row.tenant?.email || "Tenant"}</strong>
                  </div>
                  <div className="resident-profile-item">
                    <span>Unit</span>
                    <strong>{row.lease?.unit?.unit_number || "-"}</strong>
                  </div>
                  <div className="resident-profile-item">
                    <span>Amount paid</span>
                    <strong>{formatKES(row.amount || 0)}</strong>
                  </div>
                  <div className="resident-profile-item">
                    <span>Balance</span>
                    <strong>{formatKES(row.remaining_balance || 0)}</strong>
                  </div>
                  <div className="resident-profile-item">
                    <span>Time of transaction</span>
                    <strong>{formatDateTime(row.transaction_date || row.created_at)}</strong>
                  </div>
                  <div className="resident-profile-item">
                    <span>Receipt</span>
                    <button
                      className="btn btn-glass"
                      type="button"
                      onClick={() => downloadBlob(`/api/payments/receipt/${row.id}/`, `krib-receipt-${row.id}.pdf`)}
                    >
                      <Download size={16} />
                      <span>Download</span>
                    </button>
                  </div>
                </div>
              </article>
            ))
          ) : (
            filteredRows.map((row) => (
              <article className="resident-row-card" key={row.lease_id}>
                <div className="resident-row-id">{row.lease_id}</div>
                <div className="resident-profile-columns manager-action-columns">
                  <div className="resident-profile-item">
                    <span>Name</span>
                    <strong>{row.tenant || "-"}</strong>
                  </div>
                  <div className="resident-profile-item">
                    <span>Unit</span>
                    <strong>{row.unit || "-"}</strong>
                  </div>
                  <div className="resident-profile-item">
                    <span>Balance</span>
                    <strong>{formatKES(row.balance || 0)}</strong>
                  </div>
                  <div className="resident-profile-item">
                    <span>Status</span>
                    <StatusBadge status={row.status} />
                  </div>
                </div>
                <div className="resident-row-meta manager-action-meta">
                  <button
                    className="btn btn-glass"
                    type="button"
                    onClick={() => deliverFollowUp(row, "email")}
                    disabled={!row.tenant_email || sendingKey === `email-${row.lease_id}`}
                  >
                    <Mail size={16} />
                    <span>{sendingKey === `email-${row.lease_id}` ? "Sending..." : "Email"}</span>
                  </button>
                  <button
                    className="btn btn-glass"
                    type="button"
                    onClick={() => deliverFollowUp(row, "sms")}
                    disabled={!row.tenant_phone_number || sendingKey === `sms-${row.lease_id}`}
                  >
                    <MessageSquare size={16} />
                    <span>{sendingKey === `sms-${row.lease_id}` ? "Sending..." : "SMS"}</span>
                  </button>
                </div>
              </article>
            ))
          )}
        </div>
      </SectionCard>
    </PageLayout>
  );
}
