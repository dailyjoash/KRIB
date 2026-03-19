import React, { useState, useContext } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { AuthContext } from "../context/AuthContext";
import logo from "../assets/krib-logo.png";

const Login = () => {
  const navigate = useNavigate();
  const { login } = useContext(AuthContext);
  const location = useLocation();

  const [formData, setFormData] = useState({
    username: "",
    password: "",
  });

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      console.log("Sending login request for:", formData.username);

      const userData = await login({
        username: formData.username,
        password: formData.password,
      });

      navigate(
        userData.role === "landlord"
          ? "/dashboard"
          : userData.role === "tenant"
            ? "/tenant"
            : "/manager"
      );
    } catch (err) {
      console.error("❌ Login failed:", err.response?.data || err.message);
      setError(err.response?.data?.detail || "Invalid credentials. Try again!");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <section className="auth-left">
        <div className="auth-left-overlay">
          <p className="auth-kicker">Property Management, Elevated</p>
          <h1>Run your rentals smarter with KRIB.</h1>
          <p className="auth-subtitle">
            Track rent, maintenance, and communication in one premium platform.
          </p>
        </div>
      </section>

      <section className="auth-right">
        <div className="auth-card">
          <img src={logo} alt="KRIB logo" className="auth-logo" />
          <h2 className="auth-title">Sign in</h2>
          <p className="auth-subtitle">Welcome back. Access your account below.</p>

          <form onSubmit={handleSubmit}>
            <input
              type="text"
              name="username"
              placeholder="Username or email"
              value={formData.username}
              onChange={handleChange}
              className="auth-input"
              required
            />

            <div className="auth-password-wrap">
              <input
                type={showPassword ? "text" : "password"}
                name="password"
                placeholder="Password"
                value={formData.password}
                onChange={handleChange}
                className="auth-input"
                required
              />
              <button
                type="button"
                className="auth-password-toggle"
                onClick={() => setShowPassword((prev) => !prev)}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? "🙈" : "👁️"}
              </button>
            </div>

            <a href="#" className="auth-forgot" onClick={(e) => e.preventDefault()}>
              Forgot password?
            </a>

            {location.state?.message && <p className="success">{location.state.message}</p>}
            {error && <p className="error">{error}</p>}

            <button type="submit" className="auth-button" disabled={loading}>
              {loading ? "Logging in..." : "Sign in"}
            </button>
          </form>
        </div>
      </section>
    </div>
  );
};

export default Login;
