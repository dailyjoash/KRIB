import React, { useEffect, useState } from "react";
import api from "../services/api";
import GlassCard from "./GlassCard";

const PHOTO_STORAGE_KEY = "profilePhoto";

export default function Profile() {
  const [form, setForm] = useState({ email: "", phone_number: "" });
  const [passwordForm, setPasswordForm] = useState({ old_password: "", new_password: "", confirm_password: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [photo, setPhoto] = useState(localStorage.getItem(PHOTO_STORAGE_KEY) || "");

  useEffect(() => {
    api
      .get("/api/me/")
      .then((res) => {
        setForm({
          email: res.data.email || "",
          phone_number: res.data.phone_number || "",
        });
      })
      .catch(() => setError("Failed to load profile"));
  }, []);

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

  const handlePhotoUpload = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!["image/jpeg", "image/png"].includes(file.type)) {
      setError("Please upload a JPG or PNG image.");
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      const base64 = typeof reader.result === "string" ? reader.result : "";
      if (!base64) return;
      localStorage.setItem(PHOTO_STORAGE_KEY, base64);
      setPhoto(base64);
      setMessage("Profile photo updated.");
      setError("");
      window.dispatchEvent(new Event("profile-photo-updated"));
    };
    reader.readAsDataURL(file);
  };

  const initials = (form.email || "KRIB User")
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "K";

  return (
    <div className="dashboard-container">
      <h2>Profile Settings</h2>
      {message && <p className="success">{message}</p>}
      {error && <p className="error">{error}</p>}

      <GlassCard title="Profile Photo">
        <div className="profile-photo-section">
          {photo ? <img src={photo} alt="Profile" className="profile-photo-preview" /> : <span className="profile-photo-preview profile-photo-fallback">{initials}</span>}
          <label className="btn" htmlFor="profile-photo-input">
            Upload JPG/PNG
          </label>
          <input id="profile-photo-input" type="file" accept="image/jpeg,image/png" onChange={handlePhotoUpload} className="profile-photo-input" />
        </div>
      </GlassCard>

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
          <input
            type="password"
            value={passwordForm.confirm_password}
            onChange={(e) => setPasswordForm({ ...passwordForm, confirm_password: e.target.value })}
            placeholder="Confirm new password"
            required
          />
          <button type="submit">Change Password</button>
        </form>
      </GlassCard>
    </div>
  );
}
