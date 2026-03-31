import React from "react";

export default function FeatureTile({ icon: Icon, title, value, label, description, onClick }) {
  return (
    <button className="resident-feature-card" type="button" onClick={onClick}>
      <div className="resident-feature-head">
        <h3>{title}</h3>
        {Icon ? (
          <span className="resident-round-icon">
            <Icon size={18} />
          </span>
        ) : null}
      </div>
      <div className="resident-feature-stats">
        <strong>{value}</strong>
        <span>{label}</span>
      </div>
      <p>{description}</p>
    </button>
  );
}
