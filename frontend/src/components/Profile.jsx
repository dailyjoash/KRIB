import React, { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import api from "../services/api";
import GlassCard from "./GlassCard";

export default function Profile() {
  const [form, setForm] = useState({ email: "", phone_number: "" });
  const [passwordForm, setPasswordForm] = useState({ old_password: "", new_password: "", confirm_password: "" });
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "light");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/api/me/").then((res) => {
      setForm({
        email: res.data.email || "",
        phone_number: res.data.phone_number || "",
      });
    }).catch(() => setError("Failed to load profile"));
  }, []);

  useEffect(() => {
    localStorage.setItem("theme", theme);
    if (theme === "light") {
      document.documentElement.classList.add("theme-light");
    } else {
      document.documentElement.classList.remove("theme-light");
    }
  }, [theme]);

  const saveProfile = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      await api.patch("/api/me/", form);
      setMessage("Profile updated successfully.");
    } catch (err) {
      setError(JSON.stringify(err.response?.data || "Failed to update profile"));
    }
  };

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
      setError(JSON.stringify(err.response?.data || "Failed to change password"));
    }
  };

  return (
    <div className="dashboard-container">
      <h2>Profile Settings</h2>
      {message && <p className="success">{message}</p>}
      {error && <p className="error">{error}</p>}

      <GlassCard title="Update details">
        <form onSubmit={saveProfile}>
          <input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="Email" />
          <input value={form.phone_number} onChange={(e) => setForm({ ...form, phone_number: e.target.value })} placeholder="Phone number" />
          <button type="submit">Save</button>
        </form>
      </GlassCard>

      <GlassCard title="Change password">
        <form onSubmit={changePassword}>
          <input type="password" value={passwordForm.old_password} onChange={(e) => setPasswordForm({ ...passwordForm, old_password: e.target.value })} placeholder="Old password" required />
          <input type="password" value={passwordForm.new_password} onChange={(e) => setPasswordForm({ ...passwordForm, new_password: e.target.value })} placeholder="New password" required />
          <input type="password" value={passwordForm.confirm_password} onChange={(e) => setPasswordForm({ ...passwordForm, confirm_password: e.target.value })} placeholder="Confirm new password" required />
          <button type="submit">Change Password</button>
        </form>
      </GlassCard>

      <GlassCard
        title="Appearance"
        actions={(
          <button className="icon-btn" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} type="button" aria-label="Toggle color theme">
            {theme === "light" ? <Moon size={18} /> : <Sun size={18} />}
          </button>
        )}
      >
        <p className="subtitle">Current theme: {theme === "light" ? "Light" : "Dark"}</p>
      </GlassCard>
    </div>
  );
}
