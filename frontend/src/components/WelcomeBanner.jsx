import React from "react";

export default function WelcomeBanner({ title, subtitle }) {
  return (
    <section className="welcome-banner">
      <div className="welcome-content">
        <p className="welcome-kicker">Welcome back</p>
        <h2 className="welcome-title">{title}</h2>
        <p className="welcome-subtitle">{subtitle}</p>
      </div>
    </section>
  );
}
