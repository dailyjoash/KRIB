import React, { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import heroImage from "../assets/images.jpg";
import logo from "../assets/Gemini_Generated_Image_2trnue2trnue2trn (1).png";

function getInviteErrorState(err, fallback) {
  const detail = String(err?.response?.data?.detail || "").trim().toLowerCase();
  if (detail.includes("already used")) {
    return {
      title: "This invite has already been used.",
      body: "This manager invite was already accepted. Sign in with the account that was created for you.",
    };
  }
  if (detail.includes("expired")) {
    return {
      title: "This invite has expired.",
      body: "This manager invite has expired. Ask the landlord or admin to send you a fresh manager invite.",
    };
  }
  if (err?.response?.status === 404 || detail === "not found" || detail.includes("invalid")) {
    return {
      title: "This invite link is invalid.",
      body: "We could not find this manager invite. Ask the landlord or admin to send you a fresh manager invite.",
    };
  }
  return {
    title: fallback,
    body: getErrorMessage(err, fallback),
  };
}

export default function AcceptInvite() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [deadState, setDeadState] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      await api.post("/api/manager-invites/accept/", {
        token,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        password,
      });
      navigate("/login", { replace: true, state: { message: "Manager invite accepted. Please sign in." } });
    } catch (err) {
      const state = getInviteErrorState(err, "Unable to accept manager invite.");
      setDeadState(state);
      setError(state.title);
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
          <h2 className="auth-title">Accept manager invite</h2>
          <p className="auth-subtitle">{deadState?.body || "Enter your first and last name, then choose a secure password to activate your manager account."}</p>

          <form onSubmit={submit}>
            <input
              className="auth-input"
              name="first_name"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              placeholder="First name"
              autoComplete="given-name"
              required
            />
            <input
              className="auth-input"
              name="last_name"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              placeholder="Last name"
              autoComplete="family-name"
              required
            />
            <div className="auth-password-wrap">
              <input
                className="auth-input"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password"
                autoComplete="new-password"
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
            <div className="auth-password-wrap">
              <input
                className="auth-input"
                type={showConfirm ? "text" : "password"}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="Confirm password"
                autoComplete="new-password"
                required
              />
              <button
                type="button"
                className="auth-password-toggle"
                onClick={() => setShowConfirm((prev) => !prev)}
                aria-label={showConfirm ? "Hide confirm password" : "Show confirm password"}
              >
                {showConfirm ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            {error ? <p className="error">{error}</p> : null}
            <button type="submit" className="auth-button" disabled={loading}>
              {loading ? "Accepting invite..." : "Accept invite"}
            </button>
          </form>

          {deadState ? (
            <div className="auth-dead-end">
              <button
                type="button"
                className="auth-button auth-button-link"
                onClick={() => navigate("/login", { replace: true })}
              >
                Back to sign in
              </button>
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
