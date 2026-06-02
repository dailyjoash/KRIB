import React, { useEffect, useMemo, useState } from "react";
import { CreditCard, Loader2, RefreshCw } from "lucide-react";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { formatDateTime, formatKES } from "../utils/format";
import StatusBadge from "./StatusBadge";
import { SectionCard } from "./ui";

const STATUS_LABEL = {
  pending: "Pending",
  paid: "Paid",
  free_tier: "Free tier",
  overdue: "Overdue",
  waived: "Waived",
};

const formatPeriod = (period) => {
  if (!period || typeof period !== "string" || !period.includes("-")) return period || "-";
  const [year, month] = period.split("-");
  const date = new Date(Number(year), Number(month) - 1, 1);
  if (Number.isNaN(date.getTime())) return period;
  return date.toLocaleDateString("en-KE", { month: "long", year: "numeric" });
};

export default function LandlordSubscriptionCard() {
  const [current, setCurrent] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [phone, setPhone] = useState("");
  const [paying, setPaying] = useState(false);
  const [success, setSuccess] = useState("");

  const load = async () => {
    setError("");
    setSuccess("");
    setLoading(true);
    try {
      const [currentRes, historyRes] = await Promise.all([
        api.get("/api/landlord/subscription/current/").catch((err) => {
          if (err?.response?.status === 404) return { data: null };
          throw err;
        }),
        api.get("/api/landlord/subscription/invoices/"),
      ]);
      setCurrent(currentRes?.data || null);
      setHistory(historyRes?.data || []);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load subscription invoices."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handlePay = async () => {
    if (!current || !current.id) return;
    const trimmed = phone.trim();
    if (!trimmed) {
      setError("Enter the M-Pesa phone number to receive the STK push.");
      return;
    }
    setError("");
    setSuccess("");
    setPaying(true);
    try {
      const response = await api.post(
        `/api/landlord/subscription/invoices/${current.id}/pay/`,
        { phone_number: trimmed },
      );
      setSuccess(
        response.data?.detail ||
          "STK push initiated. Approve the prompt on your M-Pesa-registered phone to complete payment.",
      );
      if (response.data?.invoice) {
        setCurrent(response.data.invoice);
      }
    } catch (err) {
      setError(getErrorMessage(err, "Could not start the STK push. Please try again."));
    } finally {
      setPaying(false);
    }
  };

  const headerAction = useMemo(
    () => (
      <button
        type="button"
        className="resident-ghost-btn"
        onClick={load}
        disabled={loading}
        style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
      >
        <RefreshCw size={14} /> Refresh
      </button>
    ),
    [loading],
  );

  return (
    <SectionCard
      icon={CreditCard}
      title="KRIB subscription"
      action={headerAction}
    >
      {loading ? (
        <p style={{ color: "#6b7280" }}>
          <Loader2 size={14} className="resident-spin" /> Loading subscription invoices…
        </p>
      ) : null}

      {error ? (
        <p style={{ color: "#b91c1c", marginTop: 8 }}>{error}</p>
      ) : null}
      {success ? (
        <p style={{ color: "#047857", marginTop: 8 }}>{success}</p>
      ) : null}

      {!loading && !current ? (
        <p style={{ color: "#6b7280" }}>
          No subscription invoice has been generated for this period yet. KRIB will
          surface one as soon as the monthly billing cycle runs.
        </p>
      ) : null}

      {current ? (
        <div className="resident-subscription-current">
          <div className="resident-row" style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "baseline" }}>
            <div>
              <p className="resident-kicker">Billing period</p>
              <strong>{formatPeriod(current.period)}</strong>
            </div>
            <div>
              <p className="resident-kicker">Billable units</p>
              <strong>{current.billable_units_count}</strong>
            </div>
            <div>
              <p className="resident-kicker">Amount</p>
              <strong>{formatKES(current.amount)}</strong>
            </div>
            <div>
              <p className="resident-kicker">Status</p>
              <StatusBadge status={(STATUS_LABEL[current.status] || current.status || "").toUpperCase()} />
            </div>
            {current.due_at ? (
              <div>
                <p className="resident-kicker">Due by</p>
                <strong>{formatDateTime(current.due_at)}</strong>
              </div>
            ) : null}
          </div>

          {current.status === "free_tier" ? (
            <p style={{ marginTop: 12, color: "#0f766e" }}>
              Free tier — {current.billable_units_count} unit
              {current.billable_units_count === 1 ? "" : "s"} under the
              {" "}
              {current.free_tier_threshold}-unit threshold. No payment required.
            </p>
          ) : null}

          {(current.status === "pending" || current.status === "overdue") && current.amount > 0 ? (
            <div style={{ marginTop: 12, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <input
                type="tel"
                value={phone}
                onChange={(event) => setPhone(event.target.value)}
                placeholder="07XX XXX XXX"
                className="resident-input"
                style={{ maxWidth: 200 }}
              />
              <button
                type="button"
                className="resident-primary-btn"
                onClick={handlePay}
                disabled={paying}
              >
                {paying ? "Starting STK push…" : "Pay now"}
              </button>
            </div>
          ) : null}

          {current.line_items?.length ? (
            <details style={{ marginTop: 16 }}>
              <summary style={{ cursor: "pointer", color: "#1f2937" }}>
                Show the {current.line_items.length} billed unit
                {current.line_items.length === 1 ? "" : "s"}
              </summary>
              <ul style={{ marginTop: 8 }}>
                {current.line_items.map((item) => (
                  <li key={item.id}>{item.unit_label || `Unit #${item.unit}`}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>
      ) : null}

      {history.length ? (
        <div style={{ marginTop: 24 }}>
          <p className="resident-kicker">Invoice history</p>
          <table className="resident-table">
            <thead>
              <tr>
                <th>Period</th>
                <th>Units</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Paid via</th>
                <th>Generated</th>
              </tr>
            </thead>
            <tbody>
              {history.map((invoice) => (
                <tr key={invoice.id}>
                  <td>{formatPeriod(invoice.period)}</td>
                  <td>{invoice.billable_units_count}</td>
                  <td>{formatKES(invoice.amount)}</td>
                  <td>
                    <StatusBadge
                      status={(STATUS_LABEL[invoice.status] || invoice.status || "").toUpperCase()}
                    />
                  </td>
                  <td>{invoice.paid_via || "-"}</td>
                  <td>{formatDateTime(invoice.generated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </SectionCard>
  );
}
