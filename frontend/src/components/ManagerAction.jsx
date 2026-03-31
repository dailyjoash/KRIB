import React, { useEffect, useMemo, useState } from "react";
import { Mail, MessageSquare } from "lucide-react";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { formatKES } from "../utils/format";
import { sendLeaseContactMessage } from "../utils/leaseContact";
import StatusBadge from "./StatusBadge";
import { PageLayout, SectionCard } from "./ui";

const buildReminderMessage = (row) => {
  const label = row.status === "PARTIAL" ? "partially paid" : "unpaid";
  return `Hello ${row.tenant || "Tenant"}, your rent for ${row.unit || "-"} for ${row.period} is currently ${label}. Please clear the outstanding balance of ${formatKES(row.balance)} as soon as possible.`;
};

export default function ManagerAction() {
  const [summary, setSummary] = useState(null);
  const [period, setPeriod] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [sendingKey, setSendingKey] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get("/api/dashboard/summary/", { params: period ? { period } : {} });
        setSummary(res.data);
        if (!period && res.data?.period) {
          setPeriod(res.data.period);
        }
      } catch (err) {
        setError(getErrorMessage(err, "Failed to load follow-up actions."));
      }
    };
    load();
  }, [period]);

  const rows = useMemo(() => {
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

  if (!summary) {
    return <div className="loading">Loading actions...</div>;
  }

  return (
    <PageLayout variant="executive" kicker="Manager Follow-Up" title="Action Queue" chip={`${rows.length} tenants need attention`}>
      {error ? <p className="error">{error}</p> : null}
      {success ? <p className="success">{success}</p> : null}

      <SectionCard
        icon={MessageSquare}
        title="Tenants Requiring Follow-Up"
        action={<input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />}
      >
        <div className="resident-table-list">
          {rows.length === 0 ? (
            <p className="resident-helper-text">No unpaid or partially paid tenants right now.</p>
          ) : (
            rows.map((row, index) => (
              <article className="resident-row-card" key={row.lease_id}>
                <div className="resident-row-id">{index + 1}</div>
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
