import React, { useEffect, useMemo, useState } from "react";
import { Camera, ClipboardList, FileBadge2, ShieldCheck } from "lucide-react";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { formatDate, formatKES } from "../utils/format";
import SignaturePad from "./SignaturePad";
import StatusBadge from "./StatusBadge";
import { PageLayout, SectionCard, StatCard } from "./ui";

const sortByPropertyUnit = (left, right) => {
  const leftLabel = `${left.property?.name || ""}-${left.unit_number || ""}`;
  const rightLabel = `${right.property?.name || ""}-${right.unit_number || ""}`;
  return leftLabel.localeCompare(rightLabel, undefined, { numeric: true, sensitivity: "base" });
};

const sortLeaseRows = (left, right) => {
  const leftLabel = `${left.unit?.property?.name || ""}-${left.unit?.unit_number || ""}`;
  const rightLabel = `${right.unit?.property?.name || ""}-${right.unit?.unit_number || ""}`;
  return leftLabel.localeCompare(rightLabel, undefined, { numeric: true, sensitivity: "base" });
};

export default function LeasesNew() {
  const [units, setUnits] = useState([]);
  const [tenants, setTenants] = useState([]);
  const [leases, setLeases] = useState([]);
  const [form, setForm] = useState({
    unit_id: "",
    tenant_id: "",
    start_date: "",
    end_date: "",
    due_day: 5,
  });
  const [identityDocument, setIdentityDocument] = useState(null);
  const [identityPreviewUrl, setIdentityPreviewUrl] = useState("");
  const [tenantSignature, setTenantSignature] = useState("");
  const [signatureResetKey, setSignatureResetKey] = useState(0);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const [leaseToRemove, setLeaseToRemove] = useState(null);
  const [removingTenant, setRemovingTenant] = useState(false);

  const loadData = async () => {
    try {
      const [unitRes, tenantRes, leaseRes] = await Promise.all([
        api.get("/api/units/"),
        api.get("/api/tenants/"),
        api.get("/api/leases/"),
      ]);
      setUnits(unitRes.data || []);
      setTenants(tenantRes.data || []);
      setLeases(leaseRes.data || []);
      setError("");
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load lease data."));
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => () => {
    if (identityPreviewUrl) {
      window.URL.revokeObjectURL(identityPreviewUrl);
    }
  }, [identityPreviewUrl]);

  const updateIdentityDocument = (file) => {
    if (identityPreviewUrl) {
      window.URL.revokeObjectURL(identityPreviewUrl);
    }
    setIdentityDocument(file);
    setIdentityPreviewUrl(file ? window.URL.createObjectURL(file) : "");
  };

  const resetForm = () => {
    if (identityPreviewUrl) {
      window.URL.revokeObjectURL(identityPreviewUrl);
    }
    setForm({ unit_id: "", tenant_id: "", start_date: "", end_date: "", due_day: 5 });
    setIdentityDocument(null);
    setIdentityPreviewUrl("");
    setTenantSignature("");
    setSignatureResetKey((prev) => prev + 1);
  };

  const createLease = async (event) => {
    event.preventDefault();
    setError("");
    setSuccess("");
    setLoading(true);

    try {
      const selectedUnit = units.find((unit) => String(unit.id) === String(form.unit_id));
      if (!selectedUnit) {
        throw new Error("Selected unit not found.");
      }
      if (!identityDocument) {
        throw new Error("Capture the tenant ID or passport before creating the lease.");
      }
      if (!tenantSignature) {
        throw new Error("Capture the tenant signature before creating the lease.");
      }

      const payload = new FormData();
      payload.append("unit_id", form.unit_id);
      payload.append("tenant_id", form.tenant_id);
      payload.append("start_date", form.start_date);
      if (form.end_date) payload.append("end_date", form.end_date);
      payload.append("status", "active");
      payload.append("due_day", String(Number(form.due_day) || 5));
      payload.append("rent_amount", String(selectedUnit.rent_amount));
      payload.append("identity_document", identityDocument);
      payload.append("tenant_signature", tenantSignature);

      await api.post("/api/leases/", payload, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      setSuccess("Lease created, tenant ID stored, and signed agreement generated successfully.");
      resetForm();
      await loadData();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to create lease."));
    } finally {
      setLoading(false);
    }
  };

  const confirmRemoveTenant = async () => {
    if (!leaseToRemove) return;
    setRemovingTenant(true);
    setError("");
    setSuccess("");

    try {
      await api.post(`/api/leases/${leaseToRemove.id}/remove-tenant/`);
      setSuccess(`Tenant removed from ${leaseToRemove.unit?.property?.name || "the property"} / Unit ${leaseToRemove.unit?.unit_number || "-"}.`);
      setLeaseToRemove(null);
      await loadData();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to remove tenant."));
    } finally {
      setRemovingTenant(false);
    }
  };

  const availableUnits = useMemo(
    () => units
      .filter((unit) => ["available", "vacant"].includes(String(unit.status || "").toLowerCase()))
      .slice()
      .sort(sortByPropertyUnit),
    [units]
  );

  const activeLeases = useMemo(
    () => leases
      .filter((lease) => String(lease.status || "").toLowerCase() === "active")
      .slice()
      .sort(sortLeaseRows),
    [leases]
  );

  const selectedUnit = useMemo(
    () => units.find((unit) => String(unit.id) === String(form.unit_id)) || null,
    [form.unit_id, units]
  );

  const selectedTenant = useMemo(
    () => tenants.find((tenant) => String(tenant.user?.id) === String(form.tenant_id)) || null,
    [form.tenant_id, tenants]
  );

  return (
    <PageLayout variant="executive" kicker="Occupancy" title="Leases">
      {error ? <p className="error">{error}</p> : null}
      {success ? <p className="success">{success}</p> : null}

      <section className="resident-hero-grid">
        <StatCard variant="blue" title="Available Units" subtitle="Ready for allocation" value={String(availableUnits.length).padStart(2, "0")} />
        <StatCard variant="mint" title="Active Leases" subtitle="Current occupancy" value={String(activeLeases.length).padStart(2, "0")} />
      </section>

      <SectionCard icon={ClipboardList} title="Create Lease">
        <form className="resident-form-grid" onSubmit={createLease}>
          <label className="resident-field">
            <span>Available unit</span>
            <select name="unit_id" value={form.unit_id} onChange={(e) => setForm({ ...form, unit_id: e.target.value })} required disabled={loading}>
              <option value="">Select unit</option>
              {availableUnits.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.property?.name} / Unit {unit.unit_number} / {formatKES(unit.rent_amount)}
                </option>
              ))}
            </select>
          </label>

            <label className="resident-field">
              <span>Tenant</span>
              <select name="tenant_id" value={form.tenant_id} onChange={(e) => setForm({ ...form, tenant_id: e.target.value })} required disabled={loading}>
                <option value="">Select tenant</option>
                {tenants.map((tenant) => (
                <option key={tenant.id} value={tenant.user?.id}>
                  {tenant.user?.username} {tenant.user?.email ? `(${tenant.user.email})` : ""}
                  </option>
                ))}
              </select>
            </label>

          <label className="resident-field">
            <span>Start date</span>
            <input type="date" name="start_date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} required disabled={loading} />
          </label>

          <label className="resident-field">
            <span>End date</span>
            <input type="date" name="end_date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} disabled={loading} />
          </label>

          <label className="resident-field">
            <span>Due day</span>
            <input type="number" min="1" max="28" name="due_day" value={form.due_day} onChange={(e) => setForm({ ...form, due_day: e.target.value })} disabled={loading} />
          </label>

          <label className="resident-field resident-field-full">
            <span>ID / Passport capture</span>
            <div className="lease-capture-card">
              <div className="lease-capture-copy">
                <div className="lease-capture-title">
                  <Camera size={16} />
                  <strong>Identification document</strong>
                </div>
              </div>
              <input
                type="file"
                accept="image/*"
                capture="environment"
                onChange={(e) => updateIdentityDocument(e.target.files?.[0] || null)}
                required
                disabled={loading}
              />
              {identityPreviewUrl ? (
                <div className="lease-capture-preview">
                  <img src={identityPreviewUrl} alt="Tenant identification preview" />
                  <span>{identityDocument?.name || "Identification document captured"}</span>
                </div>
              ) : (
                <div className="lease-capture-placeholder">
                  <ShieldCheck size={18} />
                  <span>No identification document captured yet.</span>
                </div>
              )}
            </div>
          </label>

          <div className="resident-field resident-field-full">
            <span>Tenant signature</span>
            <SignaturePad onChange={setTenantSignature} resetKey={signatureResetKey} />
          </div>

          <div className="resident-field resident-field-full">
            <div className="lease-preview-card">
              <div className="lease-preview-head">
                <div className="lease-preview-title">
                  <FileBadge2 size={16} />
                  <strong>Agreement preview</strong>
                </div>
              </div>
              <div className="lease-preview-grid">
                <div>
                  <span>Tenant</span>
                  <strong>{selectedTenant?.user?.username || "Select tenant"}</strong>
                </div>
                <div>
                  <span>Property / Unit</span>
                  <strong>{selectedUnit ? `${selectedUnit.property?.name} / ${selectedUnit.unit_number}` : "Select unit"}</strong>
                </div>
                <div>
                  <span>Monthly Rent</span>
                  <strong>{selectedUnit ? formatKES(selectedUnit.rent_amount) : "-"}</strong>
                </div>
                <div>
                  <span>Deposit</span>
                  <strong>{selectedUnit ? formatKES(selectedUnit.deposit) : "-"}</strong>
                </div>
                <div>
                  <span>Start Date</span>
                  <strong>{form.start_date ? formatDate(form.start_date) : "-"}</strong>
                </div>
                <div>
                  <span>Due day</span>
                  <strong>{form.due_day ? `Day ${form.due_day}` : "-"}</strong>
                </div>
              </div>
            </div>
          </div>

          <button className="resident-primary-btn" type="submit" disabled={loading}>
            <ClipboardList size={16} />
            <span>{loading ? "Creating..." : "Create Lease"}</span>
          </button>
        </form>
      </SectionCard>

      <SectionCard title="Current Leases">
        {leases.length === 0 ? (
          <p className="resident-helper-text">No leases found yet.</p>
        ) : (
          <div className="resident-lease-list">
            {leases.slice().sort(sortLeaseRows).map((lease) => (
              <article className="resident-lease-card" key={lease.id}>
                <div className="resident-lease-id">{lease.unit?.unit_number || lease.id}</div>
                <div className="resident-lease-main">
                  <h4>{lease.tenant?.username || "Tenant"}</h4>
                  <p>{lease.unit?.property?.name || "Property"} / Unit {lease.unit?.unit_number || "-"}</p>
                  <p>{formatKES(lease.rent_amount)} / Start {formatDate(lease.start_date)} / Due day {lease.due_day || 5}</p>
                </div>
                <div className="resident-lease-side">
                  <span className="resident-lease-meta">{lease.end_date ? `Ends ${formatDate(lease.end_date)}` : "Open ended"}</span>
                  <StatusBadge status={lease.status} />
                  {String(lease.status || "").toLowerCase() === "active" ? (
                    <button className="btn btn-glass" type="button" onClick={() => setLeaseToRemove(lease)}>
                      Remove Tenant
                    </button>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        )}
      </SectionCard>

      {leaseToRemove ? (
        <div className="resident-modal-backdrop" role="presentation" onClick={() => setLeaseToRemove(null)}>
          <div className="resident-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="remove-tenant-title" onClick={(event) => event.stopPropagation()}>
            <div className="resident-confirm-copy">
              <h3 id="remove-tenant-title">Remove tenant from unit?</h3>
              <p>
                This will end the active lease for {leaseToRemove.tenant?.username || "the tenant"} in {leaseToRemove.unit?.property?.name || "the property"} / Unit {leaseToRemove.unit?.unit_number || "-"} and mark the unit as vacant. The tenant account and payment history will stay in KRIB.
              </p>
            </div>
            <div className="resident-form-actions resident-confirm-actions">
              <button className="btn" type="button" onClick={() => setLeaseToRemove(null)} disabled={removingTenant}>
                Cancel
              </button>
              <button className="btn btn-primary" type="button" onClick={confirmRemoveTenant} disabled={removingTenant}>
                {removingTenant ? "Removing..." : "Remove Tenant"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </PageLayout>
  );
}
