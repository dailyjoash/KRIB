import React, { useEffect, useMemo, useState } from "react";
import { Building2, Save, UserPlus } from "lucide-react";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import StatusBadge from "./StatusBadge";
import { PageLayout, SectionCard, StatCard } from "./ui";

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
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load properties and managers."));
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const createProperty = async (event) => {
    event.preventDefault();
    setError("");
    setSuccess("");

    try {
      await api.post("/api/properties/", { name, location, description });
      setSuccess("Property created successfully.");
      setName("");
      setLocation("");
      setDescription("");
      await loadData();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to create property."));
    }
  };

  const assignManager = async (propertyId) => {
    const managerId = selection[propertyId];
    if (!managerId) {
      setError("Please select a manager.");
      return;
    }

    setError("");
    setSuccess("");
    try {
      await api.patch(`/api/properties/${propertyId}/`, { manager_id: managerId });
      setSuccess("Manager assigned successfully.");
      await loadData();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to assign manager."));
    }
  };

  const assignedCount = useMemo(
    () => properties.filter((property) => property.manager).length,
    [properties]
  );

  return (
    <PageLayout
      variant="executive"
      kicker="Landlord Setup"
      title="Properties"
      chip={`${properties.length} properties / ${managers.length} managers`}
    >
      {error ? <p className="error">{error}</p> : null}
      {success ? <p className="success">{success}</p> : null}

      <section className="resident-hero-grid">
        <StatCard variant="blue" title="Total Properties" subtitle="Your active portfolio" value={String(properties.length).padStart(2, "0")} />
        <StatCard variant="purple" title="Manager Ready" subtitle="Available manager accounts" value={String(managers.length).padStart(2, "0")} />
        <StatCard variant="mint" title="Assigned" subtitle="Properties with managers" value={String(assignedCount).padStart(2, "0")} />
      </section>

      <SectionCard icon={Building2} title="Create New Property">
        <p className="resident-helper-text">Keep the entry short and structured so it is easy to scan from a phone later.</p>
        <form className="resident-form-grid" onSubmit={createProperty}>
          <label className="resident-field">
            <span>Property name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label className="resident-field">
            <span>Location</span>
            <input value={location} onChange={(e) => setLocation(e.target.value)} required />
          </label>
          <label className="resident-field" style={{ gridColumn: "1 / -1" }}>
            <span>Description</span>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows="4" />
          </label>
          <button className="resident-primary-btn" type="submit">
            <Save size={16} />
            <span>Create Property</span>
          </button>
        </form>
      </SectionCard>

      <SectionCard title="Property Directory">
        {properties.length === 0 ? (
          <p className="resident-helper-text">No properties have been added yet.</p>
        ) : (
          <div className="resident-card-grid">
            {properties.map((property) => (
              <article className="resident-section-card" key={property.id}>
                <div className="resident-section-head">
                  <div className="resident-title-row">
                    <Building2 size={18} />
                    <h3>{property.name}</h3>
                  </div>
                  <StatusBadge status={property.manager ? "assigned" : "pending"} />
                </div>
                <div className="resident-profile-columns">
                  <div className="resident-profile-item">
                    <span>Location</span>
                    <strong>{property.location || "-"}</strong>
                  </div>
                  <div className="resident-profile-item">
                    <span>Manager</span>
                    <strong>{property.manager?.username || "Not assigned"}</strong>
                  </div>
                </div>
                {property.description ? <p className="resident-helper-text">{property.description}</p> : null}
                <div className="resident-form-actions">
                  <select value={selection[property.id] || ""} onChange={(e) => setSelection({ ...selection, [property.id]: e.target.value })} aria-label={`Assign manager for ${property.name}`}>
                    <option value="" hidden></option>
                    {managers.map((manager) => (
                      <option key={manager.id} value={manager.id}>{manager.username}</option>
                    ))}
                  </select>
                  <button className="btn btn-primary" type="button" onClick={() => assignManager(property.id)}>
                    <UserPlus size={16} />
                    <span>Assign</span>
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </SectionCard>
    </PageLayout>
  );
}
