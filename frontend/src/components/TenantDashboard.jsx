import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CircleDollarSign, Home, Wallet } from "lucide-react";
import api from "../services/api";
import GradientCard from "./GradientCard";
import Greeting from "./Greeting";
import WelcomeBanner from "./WelcomeBanner";

const formatCurrency = (amount) => Number(amount || 0).toFixed(2);

export default function TenantDashboard() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [wallet, setWallet] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const [sumRes, walletRes] = await Promise.all([api.get("/api/dashboard/summary/"), api.get("/api/wallet/")]);
        setSummary(sumRes.data);
        setWallet(walletRes.data);
      } catch {
        setError("Failed to load tenant dashboard");
        setSummary({ active_lease: null, rent: {} });
        setWallet({ wallet_available: 0 });
      }
    };
    load();
  }, []);

  if (!summary || !wallet) return <p className="loading">Loading...</p>;

  const leaseSubtitle = summary.active_lease?.unit
    ? `${summary.active_lease.unit.property?.name || "Property"}`
    : "No active lease";
  const leaseValue = summary.active_lease?.unit ? `Unit ${summary.active_lease.unit.unit_number}` : "Not assigned";

  return (
    <div className="dashboard-container">
      <WelcomeBanner title={<Greeting />} subtitle="Tenant view" />
      {error ? <p className="error">{error}</p> : null}

      <section className="gradient-card-row">
        <GradientCard
          variant="blue"
          icon={Home}
          title="Current Lease"
          subtitle={leaseSubtitle}
          value={leaseValue}
          ctaLabel="View lease"
          onCta={() => navigate("/tenant/lease")}
          onClick={() => navigate("/tenant/lease")}
        />
        <GradientCard
          variant="indigo"
          icon={CircleDollarSign}
          title="Amount Due"
          subtitle={`Status: ${summary.rent?.status || "pending"}`}
          value={formatCurrency(summary.rent?.balance || summary.rent?.rent_due)}
          ctaLabel="Pay now"
          onCta={() => navigate("/tenant/pay")}
          onClick={() => navigate("/tenant/pay")}
        />
        <GradientCard
          variant="violet"
          icon={Wallet}
          title="Wallet"
          subtitle="Available balance"
          value={formatCurrency(wallet.wallet_available)}
          ctaLabel="Withdraw / Wallet"
          onCta={() => navigate("/tenant/wallet")}
          onClick={() => navigate("/tenant/wallet")}
        />
      </section>
    </div>
  );
}
