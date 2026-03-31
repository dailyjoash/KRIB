import React from "react";

export default function PageLayout({ variant = "tenant", kicker, title, chip, children, className = "" }) {
  return (
    <div className={`resident-page ${variant === "executive" ? "executive-page" : ""} ${className}`.trim()}>
      {title ? (
        <section className="resident-intro-card">
          <div className="resident-intro-copy">
            {kicker ? <p className="resident-kicker">{kicker}</p> : null}
            <h1>{title}</h1>
            {chip ? <span className="resident-chip">{chip}</span> : null}
          </div>
        </section>
      ) : null}
      {children}
    </div>
  );
}
