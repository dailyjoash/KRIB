import React, { useEffect, useMemo, useState } from "react";
import { Copy, CreditCard, Download, Receipt, Send, Smartphone } from "lucide-react";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { downloadBlob } from "../utils/files";
import { formatKES } from "../utils/format";
import StatusBadge from "./StatusBadge";

const toDateTimeLocal = (value = new Date()) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 16);
};

export default function TenantPayRent() {
  const [leaseId, setLeaseId] = useState(null);
  const [phone, setPhone] = useState("");
  const [amount, setAmount] = useState("");
  const [rentStatus, setRentStatus] = useState({});
  const [collectionMode, setCollectionMode] = useState("custody_legacy");
  const [directInstructions, setDirectInstructions] = useState(null);
  const [directPayments, setDirectPayments] = useState([]);
  const [confirmationForm, setConfirmationForm] = useState({
    transaction_code: "",
    amount: "",
    transaction_date: toDateTimeLocal(),
    phone_number: "",
  });
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
        const activeLease = summaryRes.data?.active_lease || {};
        const instructions = summaryRes.data?.direct_pay_instructions || activeLease?.direct_pay_instructions || null;
        const nextBalance = String(summaryRes.data?.rent?.balance ?? "");
        const nextPhone = meRes.data?.phone_number || "";
        setLeaseId(activeLease?.id || null);
        setAmount(nextBalance);
        setRentStatus(summaryRes.data?.rent || {});
        setPhone(nextPhone);
        setCollectionMode(activeLease?.collection_mode || instructions?.collection_mode || "custody_legacy");
        setDirectInstructions(instructions);
        setDirectPayments(summaryRes.data?.direct_payments || []);
        setConfirmationForm((prev) => ({
          ...prev,
          amount: nextBalance,
          phone_number: nextPhone,
        }));
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

  const handleCopy = async (label, value) => {
    resetFeedback();
    try {
      await navigator.clipboard.writeText(String(value || ""));
      setMessage(`${label} copied.`);
    } catch {
      setError(`Could not copy ${label.toLowerCase()}.`);
    }
  };

  const refreshDirectSummary = async () => {
    const summaryRes = await api.get("/api/dashboard/summary/");
    const activeLease = summaryRes.data?.active_lease || {};
    const instructions = summaryRes.data?.direct_pay_instructions || activeLease?.direct_pay_instructions || null;
    const nextBalance = String(summaryRes.data?.rent?.balance ?? "");
    setRentStatus(summaryRes.data?.rent || {});
    setAmount(nextBalance);
    setDirectInstructions(instructions);
    setDirectPayments(summaryRes.data?.direct_payments || []);
    setConfirmationForm((prev) => ({
      ...prev,
      transaction_code: "",
      amount: nextBalance,
      transaction_date: toDateTimeLocal(),
    }));
  };

  const handleManualConfirmation = async (event) => {
    event.preventDefault();
    resetFeedback();
    if (!leaseId) {
      setError("No active lease found.");
      return;
    }

    setLoading(true);
    try {
      await api.post("/api/payments/direct/", {
        lease_id: leaseId,
        transaction_code: confirmationForm.transaction_code,
        amount: confirmationForm.amount,
        transaction_date: new Date(confirmationForm.transaction_date).toISOString(),
        phone_number: confirmationForm.phone_number,
      });
      await refreshDirectSummary();
      setMessage("Payment confirmation submitted for landlord review.");
    } catch (err) {
      setError(getErrorMessage(err, "Failed to submit payment confirmation."));
    } finally {
      setLoading(false);
    }
  };

  const latestDirectStatus = useMemo(() => directPayments[0]?.status || rentStatus.status || "unpaid", [directPayments, rentStatus.status]);

  const receiptLabel = useMemo(() => {
    if (!receiptPaymentId) return null;
    return `Receipt #${receiptPaymentId}`;
  }, [receiptPaymentId]);

  const isDirectPaybill = collectionMode === "direct_paybill";

  return (
    <div className="resident-page">
      <section className="resident-section-card">
        <div className="resident-section-head">
          <div className="resident-title-row">
            <CreditCard size={18} />
            <h2>Pay Rent</h2>
          </div>
          <StatusBadge status={isDirectPaybill ? latestDirectStatus : rentStatus.status || "pending"} />
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

        {isDirectPaybill ? (
          <>
            <div className="payment-panel">
              <label className="resident-field">
                <span>Paybill</span>
                <input value={directInstructions?.paybill_number || ""} readOnly />
              </label>
              <button className="resident-link-btn" type="button" onClick={() => handleCopy("Paybill", directInstructions?.paybill_number)} disabled={!directInstructions?.paybill_number}>
                <Copy size={16} />
                <span>Copy</span>
              </button>
              <label className="resident-field">
                <span>Account / reference</span>
                <input value={directInstructions?.account_reference || ""} readOnly />
              </label>
              <button className="resident-link-btn" type="button" onClick={() => handleCopy("Account reference", directInstructions?.account_reference)} disabled={!directInstructions?.account_reference}>
                <Copy size={16} />
                <span>Copy</span>
              </button>
              <label className="resident-field">
                <span>Amount due</span>
                <input value={formatKES(directInstructions?.amount ?? amount ?? 0)} readOnly />
              </label>
              <label className="resident-field">
                <span>Period</span>
                <input value={directInstructions?.period || rentStatus.period || ""} readOnly />
              </label>
            </div>

            {!directInstructions?.paybill_number ? (
              <p className="error">Your landlord has not completed Paybill setup yet. Contact the landlord before paying.</p>
            ) : null}

            <form className="payment-panel" onSubmit={handleManualConfirmation}>
              <label className="resident-field">
                <span>M-Pesa transaction code</span>
                <input
                  value={confirmationForm.transaction_code}
                  onChange={(e) => setConfirmationForm({ ...confirmationForm, transaction_code: e.target.value })}
                  required
                />
              </label>
              <label className="resident-field">
                <span>Amount paid</span>
                <input
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={confirmationForm.amount}
                  onChange={(e) => setConfirmationForm({ ...confirmationForm, amount: e.target.value })}
                  required
                />
              </label>
              <label className="resident-field">
                <span>Date and time paid</span>
                <input
                  type="datetime-local"
                  value={confirmationForm.transaction_date}
                  onChange={(e) => setConfirmationForm({ ...confirmationForm, transaction_date: e.target.value })}
                  required
                />
              </label>
              <label className="resident-field">
                <span>Phone used</span>
                <input
                  value={confirmationForm.phone_number}
                  onChange={(e) => setConfirmationForm({ ...confirmationForm, phone_number: e.target.value })}
                  required
                />
              </label>
              <button className="resident-primary-btn" type="submit" disabled={loading || !directInstructions?.paybill_number}>
                <Send size={16} />
                <span>{loading ? "Submitting..." : "Submit confirmation"}</span>
              </button>
            </form>

            {directPayments.length ? (
              <div className="resident-table-list">
                {directPayments.slice(0, 4).map((payment) => (
                  <article className="resident-row-card" key={payment.id}>
                    <div className="resident-row-main">
                      <h4>{payment.transaction_code}</h4>
                      <p>{formatKES(payment.amount)} / {payment.collection_label || "direct landlord-collected"}</p>
                    </div>
                    <div className="resident-row-meta">
                      <StatusBadge status={payment.status} />
                    </div>
                  </article>
                ))}
              </div>
            ) : null}
          </>
        ) : (
          <div className="payment-panel">
            <label className="resident-field">
              <span>M-Pesa phone number</span>
              <input value={phone} onChange={(e) => setPhone(e.target.value)} />
            </label>
            <label className="resident-field">
              <span>Amount to pay</span>
              <input
                type="number"
                min="0.01"
                step="0.01"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </label>
            <button className="resident-primary-btn" type="button" onClick={handleMpesaPay} disabled={loading}>
              <Smartphone size={16} />
              <span>{loading ? "Sending STK..." : "Pay now"}</span>
            </button>
          </div>
        )}

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
