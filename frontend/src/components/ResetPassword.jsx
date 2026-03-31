import React, { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import heroImage from "../assets/images.jpg";
import logo from "../assets/Gemini_Generated_Image_2trnue2trnue2trn (1).png";

export default function ResetPassword() {
  const { uid, token } = useParams();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      await api.post("/api/auth/password-reset/confirm/", {
        uid,
        token,
        new_password: password,
      });
      navigate("/login", { replace: true, state: { message: "Password reset successful. Please sign in." } });
    } catch (err) {
      setError(getErrorMessage(err, "Unable to reset password."));
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
          <h2 className="auth-title">Reset password</h2>

          <form onSubmit={submit}>
            <input
              className="auth-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="New password"
              required
            />
            <input
              className="auth-input"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="Confirm new password"
              required
            />
            {error ? <p className="error">{error}</p> : null}
            <button type="submit" className="auth-button" disabled={loading}>
              {loading ? "Updating password..." : "Update password"}
            </button>
          </form>

          <p className="auth-footnote">
            <Link to="/login">Back to sign in</Link>
          </p>
        </div>
      </section>
    </div>
  );
}
