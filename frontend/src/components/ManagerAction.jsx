import React, { useEffect, useMemo, useState } from "react";
import api from "../services/api";
import GlassCard from "./GlassCard";
import StatusBadge from "./StatusBadge";
import { formatKES } from "../utils/format";

const templates = {
  friendly: "Hi {tenant}, friendly reminder that your rent balance for {period} is {balance} for {unit}. Kindly clear it at your earliest convenience. Thank you.",
  professional: "Dear {tenant}, this is a polite reminder that rent for {unit} for {period} has an outstanding balance of {balance}. Kindly arrange payment.",
  firm: "Hello {tenant}. Your rent for {unit} in {period} is outstanding at {balance}. Please settle promptly to avoid penalties.",
  final_notice: "FINAL NOTICE: Your rent balance of {balance} for {unit} ({period}) remains unpaid. Please clear immediately.",
  short: "Reminder: {unit} rent balance for {period} is {balance}. Please pay today.",
};

const applyTemplate = (template, row) => template
  .replaceAll("{tenant}", row.tenant || "Tenant")
  .replaceAll("{period}", row.period)
  .replaceAll("{balance}", formatKES(row.balance))
  .replaceAll("{unit}", row.unit || "-");

export default function ManagerAction() {
  const [summary, setSummary] = useState(null);
  const [period, setPeriod] = useState("");
  const [templateKey, setTemplateKey] = useState("friendly");
  const [customMessages, setCustomMessages] = useState({});

  useEffect(() => {
    const load = async () => {
      const res = await api.get("/api/dashboard/summary/", { params: period ? { period } : {} });
      setSummary(res.data);
      if (!period && res.data?.period) {
        setPeriod(res.data.period);
      }
    };
    load();
  }, [period]);

  const rows = useMemo(() => {
    if (!summary?.lists) return [];
    const statuses = ["UNPAID", "PARTIAL", "OVERDUE"];
    return statuses.flatMap((status) =>
      (summary.lists?.[status] || []).map((row) => ({ ...row, status, period: summary.period })),
    );
  }, [summary]);

  const messages = useMemo(() => {
    const next = {};
    rows.forEach((row) => {
      next[row.lease_id] = customMessages[row.lease_id] || applyTemplate(templates[templateKey], row);
    });
    return next;
  }, [rows, templateKey, customMessages]);

  const setMessage = (leaseId, message) => setCustomMessages((prev) => ({ ...prev, [leaseId]: message }));

  const copyMessage = async (message) => {
    if (navigator.clipboard) await navigator.clipboard.writeText(message);
  };

  if (!summary) {
    return <div className="loading">Loading actions...</div>;
  }

  return (
    <div className="dashboard-container">
      <GlassCard title="Follow-up List" actions={<span className="subtitle">UNPAID / PARTIAL / OVERDUE</span>}>
        <div className="followup-toolbar">
          <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
          <select value={templateKey} onChange={(e) => setTemplateKey(e.target.value)}>
            <option value="friendly">Friendly</option>
            <option value="professional">Professional</option>
            <option value="firm">Firm</option>
            <option value="final_notice">Final Notice</option>
            <option value="short">Short</option>
          </select>
        </div>

        <table>
          <thead>
            <tr>
              <th>Tenant</th>
              <th>Unit</th>
              <th>Status</th>
              <th>Balance due</th>
              <th>Message</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const message = messages[row.lease_id] || "";
              const smsUri = `sms:?body=${encodeURIComponent(message)}`;
              const mailto = `mailto:?subject=${encodeURIComponent(`Rent follow-up ${row.period}`)}&body=${encodeURIComponent(message)}`;
              return (
                <tr key={`${row.lease_id}-${row.status}`}>
                  <td>{row.tenant || "-"}</td>
                  <td>{row.unit || "-"}</td>
                  <td><StatusBadge status={row.status} /></td>
                  <td>{formatKES(row.balance)}</td>
                  <td>
                    <textarea value={message} onChange={(e) => setMessage(row.lease_id, e.target.value)} rows={3} />
                  </td>
                  <td>
                    <div className="followup-actions">
                      <a className="btn btn-glass" href={mailto}>Email</a>
                      <a className="btn btn-glass" href={smsUri}>Text</a>
                      <button type="button" className="btn" onClick={() => copyMessage(message)}>Copy message</button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </GlassCard>
    </div>
  );
}
