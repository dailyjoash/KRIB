import React, { useState } from "react";
import api from "../services/api";
import BackButton from "./BackButton";

export default function InviteManager() {
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [inviteLink, setInviteLink] = useState("");
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const res = await api.post("/api/manager-invites/", { email, phone });
      setInviteLink(res.data.invite_link || "");
    } catch (err) {
      setError(JSON.stringify(err.response?.data || "Failed to create invite"));
    }
  };

  return (
    <div className="dashboard-container">
      <BackButton />
      <h2>Invite Manager</h2>
      {error && <p className="error">{error}</p>}
      <div className="card">
        <form onSubmit={submit}>
          <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email (optional)" />
          <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Phone (optional)" />
          <button type="submit">Create Invite</button>
        </form>
        {inviteLink && (
          <p>
            Invite link: <code>{inviteLink}</code>{" "}
            <button onClick={() => navigator.clipboard.writeText(inviteLink)}>Copy</button>
          </p>
        )}
      </div>
    </div>
  );
}
