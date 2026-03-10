import React, { useEffect, useState } from "react";
import api from "../services/api";
import { formatKES } from "../utils/format";
import GlassCard from "./GlassCard";
import StatusBadge from "./StatusBadge";

export default function TenantPayments() {
  const [payments, setPayments] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get("/api/dashboard/summary/");
        setPayments(res.data?.payments || []);
      } catch {
        setError("Failed to load payment history");
      }
    };
    load();
  }, []);

  return (
    <div className="dashboard-container">
      {error ? <p className="error">{error}</p> : null}
      <GlassCard title="Payment History">
        {payments.length === 0 ? (
          <p>No payment history found.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Amount</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {payments.map((payment) => (
                <tr key={payment.id}>
                  <td>{payment.created_at ? new Date(payment.created_at).toLocaleDateString() : "-"}</td>
                  <td>{formatKES(payment.amount)}</td>
                  <td><StatusBadge status={payment.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </GlassCard>
    </div>
  );
}
