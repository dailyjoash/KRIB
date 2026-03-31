import React, { useEffect, useMemo, useRef, useState } from "react";
import { Copy, Send, ShieldCheck, Users } from "lucide-react";
import { useLocation } from "react-router-dom";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { formatDateTime } from "../utils/format";
import StatusBadge from "./StatusBadge";
import { PageLayout, SectionCard } from "./ui";

const buildInviteUrl = (invite) => {
  const token = invite?.token || invite?.invite_link?.split("/").filter(Boolean).at(-1);
  return token ? `${window.location.origin}/invite/tenant/${token}` : "";
};

const createDefaultExpiry = () => {
  const next = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
  const shifted = new Date(next.getTime() - next.getTimezoneOffset() * 60 * 1000);
  return shifted.toISOString().slice(0, 16);
};

const createDefaultTenantForm = () => ({
  full_name: "",
  email: "",
  phone: "",
  property: "",
  unit: "",
  expires_at: createDefaultExpiry(),
});

const resolveInviteStatus = (invite) => {
  if (invite?.status !== "pending") return invite?.status;
  return new Date(invite.expires_at).getTime() < Date.now() ? "expired" : invite.status;
};

const buildDeliveryMessage = (payload) => {
  const channels = [];
  if (payload?.email_sent) channels.push("email");
  if (payload?.sms_sent) channels.push("sms");
  if (!channels.length) return "Invite created. Share the link manually.";
  return `Invite sent by ${channels.join(" and ")}.`;
};

