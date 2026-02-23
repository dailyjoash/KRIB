import React, { useEffect, useState } from "react";
import api from "../services/api";

export default function LeasesNew() {
  const [units, setUnits] = useState([]);
  const [unitId, setUnitId] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [startDate, setStartDate] = useState("");

  useEffect(() => {
    api.get("/api/units/").then((res) => setUnits(res.data));
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    await api.post("/api/leases/", { unit_id: unitId, tenant_id: tenantId, start_date: startDate });
    alert("Lease created");
  };

  return (
    <div className="card">
      <h3>Create Lease</h3>
      <form onSubmit={submit}>
        <select value={unitId} onChange={(e) => setUnitId(e.target.value)} required>
          <option value="">Select Unit</option>
          {units.map((u) => (
            <option key={u.id} value={u.id}>{u.property.name} / {u.unit_number} ({u.status})</option>
          ))}
        </select>
        <input value={tenantId} onChange={(e) => setTenantId(e.target.value)} placeholder="Tenant user ID" required />
        <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} required />
        <button type="submit">Create Lease</button>
      </form>
    </div>
  );
}
