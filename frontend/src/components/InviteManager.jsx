import React, { useState } from "react";
import api from "../services/api";

export default function InviteManager() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [inviteLink, setInviteLink] = useState("");
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const res = await api.post("/api/manager-invites/", { name, email, phone });
      setInviteLink(res.data.invite_link || "");
    } catch (err) {
      setError(JSON.stringify(err.response?.data || "Failed to create invite"));
    }
  };

  return (
    <div className="dashboard-container">
      <h2>Invite Manager</h2>
      {error && <p className="error">{error}</p>}
      <div className="card">
        <form onSubmit={submit}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Manager name" required />
          <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Phone number" required />
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Personal email (optional)" />
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
