import React from "react";

const formatCurrency = (amount) => `$${Number(amount || 0).toFixed(2)}`;

export default function StatCards({ expected = 0, collected = 0, outstanding = 0 }) {
  return (
    <div className="summary-stats">
      <div className="stat-card">
        <p>Expected</p>
        <h3>{formatCurrency(expected)}</h3>
      </div>
      <div className="stat-card">
        <p>Collected</p>
        <h3>{formatCurrency(collected)}</h3>
      </div>
      <div className="stat-card">
        <p>Outstanding</p>
        <h3>{formatCurrency(outstanding)}</h3>
      </div>
    </div>
  );
}
