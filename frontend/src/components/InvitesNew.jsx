import React, { useEffect, useState } from "react";
import api from "../services/api";

export default function InvitesNew() {
  const [properties, setProperties] = useState([]);
  const [units, setUnits] = useState([]);
  const [invites, setInvites] = useState([]);
  const [createdLink, setCreatedLink] = useState("");
  const [form, setForm] = useState({ full_name: "", email: "", phone: "", property: "", unit: "", expires_at: "" });
  const [error, setError] = useState("");

  const load = async () => {
    const [pRes, uRes, iRes] = await Promise.all([api.get('/api/properties/'), api.get('/api/units/'), api.get('/api/invites/')]);
    setProperties(pRes.data || []);
    setUnits(uRes.data || []);
    setInvites(iRes.data || []);
  };

  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const payload = { ...form };
      if (!payload.property) delete payload.property;
      if (!payload.unit) delete payload.unit;
      const res = await api.post('/api/invites/', payload);
      setCreatedLink(res.data.invite_link || "");
      await load();
    } catch (err) {
      setError(JSON.stringify(err.response?.data || "Failed to invite tenant"));
    }
  };

  const copy = async (text) => { try { await navigator.clipboard.writeText(text); } catch {} };

  return (
    <div className="dashboard-container">
      <div className="card">
        <h3>Invite Tenant</h3>
        {error && <p className="error">{error}</p>}
        {createdLink && <p>Invite link: <code>{createdLink}</code> <button onClick={() => copy(createdLink)}>Copy</button></p>}
        <form onSubmit={submit}>
          <input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} placeholder="Full name" required />
          <input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="Email (optional)" />
          <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="Phone (optional)" />
          <select value={form.property} onChange={(e) => setForm({ ...form, property: e.target.value })}><option value="">Optional property</option>{properties.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
          <select value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })}><option value="">Optional unit</option>{units.map((u) => <option key={u.id} value={u.id}>{u.property?.name} / {u.unit_number}</option>)}</select>
          <input type="datetime-local" value={form.expires_at} onChange={(e) => setForm({ ...form, expires_at: e.target.value })} required />
          <button type="submit">Send Invite</button>
        </form>
      </div>

      <div className="card">
        <h3>Invites</h3>
        <table><thead><tr><th>Name</th><th>Status</th><th>Property</th><th>Unit</th><th>Token</th></tr></thead>
          <tbody>{invites.map((i) => <tr key={i.id}><td>{i.full_name}</td><td>{i.status}</td><td>{i.property || '-'}</td><td>{i.unit || '-'}</td><td><code>{i.token}</code></td></tr>)}</tbody>
        </table>
      </div>
    </div>
  );
}
