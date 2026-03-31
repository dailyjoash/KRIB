import React, { useEffect, useMemo, useState } from "react";
import { DoorClosed, PlusSquare } from "lucide-react";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { formatKES } from "../utils/format";
import StatusBadge from "./StatusBadge";
import { PageLayout, SectionCard, StatCard } from "./ui";

export default function UnitsNew() {
  const [properties, setProperties] = useState([]);
  const [units, setUnits] = useState([]);
  const [form, setForm] = useState({ property_id: "", unit_number: "", unit_type: "single", rent_amount: "", deposit: "" });
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const [propertyRes, unitRes] = await Promise.all([api.get("/api/properties/"), api.get("/api/units/")]);
      setProperties(propertyRes.data || []);
      setUnits(unitRes.data || []);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load units."));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    try {
      await api.post("/api/units/", form);
      setForm({ property_id: "", unit_number: "", unit_type: "single", rent_amount: "", deposit: "" });
      await load();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to add unit."));
    }
  };

  const occupied = useMemo(() => units.filter((unit) => unit.status === "occupied").length, [units]);

  return (
    <PageLayout
      variant="executive"
      kicker="Inventory"
      title="Units"
      chip={`${units.length} units across ${properties.length} properties`}
    >
      {error ? <p className="error">{error}</p> : null}

      <section className="resident-hero-grid">
        <StatCard variant="blue" title="Total Units" subtitle="All created units" value={String(units.length).padStart(2, "0")} />
        <StatCard variant="purple" title="Occupied" subtitle="Currently leased" value={String(occupied).padStart(2, "0")} />
        <StatCard variant="mint" title="Vacant" subtitle="Available to lease" value={String(Math.max(units.length - occupied, 0)).padStart(2, "0")} />
      </section>

      <SectionCard icon={PlusSquare} title="Add Unit">
        <form className="resident-form-grid" onSubmit={submit}>
          <label className="resident-field">
            <span>Property</span>
            <select value={form.property_id} onChange={(e) => setForm({ ...form, property_id: e.target.value })} required>
              <option value="">Select property</option>
              {properties.map((property) => <option key={property.id} value={property.id}>{property.name}</option>)}
            </select>
          </label>
          <label className="resident-field">
            <span>Unit number</span>
            <input value={form.unit_number} onChange={(e) => setForm({ ...form, unit_number: e.target.value })} placeholder="A-01" required />
          </label>
          <label className="resident-field">
            <span>Unit type</span>
            <select value={form.unit_type} onChange={(e) => setForm({ ...form, unit_type: e.target.value })}>
              <option value="single">Single</option>
              <option value="bedsitter">Bedsitter</option>
              <option value="1br">1BR</option>
              <option value="2br">2BR</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label className="resident-field">
            <span>Monthly rent</span>
            <input value={form.rent_amount} onChange={(e) => setForm({ ...form, rent_amount: e.target.value })} inputMode="decimal" required />
          </label>
          <label className="resident-field">
            <span>Deposit</span>
            <input value={form.deposit} onChange={(e) => setForm({ ...form, deposit: e.target.value })} inputMode="decimal" required />
          </label>
          <button className="resident-primary-btn" type="submit">
            <PlusSquare size={16} />
            <span>Create Unit</span>
          </button>
        </form>
      </SectionCard>

      <SectionCard icon={DoorClosed} title="Unit Directory">
        {units.length === 0 ? (
          <p className="resident-helper-text">No units available yet.</p>
        ) : (
          <div className="resident-card-grid">
            {units.map((unit) => (
              <article className="resident-row-card" key={unit.id}>
                <div className="resident-row-id">
                  <DoorClosed size={18} />
                </div>
                <div className="resident-row-main">
                  <h4>{unit.property?.name || "Property"} / {unit.unit_number}</h4>
                  <p>{unit.unit_type} / Rent {formatKES(unit.rent_amount)} / Deposit {formatKES(unit.deposit)}</p>
                </div>
                <div className="resident-row-meta">
                  <StatusBadge status={unit.status} />
                </div>
              </article>
            ))}
          </div>
        )}
      </SectionCard>
    </PageLayout>
  );
}
