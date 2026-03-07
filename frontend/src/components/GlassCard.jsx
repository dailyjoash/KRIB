import React from "react";

export default function GlassCard({ title, actions, children, className = "" }) {
  return (
    <section className={`glass-card ${className}`.trim()}>
      {(title || actions) && (
        <header className="glass-card-header">
          {title ? <h3>{title}</h3> : <span />}
          {actions ? <div>{actions}</div> : null}
        </header>
      )}
      <div className="glass-card-body">{children}</div>
    </section>
  );
}
