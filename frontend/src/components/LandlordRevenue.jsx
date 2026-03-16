import React, { useEffect, useState } from "react";
import api from "../services/api";
import { formatKES } from "../utils/format";
import GlassCard from "./GlassCard";
import GradientCard from "./GradientCard";
import { Banknote, Wallet } from "lucide-react";

export default function LandlordRevenue() {
  const [data, setData] = useState(null);
  const [period, setPeriod] = useState("");

  useEffect(() => {
    const load = async () => {
      const res = await api.get("/api/landlord/revenue/", { params: period ? { period } : {} });
      setData(res.data);
    };
    load();
  }, [period]);

  if (!data) return <div className="loading">Loading revenue...</div>;

  return (
    <div className="dashboard-container">
      <GlassCard title="Revenue filter" actions={<span className="subtitle">Optional monthly view</span>}>
        <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
      </GlassCard>

      <section className="gradient-card-row two-up">
        <GradientCard variant="blue" icon={Banknote} title="Total Collected" subtitle="Gross" value={formatKES(data.gross_collected)} />
        <GradientCard variant="violet" icon={Wallet} title="Net to Landlord" subtitle="Same as total collected" value={formatKES(data.net_amount)} />
      </section>

      <GlassCard title="Lifetime totals" actions={<span className="subtitle">All successful collections</span>}>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Total Collected</th>
                <th>Net to Landlord</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{formatKES(data.lifetime?.gross_collected)}</td>
                <td>{formatKES(data.lifetime?.net_amount)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  );
}
