import React, { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api from "../services/api";
import BackButton from "./BackButton";

export default function AcceptInvite() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    try {
      await api.post("/api/manager-invites/accept/", { token, username, password });
      navigate("/", { state: { message: "Invite accepted. Please login." } });
    } catch (err) {
      setError(JSON.stringify(err.response?.data || "Failed to accept invite"));
    }
  };

  return (
    <div className="dashboard-container">
      <BackButton />
      <h2>Accept Manager Invite</h2>
      {error && <p className="error">{error}</p>}
      <div className="card">
        <form onSubmit={submit}>
          <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Username" required />
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" required />
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="Confirm Password" required />
          <button type="submit">Accept Invite</button>
        </form>
      </div>
    </div>
  );
}
