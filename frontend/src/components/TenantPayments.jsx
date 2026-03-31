import React, { useEffect, useState } from "react";
import { ReceiptText } from "lucide-react";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { downloadBlob } from "../utils/files";
import { formatDateTime, formatKES } from "../utils/format";
import GlassCard from "./GlassCard";
import StatusBadge from "./StatusBadge";

export default function TenantPayments() {
  const [payments, setPayments] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get("/api/payments/");
        setPayments(res.data || []);
      } catch (err) {
        setError(getErrorMessage(err, "Failed to load payment history."));
      }
    };
    load();
  }, []);

  return (
    <div className="dashboard-container">
      {error ? <p className="error">{error}</p> : null}
      <GlassCard title="Payment History" actions={<span className="subtitle">Recent rent activity</span>}>
        {payments.length === 0 ? (
          <p>No payment history found.</p>
        ) : (
          <div className="stack-list">
            {payments.map((payment) => (
              <article className="stack-item" key={payment.id}>
                <div className="stack-item-main">
                  <div className="stack-item-icon"><ReceiptText size={18} /></div>
                  <div>
                    <h4>{formatKES(payment.amount)}</h4>
                    <p className="subtitle">{formatDateTime(payment.transaction_date || payment.created_at)}</p>
                    <p className="subtitle">Receipt: {payment.mpesa_receipt || payment.checkout_request_id || payment.id}</p>
                  </div>
                </div>
                <div className="stack-item-side">
                  <StatusBadge status={payment.status} />
                  {payment.status === "success" ? (
                    <button className="btn btn-glass" type="button" onClick={() => downloadBlob(`/api/payments/receipt/${payment.id}/`, `krib-receipt-${payment.id}.pdf`)}>
                      Download
                    </button>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
