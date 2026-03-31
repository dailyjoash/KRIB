import React, { useEffect, useMemo, useRef, useState } from "react";
import { Building2, DoorClosed, PlusSquare, Save, Trash2, UserMinus, UserPlus } from "lucide-react";
import { useLocation } from "react-router-dom";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { formatKES } from "../utils/format";
import StatusBadge from "./StatusBadge";
import { PageLayout, SectionCard } from "./ui";

export default function LandlordSetup() {
  const location = useLocation();
  const propertySectionRef = useRef(null);
  const unitSectionRef = useRef(null);

  const [name, setName] = useState("");
  const [locationName, setLocationName] = useState("");
  const [description, setDescription] = useState("");
  const [properties, setProperties] = useState([]);
  const [units, setUnits] = useState([]);
  const [managers, setManagers] = useState([]);
  const [selection, setSelection] = useState({});
  const [unitForm, setUnitForm] = useState({ property_id: "", unit_number: "", unit_type: "single", rent_amount: "", deposit: "" });
  const [propertyToDelete, setPropertyToDelete] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadData = async () => {
    try {
      const [propertyRes, unitRes, managersRes] = await Promise.all([
        api.get("/api/properties/"),
        api.get("/api/units/"),
        api.get("/api/users/?role=manager"),
      ]);
      const nextProperties = propertyRes.data || [];
      setProperties(nextProperties);
      setUnits(unitRes.data || []);
      setManagers(managersRes.data || []);
      setSelection(Object.fromEntries(nextProperties.map((property) => [property.id, property.manager?.id || ""])));
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load setup data."));
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    const section = new URLSearchParams(location.search).get("section");
    const target = section === "unit" ? unitSectionRef.current : propertySectionRef.current;
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [location.search]);

  const createProperty = async (event) => {
    event.preventDefault();
    setError("");
    setSuccess("");

    try {
      await api.post("/api/properties/", { name, location: locationName, description });
      setSuccess("Property created successfully.");
      setName("");
      setLocationName("");
      setDescription("");
      await loadData();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to create property."));
    }
  };

  const createUnit = async (event) => {
    event.preventDefault();
    setError("");
    setSuccess("");

    try {
      await api.post("/api/units/", unitForm);
      setSuccess("Unit created successfully.");
      setUnitForm({ property_id: "", unit_number: "", unit_type: "single", rent_amount: "", deposit: "" });
      await loadData();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to add unit."));
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

  const unassignManager = async (propertyId) => {
    setError("");
    setSuccess("");

    try {
      await api.patch(`/api/properties/${propertyId}/`, { manager_id: null });
      setSuccess("Manager removed. You now manage this property directly.");
      await loadData();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to unassign manager."));
    }
  };

  const confirmDeleteProperty = async () => {
    if (!propertyToDelete) return;
    setError("");
    setSuccess("");

    try {
      await api.delete(`/api/properties/${propertyToDelete.id}/`);
      setSuccess("Property deleted successfully.");
      setPropertyToDelete(null);
      await loadData();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to delete property."));
    }
  };

  const occupiedCount = useMemo(() => units.filter((unit) => unit.status === "occupied").length, [units]);
  const formatUnitTypeLabel = (value = "") => {
    if (value === "1br") return "1BR";
    if (value === "2br") return "2BR";
    if (!value) return "-";
    return value.charAt(0).toUpperCase() + value.slice(1);
  };

  return (
    <PageLayout
      variant="executive"
      kicker="Landlord Setup"
      title="Properties"
      chip={`${properties.length} properties / ${units.length} units`}
    >
      {error ? <p className="error">{error}</p> : null}
      {success ? <p className="success">{success}</p> : null}

      <SectionCard icon={Building2} title="Create Property">
        <div ref={propertySectionRef} />
        <form className="resident-form-grid" onSubmit={createProperty}>
          <label className="resident-field">
            <span>Property name</span>
            <input value={name} onChange={(event) => setName(event.target.value)} placeholder="KRIB Heights" required />
          </label>
          <label className="resident-field">
            <span>Location</span>
            <input value={locationName} onChange={(event) => setLocationName(event.target.value)} placeholder="Westlands, Nairobi" required />
          </label>
          <label className="resident-field" style={{ gridColumn: "1 / -1" }}>
            <span>Description</span>
            <textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Short summary of the property and its appeal." rows="4" />
          </label>
          <button className="resident-primary-btn" type="submit">
            <Save size={16} />
            <span>Create Property</span>
          </button>
        </form>
      </SectionCard>

      <SectionCard icon={PlusSquare} title="Add Unit">
        <div ref={unitSectionRef} />
        <form className="resident-form-grid" onSubmit={createUnit}>
          <label className="resident-field">
            <span>Property</span>
            <select value={unitForm.property_id} onChange={(event) => setUnitForm({ ...unitForm, property_id: event.target.value })} required>
              <option value="">Select property</option>
              {properties.map((property) => (
                <option key={property.id} value={property.id}>
                  {property.name}
                </option>
              ))}
            </select>
          </label>
          <label className="resident-field">
            <span>Unit number</span>
            <input value={unitForm.unit_number} onChange={(event) => setUnitForm({ ...unitForm, unit_number: event.target.value })} placeholder="A-01" required />
          </label>
          <label className="resident-field">
            <span>Unit type</span>
            <select value={unitForm.unit_type} onChange={(event) => setUnitForm({ ...unitForm, unit_type: event.target.value })}>
              <option value="single">Single</option>
              <option value="bedsitter">Bedsitter</option>
              <option value="1br">1BR</option>
              <option value="2br">2BR</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label className="resident-field">
            <span>Monthly rent</span>
            <input value={unitForm.rent_amount} onChange={(event) => setUnitForm({ ...unitForm, rent_amount: event.target.value })} inputMode="decimal" required />
          </label>
          <label className="resident-field">
            <span>Deposit</span>
            <input value={unitForm.deposit} onChange={(event) => setUnitForm({ ...unitForm, deposit: event.target.value })} inputMode="decimal" required />
          </label>
          <button className="resident-primary-btn" type="submit">
            <PlusSquare size={16} />
            <span>Create Unit</span>
          </button>
        </form>
      </SectionCard>

      <SectionCard title="My Property">
        {properties.length === 0 ? (
          <p className="resident-helper-text">No properties have been added yet.</p>
        ) : (
          <div className="resident-property-grid">
            {properties.map((property) => (
              <article className="resident-section-card resident-property-card" key={property.id}>
                <div className="resident-section-head">
                  <div className="resident-title-row">
                    <Building2 size={18} />
                    <h3>{property.name}</h3>
                  </div>
                  <StatusBadge status={property.manager ? "assigned" : "self managed"} />
                </div>
                <div className="resident-property-meta">
                  <div className="resident-profile-item">
                    <span>Location</span>
                    <strong>{property.location || "-"}</strong>
                  </div>
                  <div className="resident-profile-item">
                    <span>Manager</span>
                    <strong>{property.manager?.username || "Landlord managing directly"}</strong>
                  </div>
                </div>
                <div className="resident-property-controls">
                  <label className="resident-field resident-property-select">
                    <span>Assign manager</span>
                    <select value={selection[property.id] || ""} onChange={(event) => setSelection({ ...selection, [property.id]: event.target.value })}>
                      <option value="">Select manager</option>
                      {managers.map((manager) => (
                        <option key={manager.id} value={manager.id}>
                          {manager.username}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="resident-form-actions resident-property-actions">
                    <button className="btn btn-primary" type="button" onClick={() => assignManager(property.id)}>
                      <UserPlus size={16} />
                      <span>Assign</span>
                    </button>
                    {property.manager ? (
                      <button className="btn" type="button" onClick={() => unassignManager(property.id)}>
                        <UserMinus size={16} />
                        <span>Unassign</span>
                      </button>
                    ) : null}
                    <button className="btn" type="button" onClick={() => setPropertyToDelete({ id: property.id, name: property.name })}>
                      <Trash2 size={16} />
                      <span>Delete</span>
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </SectionCard>

      {propertyToDelete ? (
        <div className="resident-modal-backdrop" role="presentation" onClick={() => setPropertyToDelete(null)}>
          <div className="resident-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="delete-property-title" onClick={(event) => event.stopPropagation()}>
            <div className="resident-confirm-copy">
              <h3 id="delete-property-title">Delete property?</h3>
              <p>{propertyToDelete.name} will be removed together with its units, leases, and related records. This action cannot be undone.</p>
            </div>
            <div className="resident-form-actions resident-confirm-actions">
              <button className="btn" type="button" onClick={() => setPropertyToDelete(null)}>
                Cancel
              </button>
              <button className="btn btn-primary" type="button" onClick={confirmDeleteProperty}>
                <Trash2 size={16} />
                <span>Confirm Delete</span>
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <SectionCard icon={DoorClosed} title="Unit Directory" action={<span className="resident-chip">{occupiedCount} occupied</span>}>
        {units.length === 0 ? (
          <p className="resident-helper-text">No units available yet.</p>
        ) : (
          <div className="resident-unit-grid">
            {units.map((unit) => (
              <article className="resident-unit-card" key={unit.id}>
                <div className="resident-unit-icon">
                  <DoorClosed size={18} />
                </div>
                <div className="resident-unit-main">
                  <h4>{unit.property?.name || "Property"} / {unit.unit_number}</h4>
                  <p>{formatUnitTypeLabel(unit.unit_type)} / Rent {formatKES(unit.rent_amount)} / Deposit {formatKES(unit.deposit)}</p>
                </div>
                <div className="resident-unit-side">
                  <span className={`resident-unit-status resident-unit-status-${unit.status || "unknown"}`}>
                    {unit.status ? unit.status.charAt(0).toUpperCase() + unit.status.slice(1) : "Unknown"}
                  </span>
                </div>
              </article>
            ))}
          </div>
        )}
      </SectionCard>
    </PageLayout>
  );
}
