import React from "react";
import { ArrowUpRight } from "lucide-react";

export default function GradientCard({
  title,
  subtitle,
  value,
  ctaLabel,
  onCta,
  icon: Icon,
  variant = "blue",
}) {
  return (
    <article className={`gcard gcard-${variant}`}>
      <div className="gcard-icon-pill">{Icon ? <Icon size={20} /> : null}</div>
      <h3 className="gcard-title">{title}</h3>
      <p className="gcard-subtitle">{subtitle}</p>
      <p className="gcard-value">{value}</p>
      {ctaLabel ? (
        <button className="btn btn-glass" onClick={onCta} type="button">
          <ArrowUpRight size={16} />
          <span>{ctaLabel}</span>
        </button>
      ) : null}
    </article>
  );
}
