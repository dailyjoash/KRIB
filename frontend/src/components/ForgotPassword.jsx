import React, { useState } from "react";
import { Link } from "react-router-dom";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import heroImage from "../assets/images.jpg";
import logo from "../assets/Gemini_Generated_Image_2trnue2trnue2trn (1).png";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    setMessage("");
    setLoading(true);
    try {
      const res = await api.post("/api/auth/password-reset/", { email });
      setMessage(res.data?.detail || "If that email exists, a reset link has been sent.");
      setEmail("");
    } catch (err) {
      setError(getErrorMessage(err, "Unable to request password reset."));
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
          <h2 className="auth-title">Forgot password</h2>

          <form onSubmit={submit}>
            <input
              className="auth-input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email address"
              required
            />
            {message ? <p className="success">{message}</p> : null}
            {error ? <p className="error">{error}</p> : null}
            <button type="submit" className="auth-button" disabled={loading}>
              {loading ? "Sending link..." : "Send reset link"}
            </button>
          </form>

          <p className="auth-footnote">
            Remembered your password? <Link to="/login">Back to sign in</Link>
          </p>
        </div>
      </section>
    </div>
  );
}
