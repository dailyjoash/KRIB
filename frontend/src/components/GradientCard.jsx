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
  onClick,
}) {
  const handleCardClick = () => {
    if (onClick) onClick();
  };

  return (
    <article
      className={`gcard gcard-${variant} ${onClick ? "gcard-clickable" : ""}`.trim()}
      onClick={handleCardClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={(e) => {
        if (onClick && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <div className="gcard-content">
        <div className="gcard-icon-pill">{Icon ? <Icon size={20} /> : null}</div>
        <h3 className="gcard-title">{title}</h3>
        <p className="gcard-subtitle">{subtitle}</p>
        <p className="gcard-value">{value}</p>
      </div>
      {ctaLabel ? (
        <button
          className="btn btn-glass gcard-cta"
          onClick={(e) => {
            e.stopPropagation();
            if (onCta) onCta();
          }}
          type="button"
        >
          <ArrowUpRight size={18} />
          <span>{ctaLabel}</span>
        </button>
      ) : null}
    </article>
  );
}
