import React from "react";

export default function WelcomeBanner({ title, subtitle }) {
  return (
    <section className="welcome-banner">
      <h2 className="welcome-title">{title}</h2>
      <p className="welcome-subtitle">{subtitle}</p>
    </section>
  );
}
