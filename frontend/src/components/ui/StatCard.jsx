import React from "react";
import { Eye, EyeOff } from "lucide-react";

export default function StatCard({
  variant = "blue",
  title,
  subtitle,
  value,
  ctaLabel,
  onClick,
  blurValue = false,
  isBlurred = false,
  onToggleBlur = null,
}) {
  const toggleEnabled = blurValue && typeof onToggleBlur === "function";
  const clickable = typeof onClick === "function";

  return (
    <article
      className={`resident-gradient-card ${variant} ${clickable ? "is-clickable" : ""}`.trim()}
      onClick={onClick}
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
      onKeyDown={(e) => {
        if (clickable && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <div className="resident-gradient-card-top">
        <div>
          <h3>{title}</h3>
          <p>{subtitle}</p>
          <strong className={toggleEnabled && isBlurred ? "resident-blurred-value" : ""}>{value}</strong>
        </div>
        {toggleEnabled ? (
          <button
            className="resident-value-toggle"
            type="button"
            aria-label={isBlurred ? "Show amount" : "Hide amount"}
            onClick={(e) => {
              e.stopPropagation();
              onToggleBlur();
            }}
          >
            {isBlurred ? <Eye size={16} /> : <EyeOff size={16} />}
          </button>
        ) : null}
      </div>
      {ctaLabel ? <span className="resident-ghost-btn">{ctaLabel}</span> : null}
    </article>
  );
}
