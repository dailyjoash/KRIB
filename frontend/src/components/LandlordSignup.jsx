import React, { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../services/api";

export default function LandlordSignup() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    business_name: "",
    username: "",
    email: "",
    phone_number: "",
    password: "",
    confirm_password: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const passwordMismatch = useMemo(
    () => form.confirm_password && form.password !== form.confirm_password,
    [form.confirm_password, form.password]
  );

  const handleChange = (e) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (passwordMismatch) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      await api.post("/api/auth/signup-landlord/", {
        business_name: form.business_name,
        username: form.username,
        email: form.email,
        phone_number: form.phone_number,
        password: form.password,
      });
      navigate("/login", { state: { message: "Account created, please sign in" } });
    } catch (err) {
      setError(err.response?.data?.detail || "Signup failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <h2>Create landlord account</h2>
        <p className="subtitle">Start managing your properties with KRIB.</p>
        <form onSubmit={handleSubmit}>
          <input name="business_name" placeholder="Business name" value={form.business_name} onChange={handleChange} required />
          <input name="username" placeholder="Username" value={form.username} onChange={handleChange} required />
          <input type="email" name="email" placeholder="Email" value={form.email} onChange={handleChange} required />
          <input name="phone_number" placeholder="Phone number" value={form.phone_number} onChange={handleChange} required />
          <input type="password" name="password" placeholder="Password" value={form.password} onChange={handleChange} required />
          <input type="password" name="confirm_password" placeholder="Confirm password" value={form.confirm_password} onChange={handleChange} required />
          {error && <p className="error">{error}</p>}
          <button type="submit" className="btn-primary" disabled={loading || passwordMismatch}>
            {loading ? "Creating account..." : "Create landlord account"}
          </button>
        </form>
        <p className="subtitle">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
