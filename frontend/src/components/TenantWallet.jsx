import React, { useEffect, useState } from "react";
import { ArrowDownToLine } from "lucide-react";
import api from "../services/api";
import { formatKES } from "../utils/money";
import GlassCard from "./GlassCard";
import StatusBadge from "./StatusBadge";

export default function TenantWallet() {
  const [wallet, setWallet] = useState(null);
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const res = await api.get("/api/wallet/");
      setWallet(res.data);
    } catch {
      setError("Failed to load wallet");
      setWallet({ wallet_available: 0, wallet_locked: 0, recent: [] });
    }
  };

  useEffect(() => {
    load();
  }, []);

  const requestWithdrawal = async () => {
    setError("");
    try {
      await api.post("/api/wallet/withdraw/", { amount });
      setAmount("");
      await load();
    } catch (err) {
      setError(JSON.stringify(err.response?.data || "Failed to request withdrawal"));
    }
  };

  if (!wallet) return <p className="loading">Loading...</p>;

  return (
    <div className="dashboard-container">
      {error ? <p className="error">{error}</p> : null}
      <GlassCard title="Wallet Balances">
        <div className="detail-grid">
          <p>Available: <strong>{formatKES(wallet.wallet_available)}</strong></p>
          <p>Locked: <strong>{formatKES(wallet.wallet_locked)}</strong></p>
        </div>
        <p className="subtitle">Available after 7 days before withdrawal is processed.</p>
      </GlassCard>

      <GlassCard title="Request Withdrawal">
        <div className="form-stack">
          <input placeholder="Withdraw amount (KES)" type="number" value={amount} onChange={(e) => setAmount(e.target.value)} />
          <button className="btn btn-primary" type="button" onClick={requestWithdrawal}>
            <ArrowDownToLine size={18} />
            <span>Request Withdrawal</span>
          </button>
        </div>
      </GlassCard>

      <GlassCard title="Recent Wallet Transactions">
        {wallet.recent?.length === 0 ? (
          <p>No wallet transactions yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Type</th>
                <th>Amount</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {wallet.recent?.map((row) => (
                <tr key={row.id}>
                  <td>{row.kind}</td>
                  <td>{formatKES(row.amount)}</td>
                  <td><StatusBadge status={row.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </GlassCard>
    </div>
  );
}
