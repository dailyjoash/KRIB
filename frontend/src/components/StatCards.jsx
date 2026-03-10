import React from "react";
import { formatKES } from "../utils/format";

export default function StatCards({ expected = 0, collected = 0, outstanding = 0 }) {
  return (
    <div className="summary-stats">
      <div className="stat-card">
        <p>Expected</p>
        <h3>{formatKES(expected)}</h3>
      </div>
      <div className="stat-card">
        <p>Collected</p>
        <h3>{formatKES(collected)}</h3>
      </div>
      <div className="stat-card">
        <p>Outstanding</p>
        <h3>{formatKES(outstanding)}</h3>
      </div>
    </div>
  );
}
