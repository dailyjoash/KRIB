import React, { useEffect, useState } from "react";
import api from "../services/api";
import { downloadBlob } from "../utils/files";
import { getErrorMessage } from "../utils/errors";
import GlassCard from "./GlassCard";
import StatusBadge from "./StatusBadge";
import { formatKES } from "../utils/format";

export default function LandlordReceipts() {
  const [rows, setRows] = useState([]);
  const [period, setPeriod] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get("/api/landlord/receipts/", { params: period ? { period } : {} });
        setRows(res.data);
      } catch (err) {
        setError(getErrorMessage(err, "Failed to load receipts."));
      }
    };
    load();
  }, [period]);

  return (
    <div className="dashboard-container">
      {error ? <p className="error">{error}</p> : null}
      <GlassCard title="Receipts" actions={<input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />}>
        <table className="mobile-table">
          <thead>
            <tr>
              <th>M-Pesa Receipt Code</th>
              <th>Tenant</th>
              <th>Unit</th>
              <th>Amount</th>
              <th>Period</th>
              <th>Status</th>
              <th>Date</th>
              <th>Receipt</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td data-label="Receipt Code">{row.mpesa_receipt || "-"}</td>
                <td data-label="Tenant">{row.tenant?.username || row.tenant?.email || "-"}</td>
                <td data-label="Unit">{row.unit ? `${row.unit.property_name} / ${row.unit.unit_number}` : "-"}</td>
                <td data-label="Amount">{formatKES(row.amount)}</td>
                <td data-label="Period">{row.period}</td>
                <td data-label="Status"><StatusBadge status={(row.status || "").toUpperCase()} /></td>
                <td data-label="Date">{new Date(row.created_at).toLocaleString()}</td>
                <td data-label="Receipt">
                  <button type="button" className="btn btn-glass" onClick={() => downloadBlob(`/api/payments/receipt/${row.id}/`, `krib-receipt-${row.id}.pdf`)}>
                    Download
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </GlassCard>
    </div>
  );
}
