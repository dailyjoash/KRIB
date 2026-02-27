import React, { useEffect, useState } from "react";
import api from "../services/api";

export default function LeasesNew() {
  const [units, setUnits] = useState([]);
  const [tenants, setTenants] = useState([]);
  const [leases, setLeases] = useState([]);
  const [form, setForm] = useState({
    unit_id: "",
    tenant_id: "",
    start_date: ""
  });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const [uRes, tRes, lRes] = await Promise.all([
        api.get("/api/units/"),
        api.get("/api/tenants/"),
        api.get("/api/leases/"),
      ]);
      setUnits(uRes.data || []);
      setTenants(tRes.data || []);
      setLeases(lRes.data || []);
      setError("");
    } catch (err) {
      setError("Failed to load data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setForm(prev => ({ ...prev, [name]: value }));
  };

  const createLease = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    setLoading(true);

    try {
      const selectedUnit = units.find((u) => String(u.id) === String(form.unit_id));

      if (!selectedUnit) {
        throw new Error("Selected unit not found");
      }

      await api.post("/api/leases/", {
        unit_id: form.unit_id,
        tenant_id: form.tenant_id,
        start_date: form.start_date,
        status: "active",
        due_day: 15,
        rent_amount: selectedUnit.rent_amount,
      });

      setSuccess("Lease created successfully!");
      setForm({ unit_id: "", tenant_id: "", start_date: "" });
      await loadData(); // Refresh the leases list
    } catch (err) {
      const errorMessage = err.response?.data
        ? JSON.stringify(err.response.data)
        : err.message || "Failed to create lease";
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  if (loading && !units.length) {
    return <div className="dashboard-container">Loading...</div>;
  }

  return (
    <div className="dashboard-container">
      <h2>Lease Management</h2>

      {error && <p className="error">{error}</p>}
      {success && <p className="success">{success}</p>}

      {/* Create Lease Form */}
      <div className="card">
        <h3>Create New Lease</h3>
        <form onSubmit={createLease}>
          <div style={{ display: "flex", gap: "10px", flexDirection: "column", maxWidth: "400px" }}>
            <select
              name="unit_id"
              value={form.unit_id}
              onChange={handleInputChange}
              required
              disabled={loading}
            >
              <option value="">Select Available Unit</option>
              {units
                .filter(u => u.status === 'available' || u.status === 'vacant')
                .map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.property?.name} / Unit {u.unit_number} - ${u.rent_amount}/mo ({u.status})
                  </option>
                ))}
            </select>

            <select
              name="tenant_id"
              value={form.tenant_id}
              onChange={handleInputChange}
              required
              disabled={loading}
            >
              <option value="">Select Tenant</option>
              {tenants.map((t) => (
                <option key={t.id} value={t.user?.id}>
                  {t.user?.username} ({t.user?.email})
                </option>
              ))}
            </select>

            <input
              type="date"
              name="start_date"
              value={form.start_date}
              onChange={handleInputChange}
              required
              disabled={loading}
              min={new Date().toISOString().split('T')[0]} // Can't start in the past
            />

            <button type="submit" disabled={loading}>
              {loading ? "Creating..." : "Create Lease"}
            </button>
          </div>
        </form>
      </div>

      {/* Existing Leases List */}
      <div className="card">
        <h3>Current Leases</h3>
        {leases.length === 0 ? (
          <p>No leases found.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: "8px" }}>Tenant</th>
                <th style={{ textAlign: "left", padding: "8px" }}>Property / Unit</th>
                <th style={{ textAlign: "right", padding: "8px" }}>Monthly Rent</th>
                <th style={{ textAlign: "left", padding: "8px" }}>Status</th>
                <th style={{ textAlign: "left", padding: "8px" }}>Start Date</th>
                <th style={{ textAlign: "left", padding: "8px" }}>Due Day</th>
              </tr>
            </thead>
            <tbody>
              {leases.map((l) => (
                <tr key={l.id}>
                  <td style={{ padding: "8px" }}>{l.tenant?.username || 'N/A'}</td>
                  <td style={{ padding: "8px" }}>
                    {l.unit?.property?.name || 'Unknown'} / Unit {l.unit?.unit_number || 'N/A'}
                  </td>
                  <td style={{ padding: "8px", textAlign: "right" }}>
                    ${Number(l.rent_amount).toFixed(2)}
                  </td>
                  <td style={{ padding: "8px" }}>
                    <span className={`status-${l.status?.toLowerCase()}`}>
                      {l.status}
                    </span>
                  </td>
                  <td style={{ padding: "8px" }}>
                    {l.start_date ? new Date(l.start_date).toLocaleDateString() : 'N/A'}
                  </td>
                  <td style={{ padding: "8px" }}>{l.due_day || 15}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}