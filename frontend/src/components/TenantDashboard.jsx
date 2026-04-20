import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Wrench } from "lucide-react";
import api from "../services/api";
import { formatDate, formatKES } from "../utils/format";
import Greeting from "./Greeting";

export default function TenantDashboard() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [wallet, setWallet] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const [summaryRes, walletRes] = await Promise.all([
          api.get("/api/dashboard/summary/"),
          api.get("/api/wallet/"),
        ]);
        setSummary(summaryRes.data);
        setWallet(walletRes.data);
      } catch {
        setError("Failed to load resident home");
        setSummary({ active_lease: null, rent: {}, maintenance: [] });
        setWallet({ wallet_available: 0 });
      }
    };
    load();
  }, []);

  const openMaintenance = useMemo(
    () => (summary?.maintenance || []).filter((item) => item.status !== "resolved"),
    [summary?.maintenance]
  );

  if (!summary || !wallet) {
    return <p className="loading">Loading...</p>;
  }

  const lease = summary.active_lease;

  return (
    <div className="resident-page">
      {error ? <p className="error">{error}</p> : null}

      <section className="resident-intro-card">
        <div className="resident-intro-copy">
          <p className="resident-kicker">Welcome</p>
          <h1><Greeting /></h1>
        </div>
      </section>

      <section className="resident-hero-grid">
        <button className="resident-gradient-card blue" type="button" onClick={() => navigate("/tenant/lease")}>
          <div>
            <h3>Current Lease</h3>
            <p>{lease ? `${formatDate(lease.start_date)} - Active` : "No active lease"}</p>
          </div>
          <span className="resident-ghost-btn">View</span>
        </button>

        <button className="resident-gradient-card purple" type="button" onClick={() => navigate("/tenant/pay")}>
          <div>
            <h3>Amount Due</h3>
            <p>{summary.rent?.status || "pending"}</p>
            <strong>{formatKES(summary.rent?.balance || 0)}</strong>
          </div>
          <span className="resident-ghost-btn">Pay Now</span>
        </button>

        <button className="resident-gradient-card mint" type="button" onClick={() => navigate("/tenant/finance?tab=wallet")}>
          <div>
            <h3>Rent Credit</h3>
            <p>Available credit</p>
            <strong>{formatKES(wallet.wallet_available || 0)}</strong>
          </div>
          <span className="resident-ghost-btn">Open</span>
        </button>
      </section>

      <section className="resident-feature-grid resident-feature-grid-single">
        {lease ? (
          <button className="resident-feature-card" type="button" onClick={() => navigate("/tenant/maintenance")}>
            <div className="resident-feature-head">
              <h3>Maintenance</h3>
              <span className="resident-round-icon"><Wrench size={18} /></span>
            </div>
            <div className="resident-feature-stats">
              <strong>{String(openMaintenance.length).padStart(2, "0")}</strong>
              <span>Open</span>
            </div>
          </button>
        ) : (
          <article className="resident-feature-card">
            <div className="resident-feature-head">
              <h3>Maintenance</h3>
              <span className="resident-round-icon"><Wrench size={18} /></span>
            </div>
            <div className="resident-feature-stats">
              <strong>--</strong>
              <span>Unavailable</span>
            </div>
          </article>
        )}
      </section>
    </div>
  );
}
