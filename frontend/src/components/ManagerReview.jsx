import React, { useEffect, useState } from "react";
import api from "../services/api";
import GlassCard from "./GlassCard";
import StatusBadge from "./StatusBadge";
import { formatKES } from "../utils/format";

export default function ManagerReview() {
  const [rows, setRows] = useState([]);
  const [period, setPeriod] = useState("");

  useEffect(() => {
    const load = async () => {
      const params = { status: "SUCCESS" };
      if (period) params.period = period;
      const res = await api.get("/api/payments/", { params });
      setRows(res.data || []);
    };
    load();
  }, [period]);

  return (
    <div className="dashboard-container">
      <GlassCard title="Payments Review" actions={<input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />}>
        <table>
          <thead>
            <tr>
              <th>M-Pesa Receipt Code</th>
              <th>Tenant</th>
              <th>Unit</th>
              <th>Amount (KES)</th>
              <th>Period</th>
              <th>Status</th>
              <th>Date</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.mpesa_receipt || "-"}</td>
                <td>{row.tenant?.username || row.tenant?.email || "-"}</td>
                <td>{row.lease?.unit ? `${row.lease.unit.property?.name || "-"} / ${row.lease.unit.unit_number}` : "-"}</td>
                <td>{formatKES(row.amount)}</td>
                <td>{row.period || "-"}</td>
                <td><StatusBadge status={row.status} /></td>
                <td>{row.created_at ? new Date(row.created_at).toLocaleString() : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </GlassCard>
    </div>
  );
}
