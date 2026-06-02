import React, { useContext, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { MoonStar, ShieldCheck, UserRound } from "lucide-react";
import api from "../services/api";
import { AuthContext } from "../context/AuthContext";
import { getErrorMessage } from "../utils/errors";
import LandlordPayoutSettingsCard from "./LandlordPayoutSettingsCard";
import LandlordSubscriptionCard from "./LandlordSubscriptionCard";
import { PageLayout, SectionCard } from "./ui";

const getStoredTheme = () => (localStorage.getItem("theme") === "dark" ? "dark" : "light");

const applyTheme = (nextTheme) => {
  localStorage.setItem("theme", nextTheme);
  document.documentElement.classList.toggle("theme-light", nextTheme === "light");
};

const InitialAvatar = ({ name }) => (
  <div className="resident-avatar">
    <span>{(name || "K").slice(0, 1).toUpperCase()}</span>
  </div>
);

const ProfileList = ({ rows }) => (
  <div className="resident-profile-list">
    {rows.map((row) => (
      <div key={row.label} className="resident-profile-list-row">
        <span className="resident-profile-list-label">{row.label}</span>
        <strong className="resident-profile-list-value">{row.value}</strong>
      </div>
    ))}
  </div>
);

export default function Profile() {
  const { user } = useContext(AuthContext);
  const navigate = useNavigate();
  const passwordCurrentRef = useRef(null);
  const [me, setMe] = useState(null);
  const [summary, setSummary] = useState(null);
  const [theme, setTheme] = useState(getStoredTheme);
  const [passwordForm, setPasswordForm] = useState({ old_password: "", new_password: "", confirm_password: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.get("/api/me/"), api.get("/api/dashboard/summary/").catch(() => ({ data: null }))])
      .then(([meRes, summaryRes]) => {
        setMe(meRes.data);
        setSummary(summaryRes.data);
      })
      .catch((err) => setError(getErrorMessage(err, "Failed to load profile.")));
  }, []);

  const changePassword = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");
    if (passwordForm.new_password !== passwordForm.confirm_password) {
      setError("Passwords do not match.");
      return;
    }
    try {
      await api.post("/api/auth/change-password/", {
        old_password: passwordForm.old_password,
        new_password: passwordForm.new_password,
      });
      setMessage("Password changed successfully.");
      setPasswordForm({ old_password: "", new_password: "", confirm_password: "" });
    } catch (err) {
      setError(getErrorMessage(err, "Failed to change password."));
    }
  };

  const tenantRows = useMemo(() => {
    if (!me) return [];
    return [
      { label: "Name", value: me.username || "-" },
      { label: "User ID", value: me.id || "-" },
      { label: "Email Address", value: me.email || "-" },
      { label: "Phone Number", value: me.phone_number || "-" },
      { label: "Current Property", value: summary?.active_lease?.unit?.property?.name || "No active lease" },
    ];
  }, [me, summary]);

  const managerRows = useMemo(() => {
    if (!me) return [];
    return [
      { label: "Name", value: me.username || "-" },
      { label: "User ID", value: me.id || "-" },
      { label: "Email Address", value: me.email || "-" },
      { label: "Phone Number", value: me.phone_number || "-" },
      { label: "Role", value: me.role || "-" },
    ];
  }, [me]);

  const landlordRows = useMemo(() => {
    if (!me) return [];
    return [
      { label: "Name", value: me.username || "-" },
      { label: "User ID", value: me.id || "-" },
      { label: "Email Address", value: me.email || "-" },
      { label: "Phone Number", value: me.phone_number || "-" },
      { label: "Role", value: me.role || "-" },
    ];
  }, [me]);

  const passwordMismatch = Boolean(
    passwordForm.new_password
    && passwordForm.confirm_password
    && passwordForm.new_password !== passwordForm.confirm_password
  );

  const passwordReady = Boolean(
    passwordForm.old_password
    && passwordForm.new_password
    && passwordForm.confirm_password
    && !passwordMismatch
  );

  const clearPasswordForm = () => {
    setPasswordForm({ old_password: "", new_password: "", confirm_password: "" });
  };

  const toggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    applyTheme(nextTheme);
  };

  if (!me) {
    if (error) {
      return (
        <div className={user?.role === "tenant" ? "resident-page" : "dashboard-container"}>
          <p className="error">{error}</p>
        </div>
      );
    }
    return <p className="loading">Loading...</p>;
  }

  if (user?.role === "tenant" || user?.role === "manager") {
    const isManager = user?.role === "manager";
    const profileRows = user?.role === "manager" ? managerRows : tenantRows;
    const detailsTitle = isManager ? "Manager Information" : "General Information";

    return (
      <div className="resident-page">
        {message ? <p className="success">{message}</p> : null}
        {error ? <p className="error">{error}</p> : null}

        <SectionCard
          icon={UserRound}
          title={detailsTitle}
          action={<button className="resident-link-btn" type="button" onClick={() => navigate("/profile/contact")}>Edit details</button>}
        >
          <div className="resident-profile-hero resident-profile-hero--list">
            <InitialAvatar name={me?.username} />
            <div className="resident-profile-summary-head resident-profile-summary-head--solo">
              <div>
                <h3>{me.username || "-"}</h3>
              </div>
            </div>
          </div>
          <ProfileList rows={profileRows} />
        </SectionCard>

        <SectionCard
          icon={ShieldCheck}
          title="Security"
        >
          <form className="resident-form-grid resident-profile-stack-form" id="resident-password-form" onSubmit={changePassword}>
            <p className="resident-form-note">
              Update your password here whenever you want to secure your account.
            </p>
            <label className="resident-field">
              <span>Current password</span>
              <input ref={passwordCurrentRef} type="password" value={passwordForm.old_password} onChange={(e) => setPasswordForm({ ...passwordForm, old_password: e.target.value })} required />
            </label>
            <label className="resident-field">
              <span>New password</span>
              <input type="password" value={passwordForm.new_password} onChange={(e) => setPasswordForm({ ...passwordForm, new_password: e.target.value })} required />
            </label>
            <label className="resident-field">
              <span>Confirm new password</span>
              <input type="password" value={passwordForm.confirm_password} onChange={(e) => setPasswordForm({ ...passwordForm, confirm_password: e.target.value })} required />
            </label>
            {passwordMismatch ? <p className="resident-inline-error">New passwords do not match yet.</p> : null}
            <div className="resident-form-actions resident-profile-form-actions">
              <button className="resident-link-btn" type="button" onClick={clearPasswordForm} disabled={!passwordForm.old_password && !passwordForm.new_password && !passwordForm.confirm_password}>Clear</button>
              <button className="resident-primary-btn" type="submit" disabled={!passwordReady}>Update Password</button>
            </div>
          </form>
        </SectionCard>

        <SectionCard icon={MoonStar} title="Dark Mode">
          <div className="resident-display-row">
            <div className="resident-display-copy">
              <strong>Theme toggle</strong>
              <p>Switch the dashboard between light and dark viewing modes.</p>
            </div>
            <button className="resident-primary-btn" type="button" onClick={toggleTheme}>
              {theme === "dark" ? "Light mode" : "Dark mode"}
            </button>
          </div>
        </SectionCard>
      </div>
    );
  }

  return (
    <PageLayout variant="executive" kicker="Account" title="Profile Settings">
      {message && <p className="success">{message}</p>}
      {error && <p className="error">{error}</p>}

      <SectionCard
        icon={UserRound}
        title="Landlord Information"
        action={<button className="resident-link-btn" type="button" onClick={() => navigate("/profile/contact")}>Edit details</button>}
      >
        <div className="resident-profile-hero resident-profile-hero--list">
          <InitialAvatar name={me?.username} />
          <div className="resident-profile-summary-head resident-profile-summary-head--solo">
            <div>
              <h3>{me.username || "-"}</h3>
            </div>
          </div>
        </div>
        <ProfileList rows={landlordRows} />
      </SectionCard>

      <LandlordPayoutSettingsCard />

      <LandlordSubscriptionCard />

      <SectionCard
        icon={ShieldCheck}
        title="Security"
      >
        <form className="resident-form-grid resident-profile-stack-form" id="resident-password-form" onSubmit={changePassword}>
          <p className="resident-form-note">
            Update your password here whenever you want to secure your account.
          </p>
          <label className="resident-field">
            <span>Current password</span>
            <input ref={passwordCurrentRef} type="password" value={passwordForm.old_password} onChange={(e) => setPasswordForm({ ...passwordForm, old_password: e.target.value })} required />
          </label>
          <label className="resident-field">
            <span>New password</span>
            <input type="password" value={passwordForm.new_password} onChange={(e) => setPasswordForm({ ...passwordForm, new_password: e.target.value })} required />
          </label>
          <label className="resident-field">
            <span>Confirm password</span>
            <input
              type="password"
              value={passwordForm.confirm_password}
              onChange={(e) => setPasswordForm({ ...passwordForm, confirm_password: e.target.value })}
              required
            />
          </label>
          {passwordMismatch ? <p className="resident-inline-error">New passwords do not match yet.</p> : null}
          <div className="resident-form-actions resident-profile-form-actions">
            <button className="resident-link-btn" type="button" onClick={clearPasswordForm} disabled={!passwordForm.old_password && !passwordForm.new_password && !passwordForm.confirm_password}>Clear</button>
            <button className="resident-primary-btn" type="submit" disabled={!passwordReady}>Update Password</button>
          </div>
        </form>
      </SectionCard>

      <SectionCard icon={MoonStar} title="Dark Mode">
        <div className="resident-display-row">
          <div className="resident-display-copy">
            <strong>Theme toggle</strong>
            <p>Switch the dashboard between light and dark viewing modes.</p>
          </div>
          <button className="resident-primary-btn" type="button" onClick={toggleTheme}>
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </button>
        </div>
      </SectionCard>
    </PageLayout>
  );
}
