import React, { useEffect, useState } from "react";
import api from "../services/api";
import BackButton from "./BackButton";

export default function AddProperty() {
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
  const [properties, setProperties] = useState([]);
  const [managers, setManagers] = useState([]);
  const [selection, setSelection] = useState({});
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadData = async () => {
    try {
      const [propRes, managersRes] = await Promise.all([
        api.get("/api/properties/"),
        api.get("/api/users/?role=manager"),
      ]);
      setProperties(propRes.data || []);
      setManagers(managersRes.data || []);
    } catch {
      setError("Failed to load properties/managers");
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const createProperty = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");

    try {
      await api.post("/api/properties/", { name, location, description });
      setSuccess("Property created successfully!");
      setName("");
      setLocation("");
      setDescription("");
      await loadData();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to create property");
    }
  };

  const assignManager = async (propertyId) => {
    const managerId = selection[propertyId];
    if (!managerId) {
      setError("Please select a manager");
      return;
    }

    setError("");
    setSuccess("");

    try {
      await api.patch(`/api/properties/${propertyId}/`, { manager_id: managerId });
      setSuccess("Manager assigned successfully!");
      await loadData();
    } catch (err) {
      setError(err.response?.data?.detail || JSON.stringify(err.response?.data || "Failed to assign manager"));
    }
  };

  return (
    <div className="dashboard-container">
      <BackButton />
      <h2>Property Management</h2>

      {error && <p className="error">{error}</p>}
      {success && <p className="success">{success}</p>}

      <div className="card">
        <h3>Add New Property</h3>
        <form onSubmit={createProperty}>
          <div style={{ display: "flex", gap: "10px", flexDirection: "column", maxWidth: "400px" }}>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Property name" required />
            <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Location" required />
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description" rows="3" />
            <button type="submit">Create Property</button>
          </div>
        </form>
      </div>

      <div className="card">
        <h3>Existing Properties</h3>
        {properties.length === 0 ? (
          <p>No properties found.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: "8px" }}>Name</th>
                <th style={{ textAlign: "left", padding: "8px" }}>Location</th>
                <th style={{ textAlign: "left", padding: "8px" }}>Manager</th>
                <th style={{ textAlign: "left", padding: "8px" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {properties.map((p) => (
                <tr key={p.id}>
                  <td style={{ padding: "8px" }}>{p.name}</td>
                  <td style={{ padding: "8px" }}>{p.location}</td>
                  <td style={{ padding: "8px" }}>{p.manager?.username || "Not assigned"}</td>
                  <td style={{ padding: "8px" }}>
                    <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                      <select value={selection[p.id] || ""} onChange={(e) => setSelection({ ...selection, [p.id]: e.target.value })}>
                        <option value="">Select manager</option>
                        {managers.map((m) => <option key={m.id} value={m.id}>{m.username}</option>)}
                      </select>
                      <button onClick={() => assignManager(p.id)}>Assign</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
