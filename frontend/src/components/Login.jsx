import React, { useState, useContext } from "react";
import { useNavigate } from "react-router-dom";
import api from "../services/api";
import { AuthContext } from "../context/AuthContext";

const Login = () => {
  const navigate = useNavigate();
  const { setUser } = useContext(AuthContext); // works now

  const [formData, setFormData] = useState({
    username: "",
    password: "",
    role: "tenant",
  });

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      console.log("Sending login request for:", formData.username);

      const res = await api.post("/api/token/", {
        username: formData.username,
        password: formData.password,
      });

      console.log("Login response:", res.data);

      const { access, refresh } = res.data;

      if (!access || !refresh) {
        throw new Error("No tokens returned from server");
      }

      // Save tokens + role
      localStorage.setItem("access", access);
      localStorage.setItem("refresh", refresh);
      localStorage.setItem("role", formData.role);

      // Update context state
      setUser({
        username: formData.username,
        role: formData.role,
        token: access,
      });

      // Redirect based on role
      navigate(
        formData.role === "landlord"
          ? "/dashboard"
          : formData.role === "tenant"
            ? "/tenant-dashboard"
            : "/manager-dashboard"
      );
    } catch (err) {
      console.error("❌ Login failed:", err.response?.data || err.message);
      setError(err.response?.data?.detail || "Invalid credentials. Try again!");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <h2>
          Welcome to <span className="brand">KRIB</span> 🏠
        </h2>
        <p className="subtitle">Sign in to manage your rentals</p>

        <form onSubmit={handleSubmit}>
          <input
            type="text"
            name="username"
            placeholder="Username"
            value={formData.username}
            onChange={handleChange}
            required
          />

          <input
            type="password"
            name="password"
            placeholder="Password"
            value={formData.password}
            onChange={handleChange}
            required
          />

          <select name="role" value={formData.role} onChange={handleChange}>
            <option value="landlord">Landlord</option>
            <option value="tenant">Tenant</option>
            <option value="manager">Manager</option>
          </select>

          {error && <p className="error">{error}</p>}

          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? "Logging in..." : "Login"}
          </button>
        </form>
      </div>
    </div>
  );
};

export default Login;
