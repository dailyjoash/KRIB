import React from "react";

export default function SectionCard({ icon: Icon, title, action = null, children }) {
  return (
    <section className="resident-section-card">
      {(Icon || title || action) ? (
        <div className="resident-section-head">
          <div className="resident-title-row">
            {Icon ? <Icon size={18} /> : null}
            {title ? <h2>{title}</h2> : null}
          </div>
          {action}
        </div>
      ) : null}
      {children}
    </section>
  );
}
