import React, { useEffect, useState } from "react";
import { CreditCard } from "lucide-react";
import api from "../services/api";
import { formatKES } from "../utils/money";
import GlassCard from "./GlassCard";

export default function TenantPayRent() {
  const [leaseId, setLeaseId] = useState(null);
  const [phone, setPhone] = useState("");
  const [amount, setAmount] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get("/api/dashboard/summary/");
        setLeaseId(res.data?.active_lease?.id || null);
        setAmount(res.data?.rent?.balance || "");
      } catch {
        setError("Failed to load active lease");
      }
    };
    load();
  }, []);

  const pay = async () => {
    setError("");
    setMessage("");
    if (!leaseId) {
      setError("No active lease found.");
      return;
    }

    try {
      await api.post("/api/payments/stk/initiate/", {
        lease_id: leaseId,
        phone_number: phone,
        amount,
      });
      setMessage("STK push initiated. Complete payment on your phone.");
      setPhone("");
    } catch (err) {
      setError(JSON.stringify(err.response?.data || "Failed to initiate payment"));
    }
  };

  return (
    <div className="dashboard-container">
      <GlassCard title="Pay Rent via STK Push">
        <div className="form-stack">
          <input placeholder="Phone (e.g., 2547...)" value={phone} onChange={(e) => setPhone(e.target.value)} />
          <input placeholder="Amount (KES)" type="number" value={amount} onChange={(e) => setAmount(e.target.value)} />
          <p className="subtitle">Amount to be charged: {formatKES(amount)}</p>
          <button className="btn btn-primary" onClick={pay} type="button">
            <CreditCard size={18} />
            <span>Initiate STK Push</span>
          </button>
        </div>
        {message ? <p className="success">{message}</p> : null}
        {error ? <p className="error">{error}</p> : null}
      </GlassCard>
    </div>
  );
}
