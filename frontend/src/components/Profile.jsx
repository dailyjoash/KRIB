import React, { useEffect, useState } from "react";
import api from "../services/api";
import BackButton from "./BackButton";

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
    document.documentElement.classList.toggle("theme-dark", theme === "dark");
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
      <BackButton />
      <h2>Profile Settings</h2>
      {message && <p className="success">{message}</p>}
      {error && <p className="error">{error}</p>}

      <div className="card">
        <h3>Update details</h3>
        <form onSubmit={saveProfile}>
          <input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="Email" />
          <input value={form.phone_number} onChange={(e) => setForm({ ...form, phone_number: e.target.value })} placeholder="Phone number" />
          <button type="submit">Save</button>
        </form>
      </div>

      <div className="card">
        <h3>Change password</h3>
        <form onSubmit={changePassword}>
          <input type="password" value={passwordForm.old_password} onChange={(e) => setPasswordForm({ ...passwordForm, old_password: e.target.value })} placeholder="Old password" required />
          <input type="password" value={passwordForm.new_password} onChange={(e) => setPasswordForm({ ...passwordForm, new_password: e.target.value })} placeholder="New password" required />
          <input type="password" value={passwordForm.confirm_password} onChange={(e) => setPasswordForm({ ...passwordForm, confirm_password: e.target.value })} placeholder="Confirm new password" required />
          <button type="submit">Change Password</button>
        </form>
      </div>

      <div className="card">
        <h3>Theme</h3>
        <button onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>Switch to {theme === "dark" ? "light" : "dark"} mode</button>
      </div>
    </div>
  );
}
