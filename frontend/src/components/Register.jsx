import React, { useContext, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { AuthContext } from "../context/AuthContext";
import { getErrorMessage } from "../utils/errors";
import logo from "../assets/krib-logo.png";

export default function Register() {
  const navigate = useNavigate();
  const { register } = useContext(AuthContext);
  const [form, setForm] = useState({
    name: "",
    email: "",
    phone: "",
    role: "tenant",
    password: "",
    confirmPassword: "",
  });
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    if (form.password !== form.confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      const user = await register({
        name: form.name,
        email: form.email,
        phone: form.phone,
        role: form.role,
        password: form.password,
      });
      navigate(user.role === "landlord" ? "/dashboard" : "/tenant");
    } catch (err) {
      setError(err.message || getErrorMessage(err, "Unable to create account."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <section className="auth-left">
        <div className="auth-left-overlay">
          <p className="auth-kicker">Phone-first Rental Management</p>
          <h1>Create your KRIB account and step into a cleaner rental workflow.</h1>
          <p className="auth-subtitle">
            Landlords can start managing properties immediately, while tenants get payments, maintenance, and documents in one place.
          </p>
        </div>
      </section>

      <section className="auth-right">
        <div className="auth-card">
          <img src={logo} alt="KRIB logo" className="auth-logo" />
          <h2 className="auth-title">Create account</h2>
          <p className="auth-subtitle">Use your email and phone number so KRIB can route notices and payment records correctly.</p>

          <form onSubmit={handleSubmit}>
            <input className="auth-input" name="name" placeholder="Full name" value={form.name} onChange={handleChange} required />
            <input className="auth-input" type="email" name="email" placeholder="Email address" value={form.email} onChange={handleChange} required />
            <input className="auth-input" name="phone" placeholder="Phone number" value={form.phone} onChange={handleChange} required />
            <select className="auth-input" name="role" value={form.role} onChange={handleChange}>
              <option value="tenant">Tenant</option>
              <option value="landlord">Landlord</option>
            </select>

            <div className="auth-password-wrap">
              <input
                className="auth-input"
                type={showPassword ? "text" : "password"}
                name="password"
                placeholder="Password"
                value={form.password}
                onChange={handleChange}
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

            <input
              className="auth-input"
              type={showPassword ? "text" : "password"}
              name="confirmPassword"
              placeholder="Confirm password"
              value={form.confirmPassword}
              onChange={handleChange}
              required
            />

            {error ? <p className="error">{error}</p> : null}

            <button type="submit" className="auth-button" disabled={loading}>
              {loading ? "Creating account..." : "Create account"}
            </button>
          </form>

          <p className="auth-footnote">
            Already have an account? <Link to="/login">Sign in</Link>
          </p>
        </div>
      </section>
    </div>
  );
}
