import React, { useEffect, useState } from "react";
import api from "../services/api";

const sections = ["PAID", "PARTIAL", "UNPAID", "OVERDUE"];

export default function Dashboard() {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get("/api/dashboard/summary/").then((res) => setData(res.data));
  }, []);

  if (!data) return <p>Loading...</p>;

  return (
    <div className="dashboard-container">
      <h2>Landlord Dashboard ({data.period})</h2>
      <p>
        Expected: {data.totals.expected.toFixed(2)} | Collected: {data.totals.collected.toFixed(2)} |
        Outstanding: {data.totals.outstanding.toFixed(2)}
      </p>
      {sections.map((section) => (
        <div className="card" key={section}>
          <h3>{section}</h3>
          <table>
            <thead>
              <tr><th>Tenant</th><th>Unit</th><th>Due</th><th>Paid</th><th>Balance</th></tr>
            </thead>
            <tbody>
              {(data.lists[section] || []).map((row) => (
                <tr key={row.lease_id}>
                  <td>{row.tenant}</td>
                  <td>{row.unit}</td>
                  <td>{row.rent_due}</td>
                  <td>{row.paid_sum}</td>
                  <td>{row.balance}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
