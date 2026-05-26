import React, { useEffect, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import heroImage from "../assets/images.jpg";
import logo from "../assets/Gemini_Generated_Image_2trnue2trnue2trn (1).png";

function getInviteErrorState(err, fallback) {
  const detail = String(err?.response?.data?.detail || "").trim().toLowerCase();
  if (detail.includes("cancelled")) {
    return {
      title: "This invite was cancelled.",
      body: "This tenant invite was cancelled by the landlord or manager. Ask them to send you a fresh tenant invite.",
    };
  }
  if (detail.includes("already been used")) {
    return {
      title: "This invite has already been used.",
      body: "This tenant invite was already accepted. Sign in with the account that was created for you.",
    };
  }
  if (detail.includes("expired")) {
    return {
      title: "This invite has expired.",
      body: "This tenant invite has expired. Ask your landlord or manager to send you a fresh tenant invite.",
    };
  }
  if (err?.response?.status === 404 || detail === "not found" || detail.includes("invalid")) {
    return {
      title: "This invite link is invalid.",
      body: "We could not find this tenant invite. Ask your landlord or manager to send you a fresh tenant invite.",
    };
  }
  return {
    title: fallback,
    body: getErrorMessage(err, fallback),
  };
}

function getInviteDeadState(invite) {
  if (!invite) return null;
  const status = String(invite.status || "").trim().toLowerCase();
  const expiresAt = invite.expires_at ? new Date(invite.expires_at) : null;
  const isExpired = status === "expired" || (expiresAt && !Number.isNaN(expiresAt.getTime()) && expiresAt.getTime() < Date.now());

  if (status === "cancelled") {
    return {
      title: "This invite was cancelled.",
      body: "This tenant invite was cancelled by the landlord or manager. Ask them to send you a fresh tenant invite.",
    };
  }
  if (status === "accepted") {
    return {
      title: "This invite has already been used.",
      body: "This tenant invite was already accepted. Sign in with the account that was created for you.",
    };
  }
  if (isExpired) {
    return {
      title: "This invite has expired.",
      body: "This tenant invite has expired. Ask your landlord or manager to send you a fresh tenant invite.",
    };
  }
  return null;
}

export default function AcceptTenantInvite() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [invite, setInvite] = useState(null);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [error, setError] = useState("");
  const [deadState, setDeadState] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingInvite, setLoadingInvite] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  // The detail endpoint exposes otp_expires_at when the inviter attached an
  // OTP. We use it to decide whether to render the OTP input. The actual OTP
  // code itself is never sent to the client; the user receives it out-of-band
  // (SMS/email) and types it in.
  const requiresOtp = Boolean(invite?.otp_expires_at);

  useEffect(() => {
    let active = true;

    const loadInvite = async () => {
      try {
        const res = await api.get(`/api/invites/${token}/`);
        if (!active) return;
        const state = getInviteDeadState(res.data);
        if (state) {
          setInvite(null);
          setDeadState(state);
          setError(state.title);
          return;
        }
        setInvite(res.data);
        setDeadState(null);
        setError("");
      } catch (err) {
        if (!active) return;
        const state = getInviteErrorState(err, "This tenant invite is not available.");
        setInvite(null);
        setDeadState(state);
        setError(state.title);
      } finally {
        if (!active) return;
        setLoadingInvite(false);
      }
    };

    loadInvite();
    return () => {
      active = false;
    };
  }, [token]);

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }

    if (requiresOtp && !otpCode.trim()) {
      setError("Enter the OTP your landlord sent you.");
      return;
    }

    setLoading(true);
    try {
      const payload = new FormData();
      payload.append("first_name", firstName.trim());
      payload.append("last_name", lastName.trim());
      payload.append("password", password);
      if (requiresOtp) {
        payload.append("otp_code", otpCode.trim());
      }
      await api.post(`/api/invites/${token}/accept/`, payload, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      navigate("/login", { replace: true, state: { message: "Tenant invite accepted. Please sign in." } });
    } catch (err) {
      const state = getInviteErrorState(err, "Unable to accept tenant invite.");
      setDeadState(invite ? null : state);
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
          <h2 className="auth-title">Accept tenant invite</h2>
          {loadingInvite ? (
            <p className="auth-subtitle">Loading invite details...</p>
          ) : invite ? (
            <p className="auth-subtitle">
              Set your login details to activate {invite.full_name || "your tenant"} account{invite.property_name ? ` for ${invite.property_name}` : ""}{invite.unit_label ? ` in ${invite.unit_label}` : ""}.
            </p>
          ) : (
            <p className="auth-subtitle">{deadState?.body || "This invite link is no longer active. Ask your landlord or manager to send you a fresh tenant invite."}</p>
          )}

          {invite ? (
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
                  name="new-password"
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
                  name="confirm-password"
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
              {requiresOtp ? (
                <input
                  className="auth-input"
                  name="otp_code"
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, "").slice(0, 8))}
                  placeholder="One-time code (from SMS/email)"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  required
                />
              ) : null}
              {error ? <p className="error">{error}</p> : null}
              <button type="submit" className="auth-button" disabled={loading || !invite}>
                {loading ? "Accepting invite..." : "Accept invite"}
              </button>
            </form>
          ) : null}

          {!loadingInvite && !invite ? (
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
