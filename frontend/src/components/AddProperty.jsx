import React, { useEffect, useState } from "react";
import api from "../services/api";

export default function AddProperty() {
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
  const [managerId, setManagerId] = useState("");
  const [properties, setProperties] = useState([]);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadProperties = async () => {
    try {
      const res = await api.get("/api/properties/");
      setProperties(res.data || []);
    } catch (err) {
      setError("Failed to load properties");
    }
  };

  useEffect(() => {
    loadProperties();
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
      await loadProperties();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to create property");
    }
  };

  const assignManager = async (propertyId) => {
    if (!managerId) {
      setError("Please enter a manager user ID");
      return;
    }

    setError("");
    setSuccess("");

    try {
      await api.patch(`/api/properties/${propertyId}/`, { manager_id: managerId });
      setSuccess("Manager assigned successfully!");
      setManagerId("");
      await loadProperties();
    } catch (err) {
      setError(err.response?.data?.detail || JSON.stringify(err.response?.data || "Failed to assign manager"));
    }
  };

  return (
    <div className="dashboard-container">
      <h2>Property Management</h2>

      {error && <p className="error">{error}</p>}
      {success && <p className="success">{success}</p>}

      {/* Add Property Form */}
      <div className="card">
        <h3>Add New Property</h3>
        <form onSubmit={createProperty}>
          <div style={{ display: "flex", gap: "10px", flexDirection: "column", maxWidth: "400px" }}>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Property name"
              required
            />
            <input
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Location"
              required
            />
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Description"
              rows="3"
            />
            <button type="submit">Create Property</button>
          </div>
        </form>
      </div>

      {/* Properties List */}
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
                  <td style={{ padding: "8px" }}>
                    {p.manager?.username || "Not assigned (managed by landlord)"}
                  </td>
                  <td style={{ padding: "8px" }}>
                    <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                      <input
                        value={managerId}
                        onChange={(e) => setManagerId(e.target.value)}
                        placeholder="Manager user ID"
                        style={{ width: "150px", padding: "4px" }}
                      />
                      <button onClick={() => assignManager(p.id)}>
                        Assign
                      </button>
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