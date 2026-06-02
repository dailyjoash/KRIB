import React, { useContext, useEffect, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { AuthContext } from "../context/AuthContext";
import { getErrorMessage } from "../utils/errors";
import heroImage from "../assets/images.jpg";
import logo from "../assets/Gemini_Generated_Image_2trnue2trnue2trn (1).png";

const Login = () => {
  const navigate = useNavigate();
  const { authReady, isAuthenticated, login, role } = useContext(AuthContext);
  const location = useLocation();

  const [formData, setFormData] = useState({
    email: "",
    password: "",
  });

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    if (!authReady || !isAuthenticated || !role) return;

    navigate(
      role === "landlord"
        ? "/dashboard"
        : role === "tenant"
          ? "/tenant"
          : "/manager",
      { replace: true }
    );
  }, [authReady, isAuthenticated, navigate, role]);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const userData = await login({
        email: formData.email,
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
      setError(getErrorMessage(err, "Invalid login details."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <section
        className="auth-left"
        style={{
          backgroundImage: `linear-gradient(160deg, rgba(16, 26, 54, 0.48), rgba(7, 10, 24, 0.82)), url(${heroImage})`,
        }}
      />

      <section className="auth-right">
        <div className="auth-card">
          <img src={logo} alt="KRIB logo" className="auth-logo" />
          <h2 className="auth-title">Sign in</h2>

          <form onSubmit={handleSubmit}>
            <input
              type="text"
              name="email"
              placeholder="Email or username"
              value={formData.email}
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
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>

            <p className="auth-forgot">
              <Link to="/forgot-password">Forgot password?</Link>
            </p>

            {location.state?.message ? <p className="success">{location.state.message}</p> : null}
            {error ? <p className="error">{error}</p> : null}

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