export default function LandlordInvites() {
  const location = useLocation();
  const managerSectionRef = useRef(null);
  const tenantSectionRef = useRef(null);

  const [properties, setProperties] = useState([]);
  const [units, setUnits] = useState([]);
  const [invites, setInvites] = useState([]);
  const [managerInviteLink, setManagerInviteLink] = useState("");
  const [tenantInviteLink, setTenantInviteLink] = useState("");
  const [managerDeliveryNote, setManagerDeliveryNote] = useState("");
  const [tenantDeliveryNote, setTenantDeliveryNote] = useState("");
  const [managerForm, setManagerForm] = useState({ name: "", email: "", phone: "" });
  const [tenantForm, setTenantForm] = useState(createDefaultTenantForm);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [workingInviteId, setWorkingInviteId] = useState(null);

  const load = async () => {
    try {
      const [propertyRes, unitRes, inviteRes] = await Promise.all([
        api.get("/api/properties/"),
        api.get("/api/units/"),
        api.get("/api/invites/"),
      ]);
      setProperties(propertyRes.data || []);
      setUnits(unitRes.data || []);
      setInvites(inviteRes.data || []);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load invites."));
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const section = new URLSearchParams(location.search).get("section");
    const target = section === "tenant" ? tenantSectionRef.current : managerSectionRef.current;
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [location.search]);

  const submitManagerInvite = async (event) => {
    event.preventDefault();
    setError("");
    setSuccess("");
    try {
      const response = await api.post("/api/manager-invites/", managerForm);
      setManagerInviteLink(response.data.invite_link || "");
      setManagerDeliveryNote(buildDeliveryMessage(response.data));
      setManagerForm({ name: "", email: "", phone: "" });
      setSuccess("Manager invite created successfully.");
    } catch (err) {
      setError(getErrorMessage(err, "Failed to create manager invite."));
    }
  };

  const submitTenantInvite = async (event) => {
    event.preventDefault();
    setError("");
    setSuccess("");
    try {
      const payload = { ...tenantForm };
      if (!payload.property) delete payload.property;
      if (!payload.unit) delete payload.unit;
      if (!payload.expires_at) delete payload.expires_at;
      const response = await api.post("/api/invites/", payload);
      setTenantInviteLink(buildInviteUrl(response.data));
      setTenantDeliveryNote(buildDeliveryMessage(response.data));
      setTenantForm(createDefaultTenantForm());
      setSuccess("Tenant invite created successfully.");
      await load();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to invite tenant."));
    }
  };

  const copy = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      setSuccess("Invite link copied.");
    } catch {
      // Ignore clipboard failures.
    }
  };

  const resendInvite = async (invite) => {
    setWorkingInviteId(invite.id);
    setError("");
    setSuccess("");
    try {
      const response = await api.post(`/api/invites/${invite.id}/resend/`);
      setTenantInviteLink(buildInviteUrl(response.data));
      setTenantDeliveryNote(buildDeliveryMessage(response.data));
      setSuccess("Tenant invite resent successfully.");
      await load();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to resend tenant invite."));
    } finally {
      setWorkingInviteId(null);
    }
  };

  const cancelInvite = async (invite) => {
    setWorkingInviteId(invite.id);
    setError("");
    setSuccess("");
    try {
      await api.post(`/api/invites/${invite.id}/cancel/`);
      setSuccess("Tenant invite cancelled.");
      await load();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to cancel tenant invite."));
    } finally {
      setWorkingInviteId(null);
    }
  };

  const filteredUnits = useMemo(
    () => (!tenantForm.property ? units : units.filter((unit) => String(unit.property?.id || unit.property) === String(tenantForm.property))),
    [tenantForm.property, units]
  );
  const propertyMap = useMemo(() => Object.fromEntries(properties.map((property) => [String(property.id), property.name])), [properties]);
  const unitMap = useMemo(
    () => Object.fromEntries(units.map((unit) => [String(unit.id), `${unit.property?.name || "Property"} / ${unit.unit_number}`])),
    [units]
  );

  return (
    <PageLayout
      variant="executive"
      kicker="Onboarding"
      title="Invite Manager"
    >
      {error ? <p className="error">{error}</p> : null}
      {success ? <p className="success">{success}</p> : null}

      <SectionCard icon={ShieldCheck} title="Invite Manager">
        <div ref={managerSectionRef} />
        {managerInviteLink ? (
          <div className="resident-token-box">
            <strong>Latest manager invite link</strong>
            <code>{managerInviteLink}</code>
            {managerDeliveryNote ? <p className="subtitle">{managerDeliveryNote}</p> : null}
            <div className="resident-form-actions">
              <button className="resident-link-btn" type="button" onClick={() => copy(managerInviteLink)}>
                <Copy size={16} />
                <span>Copy link</span>
              </button>
            </div>
          </div>
        ) : null}

        <form className="resident-form-grid" onSubmit={submitManagerInvite}>
          <label className="resident-field">
            <span>Name</span>
            <input value={managerForm.name} onChange={(event) => setManagerForm({ ...managerForm, name: event.target.value })} placeholder="Manager name" required />
          </label>
          <label className="resident-field">
            <span>Phone</span>
            <input value={managerForm.phone} onChange={(event) => setManagerForm({ ...managerForm, phone: event.target.value })} placeholder="+2547..." required />
          </label>
          <label className="resident-field">
            <span>Email</span>
            <input type="email" value={managerForm.email} onChange={(event) => setManagerForm({ ...managerForm, email: event.target.value })} placeholder="Personal email (optional)" />
          </label>
          <button className="resident-primary-btn" type="submit">
            <ShieldCheck size={16} />
            <span>Create Manager Invite</span>
          </button>
        </form>
      </SectionCard>

      <SectionCard icon={Users} title="Invite Tenant">
        <div ref={tenantSectionRef} />
        {tenantInviteLink ? (
          <div className="resident-token-box">
            <strong>Latest tenant invite link</strong>
            <code>{tenantInviteLink}</code>
            {tenantDeliveryNote ? <p className="subtitle">{tenantDeliveryNote}</p> : null}
            <div className="resident-form-actions">
              <button className="resident-link-btn" type="button" onClick={() => copy(tenantInviteLink)}>
                <Copy size={16} />
                <span>Copy link</span>
              </button>
            </div>
          </div>
        ) : null}

        <form className="resident-form-grid" onSubmit={submitTenantInvite}>
          <label className="resident-field">
            <span>Tenant name</span>
            <input value={tenantForm.full_name} onChange={(event) => setTenantForm({ ...tenantForm, full_name: event.target.value })} placeholder="Full name" required />
          </label>
          <label className="resident-field">
            <span>Email</span>
            <input value={tenantForm.email} onChange={(event) => setTenantForm({ ...tenantForm, email: event.target.value })} placeholder="Email address" />
          </label>
          <label className="resident-field">
            <span>Phone</span>
            <input value={tenantForm.phone} onChange={(event) => setTenantForm({ ...tenantForm, phone: event.target.value })} placeholder="+2547..." />
          </label>
          <label className="resident-field">
            <span>Property</span>
            <select value={tenantForm.property} onChange={(event) => setTenantForm({ ...tenantForm, property: event.target.value, unit: "" })}>
              <option value="">Optional property</option>
              {properties.map((property) => (
                <option key={property.id} value={property.id}>
                  {property.name}
                </option>
              ))}
            </select>
          </label>
          <label className="resident-field">
            <span>Unit</span>
            <select value={tenantForm.unit} onChange={(event) => setTenantForm({ ...tenantForm, unit: event.target.value })}>
              <option value="">Optional unit</option>
              {filteredUnits.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.property?.name} / {unit.unit_number}
                </option>
              ))}
            </select>
          </label>
          <label className="resident-field">
            <span>Expires at</span>
            <input type="datetime-local" value={tenantForm.expires_at} onChange={(event) => setTenantForm({ ...tenantForm, expires_at: event.target.value })} />
          </label>
          <button className="resident-primary-btn" type="submit">
            <Send size={16} />
            <span>Create and Send Tenant Invite</span>
          </button>
        </form>
      </SectionCard>

      <SectionCard title="Invite Log">
        {invites.length === 0 ? (
          <p className="resident-helper-text">No tenant invites have been sent yet.</p>
        ) : (
          <div className="resident-table-list invite-log-list">
            {invites.map((invite, index) => {
              const inviteLink = buildInviteUrl(invite);
              const status = resolveInviteStatus(invite);
              return (
                <article className="resident-row-card invite-log-row" key={invite.id}>
                  <span className="resident-row-id">{String(index + 1).padStart(2, "0")}</span>
                  <div className="resident-profile-columns invite-log-columns">
                    <div className="resident-profile-item">
                      <span>Name</span>
                      <strong>{invite.full_name || "Tenant invite"}</strong>
                    </div>
                    <div className="resident-profile-item">
                      <span>Property</span>
                      <strong>{propertyMap[String(invite.property)] || "-"}</strong>
                    </div>
                    <div className="resident-profile-item">
                      <span>Unit</span>
                      <strong>{unitMap[String(invite.unit)] || "-"}</strong>
                    </div>
                    <div className="resident-profile-item">
                      <span>Email</span>
                      <strong>{invite.email || "-"}</strong>
                    </div>
                    <div className="resident-profile-item">
                      <span>Phone</span>
                      <strong>{invite.phone || "-"}</strong>
                    </div>
                    <div className="resident-profile-item">
                      <span>Expires</span>
                      <strong>{formatDateTime(invite.expires_at)}</strong>
                    </div>
                    <div className="resident-profile-item invite-log-link-item">
                      <span>Invite link</span>
                      <code className="invite-log-inline-link">{inviteLink || "-"}</code>
                    </div>
                  </div>
                  <div className="invite-log-row-side">
                    <StatusBadge status={status} />
                    <div className="invite-log-actions">
                      <button className="resident-link-btn" type="button" onClick={() => copy(inviteLink)} disabled={!inviteLink}>
                        <Copy size={16} />
                        <span>Copy</span>
                      </button>
                      <button
                        className="resident-link-btn"
                        type="button"
                        onClick={() => resendInvite(invite)}
                        disabled={status !== "pending" || workingInviteId === invite.id}
                      >
                        <Send size={16} />
                        <span>{workingInviteId === invite.id ? "Working..." : "Resend"}</span>
                      </button>
                      <button
                        className="resident-link-btn"
                        type="button"
                        onClick={() => cancelInvite(invite)}
                        disabled={status !== "pending" || workingInviteId === invite.id}
                      >
                        <span>Cancel</span>
                      </button>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </SectionCard>
    </PageLayout>
  );
}
