import React, { useContext, useEffect, useMemo, useState } from "react";
import { Copy, Send } from "lucide-react";
import api from "../services/api";
import { AuthContext } from "../context/AuthContext";
import { getErrorMessage } from "../utils/errors";
import { formatDateTime } from "../utils/format";
import StatusBadge from "./StatusBadge";
import { PageLayout, SectionCard, StatCard } from "./ui";

const buildInviteUrl = (invite) => {
  const token = invite?.token || invite?.invite_link?.split("/").filter(Boolean).at(-1);
  return token ? `${window.location.origin}/invite/tenant/${token}` : "";
};

const createDefaultForm = () => ({
  full_name: "",
  email: "",
  phone: "",
  property: "",
  unit: "",
  expires_at: "",
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

export default function InvitesNew() {
  const { user } = useContext(AuthContext);
  const [properties, setProperties] = useState([]);
  const [units, setUnits] = useState([]);
  const [invites, setInvites] = useState([]);
  const [createdLink, setCreatedLink] = useState("");
  const [deliveryNote, setDeliveryNote] = useState("");
  const [form, setForm] = useState(createDefaultForm);
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

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    setSuccess("");
    try {
      const payload = { ...form };
      if (!payload.property || payload.property === "__none") delete payload.property;
      if (!payload.unit || payload.unit === "__none") delete payload.unit;
      if (!payload.expires_at) delete payload.expires_at;
      const res = await api.post("/api/invites/", payload);
      setCreatedLink(buildInviteUrl(res.data));
      setDeliveryNote(buildDeliveryMessage(res.data));
      setSuccess("Tenant invite created successfully.");
      setForm(createDefaultForm());
      await load();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to invite tenant."));
    }
  };

  const copy = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      setSuccess("Invite link copied.");
    } catch {}
  };

  const resendInvite = async (invite) => {
    setWorkingInviteId(invite.id);
    setError("");
    setSuccess("");
    try {
      const res = await api.post(`/api/invites/${invite.id}/resend/`);
      setCreatedLink(buildInviteUrl(res.data));
      setDeliveryNote(buildDeliveryMessage(res.data));
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

  const pendingCount = useMemo(
    () => invites.filter((invite) => invite.status === "pending").length,
    [invites]
  );
  const propertyMap = useMemo(
    () => Object.fromEntries(properties.map((property) => [String(property.id), property.name])),
    [properties]
  );
  const unitMap = useMemo(
    () => Object.fromEntries(units.map((unit) => [String(unit.id), `${unit.property?.name || "Property"} / ${unit.unit_number}`])),
    [units]
  );
  const filteredUnits = useMemo(
    () => (!(form.property && form.property !== "__none") ? units : units.filter((unit) => String(unit.property?.id || unit.property) === String(form.property))),
    [form.property, units]
  );

  return (
    <PageLayout
      variant="executive"
      kicker="Onboarding"
      title="Tenant Invites"
    >
      {error ? <p className="error">{error}</p> : null}
      {success ? <p className="success">{success}</p> : null}

      {user?.role !== "manager" ? (
        <section className="resident-hero-grid">
          <StatCard variant="blue" title="Invites Sent" subtitle="All invitations" value={String(invites.length).padStart(2, "0")} />
          <StatCard variant="purple" title="Pending" subtitle="Awaiting acceptance" value={String(pendingCount).padStart(2, "0")} />
          <StatCard variant="mint" title="Scoped Units" subtitle="Selectable assignment units" value={String(units.length).padStart(2, "0")} />
        </section>
      ) : null}

      <SectionCard icon={Send} title="Send Invite">
        {createdLink ? (
          <div className="resident-token-box">
            <strong>Latest invite link</strong>
            <code>{createdLink}</code>
            {deliveryNote ? <p className="subtitle">{deliveryNote}</p> : null}
            <div className="resident-form-actions">
              <button className="resident-link-btn" type="button" onClick={() => copy(createdLink)}>
                <Copy size={16} />
                <span>Copy link</span>
              </button>
            </div>
          </div>
        ) : null}

        <form className="resident-form-grid" onSubmit={submit}>
          <label className="resident-field">
            <span>Tenant name</span>
            <input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required />
          </label>
          <label className="resident-field">
            <span>Email</span>
            <input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </label>
          <label className="resident-field">
            <span>Phone</span>
            <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </label>
            <label className="resident-field">
              <span>Property</span>
              <select
                value={form.property}
                onChange={(e) => setForm({ ...form, property: e.target.value, unit: "" })}
              >
                <option value="" hidden></option>
                <option value="__none">No specific property</option>
                {properties.map((property) => <option key={property.id} value={property.id}>{property.name}</option>)}
              </select>
            </label>
            <label className="resident-field">
              <span>Unit</span>
              <select value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })}>
                <option value="" hidden></option>
                <option value="__none">No specific unit</option>
                {filteredUnits.map((unit) => <option key={unit.id} value={unit.id}>{unit.property?.name} / {unit.unit_number}</option>)}
              </select>
            </label>
          <label className="resident-field">
            <span>Expires at</span>
            <input type="datetime-local" value={form.expires_at} onChange={(e) => setForm({ ...form, expires_at: e.target.value })} />
          </label>
          <button className="resident-primary-btn" type="submit">
            <Send size={16} />
            <span>Create and Send Invite</span>
          </button>
        </form>
      </SectionCard>

      <SectionCard title="Invite Log">
        {invites.length === 0 ? (
          <p className="resident-helper-text">No invites have been sent yet.</p>
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
