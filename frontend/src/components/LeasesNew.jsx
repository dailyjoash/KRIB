import React, { useEffect, useState } from "react";
import api from "../services/api";

export default function LeasesNew() {
  const [units, setUnits] = useState([]);
  const [tenants, setTenants] = useState([]);
  const [leases, setLeases] = useState([]);
  const [form, setForm] = useState({ unit_id: "", tenant_id: "", start_date: "" });
  const [error, setError] = useState("");

  const load = async () => {
    const [uRes, tRes, lRes] = await Promise.all([
      api.get("/api/units/"),
      api.get("/api/tenants/"),
      api.get("/api/leases/"),
    ]);
    setUnits(uRes.data || []);
    setTenants(tRes.data || []);
    setLeases(lRes.data || []);
  };

  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const selectedUnit = units.find((u) => String(u.id) === String(form.unit_id));
      await api.post("/api/leases/", {
        ...form,
        status: "active",
        due_day: 15,
        rent_amount: selectedUnit?.rent_amount,
      });
      setForm({ unit_id: "", tenant_id: "", start_date: "" });
      await load();
    } catch (err) {
      setError(JSON.stringify(err.response?.data || "Failed to create lease"));
    }
  };

  return (
    <div className="dashboard-container">
      <div className="card">
        <h3>Create Lease</h3>
        {error && <p className="error">{error}</p>}
        <form onSubmit={submit}>
          <select value={form.unit_id} onChange={(e) => setForm({ ...form, unit_id: e.target.value })} required>
            <option value="">Select Unit</option>
            {units.map((u) => (
              <option key={u.id} value={u.id}>{u.property?.name} / {u.unit_number} ({u.status})</option>
            ))}
          </select>
          <select value={form.tenant_id} onChange={(e) => setForm({ ...form, tenant_id: e.target.value })} required>
            <option value="">Select Tenant</option>
            {tenants.map((t) => (
              <option key={t.id} value={t.user.id}>{t.user.username}</option>
            ))}
          </select>
          <input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} required />
          <button type="submit">Create Lease</button>
        </form>
      </div>

      <div className="card">
        <h3>Leases</h3>
        <table><thead><tr><th>Tenant</th><th>Unit</th><th>Rent</th><th>Status</th><th>Start Date</th></tr></thead>
          <tbody>{leases.map((l) => <tr key={l.id}><td>{l.tenant?.username}</td><td>{l.unit?.property?.name} / {l.unit?.unit_number}</td><td>{l.rent_amount}</td><td>{l.status}</td><td>{l.start_date}</td></tr>)}</tbody>
        </table>
      </div>
    </div>
  );
}
