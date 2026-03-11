import React, { useEffect, useMemo, useState } from "react";
import api from "../services/api";
import GlassCard from "./GlassCard";
import StatusBadge from "./StatusBadge";
import { formatKES } from "../utils/format";

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

  return (
    <div className="dashboard-container">
      <GlassCard title="Follow-up" actions={<span className="subtitle">Current unpaid or partial balances</span>}>
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
              const smsUri = `sms:${row.tenant?.phone_number || ""}?body=${encodeURIComponent(message)}`;
              const email = row.tenant?.email || "";
              const mailto = `mailto:${email}?subject=${encodeURIComponent(`Rent follow-up ${row.period}`)}&body=${encodeURIComponent(message)}`;
              return (
                <tr key={row.lease_id}>
                  <td>{row.tenant?.username || row.tenant?.email || "-"}</td>
                  <td>{row.unit ? `${row.unit.property_name} / ${row.unit.unit_number}` : "-"}</td>
                  <td><StatusBadge status={row.status} /></td>
                  <td>{formatKES(row.balance)}</td>
                  <td>
                    <textarea value={message} onChange={(e) => setMessage(row.lease_id, e.target.value)} rows={3} />
                  </td>
                  <td>
                    <div className="followup-actions">
                      <a className="btn btn-glass" href={smsUri}>Text</a>
                      <a className="btn btn-glass" href={mailto}>Email</a>
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
