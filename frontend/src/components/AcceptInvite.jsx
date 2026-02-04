import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api from "../services/api";

export default function AcceptInvite() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [invite, setInvite] = useState(null);
  const [otp, setOtp] = useState("");
  const [password, setPassword] = useState("");
  const [otpVerified, setOtpVerified] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const loadInvite = async () => {
      try {
        const res = await api.get(`/api/invites/${token}/`);
        setInvite(res.data);
      } catch (err) {
        console.error("Failed to load invite:", err);
        setError("Invite not found.");
      }
    };
    loadInvite();
  }, [token]);

  const verifyOtp = async () => {
    setError("");
    setMessage("");
    try {
      await api.post(`/api/invites/${token}/verify_otp/`, { otp });
      setOtpVerified(true);
      setMessage("OTP verified. You can now set a password.");
    } catch (err) {
      setError(err.response?.data?.detail || "OTP verification failed.");
    }
  };

  const acceptInvite = async () => {
    setError("");
    setMessage("");
    try {
      const payload = { password };
      if (invite?.otp_required && !otpVerified) {
        payload.otp = otp;
      }
      await api.post(`/api/invites/${token}/accept/`, payload);
      setMessage("Invite accepted! Redirecting to login...");
      setTimeout(() => navigate("/"), 1500);
    } catch (err) {
      setError(err.response?.data?.detail || "Invite acceptance failed.");
    }
  };

  if (!invite) {
    return <p className="loading">Loading invite...</p>;
  }

  return (
    <div className="dashboard-container">
      <div className="card" style={{ maxWidth: "600px", margin: "auto" }}>
        <h2>Accept Invite</h2>
        <p>
          <strong>Name:</strong> {invite.full_name}
        </p>
        {invite.property && (
          <p>
            <strong>Property:</strong> {invite.property.title}
          </p>
        )}
        <p>
          <strong>Status:</strong> {invite.status}
        </p>

        {invite.status !== "PENDING" ? (
          <p className="error">This invite is no longer active.</p>
        ) : (
          <>
            {invite.otp_required && !otpVerified && (
              <div style={{ marginBottom: "16px" }}>
                <label>OTP</label>
                <input
                  type="text"
                  value={otp}
                  onChange={(e) => setOtp(e.target.value)}
                />
                <button type="button" className="btn-secondary" onClick={verifyOtp}>
                  Verify OTP
                </button>
              </div>
            )}

            <label>Set password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <button type="button" className="btn-primary" onClick={acceptInvite}>
              Accept Invite
            </button>
          </>
        )}

        {error && <p className="error">{error}</p>}
        {message && <p>{message}</p>}
      </div>
    </div>
  );
}
