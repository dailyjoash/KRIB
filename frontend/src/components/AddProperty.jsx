import React, { useEffect, useState } from "react";
import api from "../services/api";

export default function AddProperty() {
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
 codex/implement-full-krib-rental-workflow-prps6l
  const [managerId, setManagerId] = useState("");
  const [properties, setProperties] = useState([]);
  const [error, setError] = useState("");

  const load = async () => {
    const res = await api.get("/api/properties/");
    setProperties(res.data || []);
  };

  useEffect(() => { load(); }, []);

  const createProperty = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await api.post("/api/properties/", { name, location, description });
      setName(""); setLocation(""); setDescription("");
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to create property");
    }
  };

  const assignManager = async (propertyId) => {
    setError("");
    try {
      await api.patch(`/api/properties/${propertyId}/`, { manager_id: managerId || null });
      setManagerId("");
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || JSON.stringify(err.response?.data || "Failed to assign manager"));
    }
  };

  return (
    <div className="dashboard-container">
      <div className="card">
        <h3>Add Property</h3>
        {error && <p className="error">{error}</p>}
        <form onSubmit={createProperty}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Property name" required />
          <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Location" required />
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description" />
          <button type="submit">Create Property</button>
        </form>
      </div>

      <div className="card">
        <h3>Properties</h3>
        <table>
          <thead><tr><th>Name</th><th>Location</th><th>Manager</th><th>Assign manager user ID</th></tr></thead>
          <tbody>
            {properties.map((p) => (
              <tr key={p.id}>
                <td>{p.name}</td>
                <td>{p.location}</td>
                <td>{p.manager?.username || "Landlord default"}</td>
                <td>
                  <input value={managerId} onChange={(e) => setManagerId(e.target.value)} placeholder="manager user id" />
                  <button onClick={() => assignManager(p.id)}>Save</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>


  const submit = async (e) => {
    e.preventDefault();
    await api.post("/api/properties/", { name, location, description });
    setName("");
    setLocation("");
    setDescription("");
  };

  return (
    <div className="card">
      <h3>Add Property</h3>
      <form onSubmit={submit}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" required />
        <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Location" required />
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description" />
        <button type="submit">Create</button>
      </form>
 master
    </div>
  );
}
