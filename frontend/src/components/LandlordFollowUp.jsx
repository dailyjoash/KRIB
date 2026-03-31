import React, { useEffect, useMemo, useState } from "react";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import GlassCard from "./GlassCard";
import StatusBadge from "./StatusBadge";
import { formatKES } from "../utils/format";
import { sendLeaseContactMessage } from "../utils/leaseContact";

const templates = {
  friendly: "Hi {tenant}, friendly reminder that your rent balance for {period} is {balance} for {unit}. Kindly clear it at your earliest convenience. Thank you.",
  firm: "Hello {tenant}. Your rent for {unit} in {period} is outstanding at {balance}. Please settle promptly to avoid penalties.",
  final: "FINAL NOTICE: Your rent balance of {balance} for {unit} ({period}) remains unpaid. Please clear immediately.",
  professional: "Dear {tenant}, this is a polite reminder that rent for {unit} for {period} has an outstanding balance of {balance}. Kindly arrange payment.",
  one_liner: "Reminder: {unit} rent balance for {period} is {balance}. Please pay today.",
};

const applyTemplate = (template, row) => template
  .replaceAll("{tenant}", row.tenant?.username || row.tenant?.email || "Tenant")
  .replaceAll("{period}", row.period)
  .replaceAll("{balance}", formatKES(row.balance))
  .replaceAll("{unit}", `${row.unit?.property_name || "-"} / ${row.unit?.unit_number || "-"}`);

export default function LandlordFollowUp() {
  const [rows, setRows] = useState([]);
  const [period, setPeriod] = useState("");
  const [templateKey, setTemplateKey] = useState("friendly");
  const [customMessages, setCustomMessages] = useState({});
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [sendingKey, setSendingKey] = useState("");

  useEffect(() => {
    const load = async () => {
      const res = await api.get("/api/landlord/followups/", { params: period ? { period } : {} });
      setRows(res.data);
    };
    load();
  }, [period]);

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

  const deliverFollowUp = async (row, channel, message) => {
    const recipientMissing = channel === "email" ? !row.tenant?.email : !row.tenant?.phone_number;
    if (recipientMissing) return;

    const key = `${channel}-${row.lease_id}`;
    setSendingKey(key);
    setError("");
    setSuccess("");
    try {
      const response = await sendLeaseContactMessage({
        leaseId: row.lease_id,
        channel,
        subject: `Rent follow-up ${row.period}`,
        message,
      });
      setSuccess(response?.detail || `${channel.toUpperCase()} sent.`);
    } catch (err) {
      setError(getErrorMessage(err, `Failed to send ${channel}.`));
    } finally {
      setSendingKey("");
    }
  };

  return (
    <div className="dashboard-container">
      <GlassCard title="Follow-up" actions={<span className="subtitle">Current unpaid or partial balances</span>}>
        {error ? <p className="error">{error}</p> : null}
        {success ? <p className="success">{success}</p> : null}
        <div className="followup-toolbar">
          <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
          <select value={templateKey} onChange={(e) => setTemplateKey(e.target.value)}>
            <option value="friendly">Friendly reminder</option>
            <option value="firm">Firm reminder</option>
            <option value="final">Final notice</option>
            <option value="professional">Polite professional</option>
            <option value="one_liner">One-liner</option>
          </select>
        </div>

        <table className="mobile-table">
          <thead>
            <tr>
              <th>Tenant</th>
              <th>Unit</th>
              <th>Balance due</th>
              <th>Status</th>
              <th>Message</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const message = messages[row.lease_id] || "";
              return (
                <tr key={row.lease_id}>
                  <td data-label="Tenant">{row.tenant?.username || row.tenant?.email || "-"}</td>
                  <td data-label="Unit">{row.unit ? `${row.unit.property_name} / ${row.unit.unit_number}` : "-"}</td>
                  <td data-label="Balance Due">{formatKES(row.balance)}</td>
                  <td data-label="Status"><StatusBadge status={row.status} /></td>
                  <td data-label="Message">
                    <textarea value={message} onChange={(e) => setMessage(row.lease_id, e.target.value)} rows={3} />
                  </td>
                  <td data-label="Actions">
                    <div className="followup-actions">
                      <button
                        type="button"
                        className="btn btn-glass"
                        onClick={() => deliverFollowUp(row, "sms", message)}
                        disabled={!row.tenant?.phone_number || sendingKey === `sms-${row.lease_id}`}
                      >
                        {sendingKey === `sms-${row.lease_id}` ? "Sending..." : "Text"}
                      </button>
                      <button
                        type="button"
                        className="btn btn-glass"
                        onClick={() => deliverFollowUp(row, "email", message)}
                        disabled={!row.tenant?.email || sendingKey === `email-${row.lease_id}`}
                      >
                        {sendingKey === `email-${row.lease_id}` ? "Sending..." : "Email"}
                      </button>
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
