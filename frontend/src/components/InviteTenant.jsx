import React, { useEffect, useState } from "react";
import api from "../services/api";

export default function InviteTenant() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [propertyId, setPropertyId] = useState("");
  const [sendOtp, setSendOtp] = useState(false);
  const [properties, setProperties] = useState([]);
  const [inviteLink, setInviteLink] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const loadProperties = async () => {
      try {
        const res = await api.get("/api/properties/");
        setProperties(res.data || []);
      } catch (err) {
        console.error("Failed to load properties:", err);
      }
    };
    loadProperties();
  }, []);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setInviteLink("");
    if (!email && !phone) {
      setError("Email or phone is required.");
      return;
    }
    try {
      const payload = {
        full_name: fullName,
        email: email || null,
        phone: phone || null,
        property: propertyId || null,
        send_otp: sendOtp,
      };
      const res = await api.post("/api/invites/", payload);
      const token = res.data?.token;
      if (token) {
        const link = `${window.location.origin}/invite/${token}`;
        setInviteLink(link);
      }
    } catch (err) {
      console.error("Invite failed:", err);
      setError(err.response?.data?.detail || "Failed to create invite.");
    }
  };

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(inviteLink);
    } catch (err) {
      console.error("Copy failed:", err);
    }
  };

  return (
    <div className="dashboard-container">
      <div className="card" style={{ maxWidth: "600px", margin: "auto" }}>
        <h2>Invite Tenant</h2>
        <form onSubmit={handleSubmit}>
          <label>Full name</label>
          <input
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
          />

          <label>Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />

          <label>Phone</label>
          <input
            type="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />

          <label>Property (optional)</label>
          <select value={propertyId} onChange={(e) => setPropertyId(e.target.value)}>
            <option value="">No property</option>
            {properties.map((property) => (
              <option key={property.id} value={property.id}>
                {property.title}
              </option>
            ))}
          </select>

          <label style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <input
              type="checkbox"
              checked={sendOtp}
              onChange={(e) => setSendOtp(e.target.checked)}
            />
            Require OTP verification
          </label>

          {error && <p className="error">{error}</p>}

          <button type="submit" className="btn-primary">
            Create Invite
          </button>
        </form>

        {inviteLink && (
          <div style={{ marginTop: "16px" }}>
            <p>Invite link:</p>
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <input type="text" value={inviteLink} readOnly />
              <button type="button" className="btn-secondary" onClick={copyLink}>
                Copy
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
