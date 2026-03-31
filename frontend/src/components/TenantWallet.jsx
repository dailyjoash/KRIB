import React, { useEffect, useState } from "react";
import { ArrowDownToLine, WalletCards } from "lucide-react";
import api from "../services/api";
import { formatDateTime, formatKES } from "../utils/format";
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
      setWallet({ wallet_available: 0, wallet_locked: 0, recent: [], pending_withdrawals: [] });
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
      <GlassCard title="Wallet Balances" actions={<WalletCards size={16} />}>
        <div className="stack-list compact">
          <article className="stack-item">
            <div className="stack-item-main">
              <div className="stack-item-icon"><WalletCards size={18} /></div>
              <div>
                <h4>Available</h4>
                <p className="subtitle">{formatKES(wallet.wallet_available)}</p>
              </div>
            </div>
          </article>
          <article className="stack-item">
            <div className="stack-item-main">
              <div className="stack-item-icon"><ArrowDownToLine size={18} /></div>
              <div>
                <h4>Locked</h4>
                <p className="subtitle">{formatKES(wallet.wallet_locked)}</p>
              </div>
            </div>
          </article>
        </div>
        <p className="subtitle">Wallet credits unlock after the configured hold period before withdrawal can be requested.</p>
      </GlassCard>

      <GlassCard title="Request Withdrawal" actions={<span className="subtitle">Tenant wallet payout request</span>}>
        <div className="form-stack">
          <input placeholder="Withdraw amount (KES)" type="number" value={amount} onChange={(e) => setAmount(e.target.value)} />
          <button className="btn btn-primary" type="button" onClick={requestWithdrawal}>
            <ArrowDownToLine size={18} />
            <span>Request Withdrawal</span>
          </button>
        </div>
      </GlassCard>

      <GlassCard title="Recent Wallet Activity" actions={<span className="subtitle">{wallet.pending_withdrawals?.length || 0} pending withdrawals</span>}>
        {wallet.recent?.length === 0 ? (
          <p>No wallet transactions yet.</p>
        ) : (
          <div className="stack-list">
            {wallet.recent?.map((row) => (
              <article className="stack-item" key={row.id}>
                <div className="stack-item-main">
                  <div className="stack-item-icon"><WalletCards size={18} /></div>
                  <div>
                    <h4>{row.kind.replaceAll("_", " ")}</h4>
                    <p className="subtitle">{formatKES(row.amount)}</p>
                    <p className="subtitle">{formatDateTime(row.created_at)}</p>
                  </div>
                </div>
                <div className="stack-item-side">
                  <StatusBadge status={row.status} />
                </div>
              </article>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
