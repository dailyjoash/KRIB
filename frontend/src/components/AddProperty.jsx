import React, { useEffect, useState } from "react";
import { Save, UserPlus } from "lucide-react";
import api from "../services/api";

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
      {error && <p className="error">{error}</p>}
      {success && <p className="success">{success}</p>}

      <div className="card">
        <h3>Add New Property</h3>
        <form onSubmit={createProperty}>
          <div className="form-stack">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Property name" required />
            <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Location" required />
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description" rows="3" />
            <button type="submit"><Save size={16} /> Create Property</button>
          </div>
        </form>
      </div>

      <div className="card">
        <h3>Existing Properties</h3>
        {properties.length === 0 ? (
          <p>No properties found.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Location</th>
                <th>Manager</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {properties.map((p) => (
                <tr key={p.id}>
                  <td>{p.name}</td>
                  <td>{p.location}</td>
                  <td>{p.manager?.username || "Not assigned"}</td>
                  <td>
                    <div className="inline-actions">
                      <select value={selection[p.id] || ""} onChange={(e) => setSelection({ ...selection, [p.id]: e.target.value })}>
                        <option value="">Select manager</option>
                        {managers.map((m) => <option key={m.id} value={m.id}>{m.username}</option>)}
                      </select>
                      <button type="button" onClick={() => assignManager(p.id)}><UserPlus size={16} /> Assign</button>
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
