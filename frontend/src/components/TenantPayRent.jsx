import React, { useEffect, useMemo, useState } from "react";
import { CreditCard, Download, Receipt, Smartphone } from "lucide-react";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { downloadBlob } from "../utils/files";
import { formatKES } from "../utils/format";
import StatusBadge from "./StatusBadge";

export default function TenantPayRent() {
  const [leaseId, setLeaseId] = useState(null);
  const [phone, setPhone] = useState("");
  const [amount, setAmount] = useState("");
  const [rentStatus, setRentStatus] = useState({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [checkoutId, setCheckoutId] = useState("");
  const [receiptPaymentId, setReceiptPaymentId] = useState(null);

  const resetFeedback = () => {
    setError("");
    setMessage("");
    setReceiptPaymentId(null);
    setCheckoutId("");
  };

  useEffect(() => {
    const load = async () => {
      try {
        const [summaryRes, meRes] = await Promise.all([
          api.get("/api/dashboard/summary/"),
          api.get("/api/me/"),
        ]);
        setLeaseId(summaryRes.data?.active_lease?.id || null);
        setAmount(String(summaryRes.data?.rent?.balance ?? ""));
        setRentStatus(summaryRes.data?.rent || {});
        setPhone(meRes.data?.phone_number || "");
      } catch (err) {
        setError(getErrorMessage(err, "Failed to load active lease."));
      }
    };
    load();
  }, []);

  useEffect(() => {
    if (!checkoutId) return undefined;
    let attempts = 0;
    const timer = window.setInterval(async () => {
      attempts += 1;
      try {
        const res = await api.get(`/api/payments/mpesa/status/${checkoutId}/`);
        const status = res.data?.status;
        const payment = res.data?.payment;
        if (status === "success") {
          try {
            const summaryRes = await api.get("/api/dashboard/summary/");
            setLeaseId(summaryRes.data?.active_lease?.id || null);
            setAmount(String(summaryRes.data?.rent?.balance ?? ""));
            setRentStatus(summaryRes.data?.rent || {});
          } catch (refreshErr) {
            setError(getErrorMessage(refreshErr, "Payment confirmed, but the balance could not be refreshed."));
          }
          setMessage("Payment confirmed successfully.");
          setReceiptPaymentId(payment?.id || null);
          window.clearInterval(timer);
        } else if (status === "failed") {
          setError("Payment failed. Please try again.");
          window.clearInterval(timer);
        } else if (attempts >= 20) {
          setMessage("Payment is still pending. Complete the prompt on your phone and refresh if needed.");
          window.clearInterval(timer);
        }
      } catch (err) {
        if (attempts >= 20) {
          setError(getErrorMessage(err, "Unable to confirm payment status."));
          window.clearInterval(timer);
        }
      }
    }, 3000);

    return () => window.clearInterval(timer);
  }, [checkoutId]);

  const handleMpesaPay = async () => {
    resetFeedback();
    if (!leaseId) {
      setError("No active lease found.");
      return;
    }

    setLoading(true);
    try {
      const res = await api.post("/api/payments/mpesa/initiate/", {
        lease_id: leaseId,
        phone_number: phone,
        amount,
      });
      const nextCheckoutId = res.data?.payment?.checkout_request_id || "";
      setCheckoutId(nextCheckoutId);
      setMessage("STK push initiated. Complete payment on your phone.");
    } catch (err) {
      setError(getErrorMessage(err, "Payment failed. Please try again."));
    } finally {
      setLoading(false);
    }
  };

  const receiptLabel = useMemo(() => {
    if (!receiptPaymentId) return null;
    return `Receipt #${receiptPaymentId}`;
  }, [receiptPaymentId]);

  return (
    <div className="resident-page">
      <section className="resident-section-card">
        <div className="resident-section-head">
          <div className="resident-title-row">
            <CreditCard size={18} />
            <h2>Pay Rent</h2>
          </div>
          <StatusBadge status={rentStatus.status || "pending"} />
        </div>

        <div className="resident-summary-card compact resident-summary-card--rent">
          <div className="resident-summary-main">
            <div className="resident-summary-thumb">
              <Receipt size={24} />
            </div>
            <div>
              <h3>Current Amount Due</h3>
              <p>{rentStatus.period || "Current billing period"}</p>
            </div>
          </div>
          <div className="resident-summary-meta">
            <strong>{formatKES(amount || 0)}</strong>
          </div>
        </div>

        <div className="payment-panel">
          <label className="resident-field">
            <span>M-Pesa phone number</span>
            <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="2547..." />
          </label>
          <label className="resident-field">
            <span>Amount to pay</span>
            <input
              type="number"
              min="0.01"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="Enter amount"
            />
          </label>
          <button className="resident-primary-btn" type="button" onClick={handleMpesaPay} disabled={loading}>
            <Smartphone size={16} />
            <span>{loading ? "Sending STK..." : "Pay now"}</span>
          </button>
        </div>

        {message ? <p className="success">{message}</p> : null}
        {error ? <p className="error">{error}</p> : null}
        {receiptPaymentId ? (
          <button className="resident-link-btn resident-inline-download" type="button" onClick={() => downloadBlob(`/api/payments/receipt/${receiptPaymentId}/`, `krib-receipt-${receiptPaymentId}.pdf`)}>
            <Download size={16} />
            <span>{receiptLabel || "Download receipt"}</span>
          </button>
        ) : null}
      </section>
    </div>
  );
}
