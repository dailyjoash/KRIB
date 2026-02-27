import React, { useEffect, useState } from "react";
import api from "../services/api";
import BackButton from "./BackButton";

export default function UnitsNew() {
  const [properties, setProperties] = useState([]);
  const [units, setUnits] = useState([]);
  const [form, setForm] = useState({ property_id: "", unit_number: "", unit_type: "single", rent_amount: "", deposit: "" });
  const [error, setError] = useState("");

  const load = async () => {
    const [pRes, uRes] = await Promise.all([api.get('/api/properties/'), api.get('/api/units/')]);
    setProperties(pRes.data || []);
    setUnits(uRes.data || []);
  };

  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await api.post('/api/units/', form);
      setForm({ property_id: "", unit_number: "", unit_type: "single", rent_amount: "", deposit: "" });
      await load();
    } catch (err) {
      setError(JSON.stringify(err.response?.data || "Failed to add unit"));
    }
  };

  return (
    <div className="dashboard-container">
      <BackButton />
      <div className="card">
        <h3>Add Unit</h3>
        {error && <p className="error">{error}</p>}
        <form onSubmit={submit}>
          <select value={form.property_id} onChange={(e) => setForm({ ...form, property_id: e.target.value })} required>
            <option value="">Select property</option>
            {properties.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <input value={form.unit_number} onChange={(e) => setForm({ ...form, unit_number: e.target.value })} placeholder="Unit number" required />
          <select value={form.unit_type} onChange={(e) => setForm({ ...form, unit_type: e.target.value })}>
            <option value="single">Single</option><option value="bedsitter">Bedsitter</option><option value="1br">1BR</option><option value="2br">2BR</option><option value="other">Other</option>
          </select>
          <input value={form.rent_amount} onChange={(e) => setForm({ ...form, rent_amount: e.target.value })} placeholder="Rent amount" required />
          <input value={form.deposit} onChange={(e) => setForm({ ...form, deposit: e.target.value })} placeholder="Deposit" required />
          <button type="submit">Create Unit</button>
        </form>
      </div>
      <div className="card">
        <h3>Units</h3>
        <table><thead><tr><th>Property</th><th>Unit</th><th>Type</th><th>Rent</th><th>Status</th></tr></thead>
          <tbody>{units.map((u) => <tr key={u.id}><td>{u.property?.name}</td><td>{u.unit_number}</td><td>{u.unit_type}</td><td>{u.rent_amount}</td><td>{u.status}</td></tr>)}</tbody>
        </table>
      </div>
    </div>
  );
}
