import React, { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Copy, ShieldCheck, UserPlus, Users } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { formatDateTime } from "../utils/format";
import StatusBadge from "./StatusBadge";
import { PageLayout, SectionCard } from "./ui";

const PAYOUT_SETUP_PATH = "/profile";
const payoutGateStyles = `
  .payout-required-notice {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 12px 14px;
    border-radius: var(--radius-sm);
    background: rgba(244, 179, 76, 0.08);
    border: 1px solid rgba(244, 179, 76, 0.28);
    color: var(--warning);
    font-size: 0.84rem;
    font-weight: 500;
    margin-bottom: 20px;
    line-height: 1.5;
  }

  .payout-inline-link {
    background: none;
    border: none;
    padding: 0;
    color: var(--primary);
    font-size: inherit;
    font-weight: 700;
    cursor: pointer;
    text-decoration: underline;
    min-height: unset;
    border-radius: 0;
  }

  .payout-inline-link:hover {
    color: var(--text);
    transform: none;
  }
`;

const buildInviteUrl = (invite) => {
  const token = invite?.token || invite?.invite_link?.split("/").filter(Boolean).at(-1);
  return token ? `${window.location.origin}/invite/tenant/${token}` : "";
};

const createDefaultTenantForm = () => ({
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

const hasPayoutSetup = (payload) => Boolean(payload?.payout_method && payload?.payout_destination);
const isPayoutGateError = (error) => error?.response?.status === 403 && error?.response?.data?.code === "payout_not_configured";

function PayoutRequiredNotice({ children, onNavigate, role = "status" }) {
  return (
    <div className="payout-required-notice" role={role}>
      <AlertCircle size={15} />
      <span>
        {children(onNavigate)}
      </span>
    </div>
  );
}

export default function LandlordInvites() {
  const location = useLocation();
  const navigate = useNavigate();
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
  const [payoutConfigured, setPayoutConfigured] = useState(false);
  const [payoutLoading, setPayoutLoading] = useState(true);
  const [payoutGateError, setPayoutGateError] = useState(false);

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

  const loadPayoutStatus = async () => {
    setPayoutLoading(true);
    try {
      const response = await api.get("/api/landlord/settings/");
      const configured = hasPayoutSetup(response.data);
      setPayoutConfigured(configured);
      if (configured) {
        setPayoutGateError(false);
      }
    } catch {
      setPayoutConfigured(false);
    } finally {
      setPayoutLoading(false);
    }
  };

  useEffect(() => {
    // The UI mirrors the API rule so landlords understand why the form is muted,
    // while the backend still enforces the real security boundary.
    load();
    loadPayoutStatus();
  }, []);

  useEffect(() => {
    const section = new URLSearchParams(location.search).get("section");
    const target = section === "tenant" ? tenantSectionRef.current : managerSectionRef.current;
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [location.search]);

  const goToPayoutSetup = () => navigate(PAYOUT_SETUP_PATH);

  const submitManagerInvite = async (event) => {
    event.preventDefault();
    setError("");
    setSuccess("");
    setPayoutGateError(false);
    if (!payoutConfigured) {
      setPayoutGateError(true);
      return;
    }
    try {
      const response = await api.post("/api/manager-invites/", managerForm);
      setManagerInviteLink(response.data.invite_link || "");
      setManagerDeliveryNote(buildDeliveryMessage(response.data));
      setManagerForm({ name: "", email: "", phone: "" });
      setSuccess("Manager invite created successfully.");
    } catch (err) {
      if (isPayoutGateError(err)) {
        setPayoutConfigured(false);
        setPayoutGateError(true);
        return;
      }
      setError(getErrorMessage(err, "Failed to create manager invite."));
    }
  };

  const submitTenantInvite = async (event) => {
    event.preventDefault();
    setError("");
    setSuccess("");
    setPayoutGateError(false);
    if (!payoutConfigured) {
      setPayoutGateError(true);
      return;
    }
    try {
      const payload = { ...tenantForm };
      if (!payload.property || payload.property === "__none") delete payload.property;
      if (!payload.unit || payload.unit === "__none") delete payload.unit;
      if (!payload.expires_at) delete payload.expires_at;
      const response = await api.post("/api/invites/", payload);
      setTenantInviteLink(buildInviteUrl(response.data));
      setTenantDeliveryNote(buildDeliveryMessage(response.data));
      setTenantForm(createDefaultTenantForm());
      setSuccess("Tenant invite created successfully.");
      await load();
    } catch (err) {
      if (isPayoutGateError(err)) {
        setPayoutConfigured(false);
        setPayoutGateError(true);
        return;
      }
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
    () => (!(tenantForm.property && tenantForm.property !== "__none") ? units : units.filter((unit) => String(unit.property?.id || unit.property) === String(tenantForm.property))),
    [tenantForm.property, units]
  );
  const propertyMap = useMemo(() => Object.fromEntries(properties.map((property) => [String(property.id), property.name])), [properties]);
  const unitMap = useMemo(
    () => Object.fromEntries(units.map((unit) => [String(unit.id), `${unit.property?.name || "Property"} / ${unit.unit_number}`])),
    [units]
  );
  const inviteBlocked = !payoutLoading && !payoutConfigured;
  const formMutedStyle = inviteBlocked ? { opacity: 0.72 } : undefined;
  const disabledButtonStyle = {
    opacity: inviteBlocked ? 0.45 : 1,
    cursor: inviteBlocked ? "not-allowed" : "pointer",
  };

  return (
    <>
      <style>{payoutGateStyles}</style>
      <PageLayout
        variant="executive"
        kicker="Onboarding"
        title="Invites"
      >
        {payoutGateError ? (
          <PayoutRequiredNotice onNavigate={goToPayoutSetup} role="alert">
            {(openSetup) => (
              <>
                Please{" "}
                <button className="payout-inline-link" type="button" onClick={openSetup}>
                  set up your payment method
                </button>{" "}
                before inviting.
              </>
            )}
          </PayoutRequiredNotice>
        ) : null}
        {error ? <p className="error">{error}</p> : null}
        {success ? <p className="success">{success}</p> : null}

        <SectionCard icon={Users} title="Invite Tenant">
          <div ref={tenantSectionRef} />
          {!payoutLoading && !payoutConfigured ? (
            <PayoutRequiredNotice onNavigate={goToPayoutSetup}>
              {(openSetup) => (
                <>
                  You need to{" "}
                  <button className="payout-inline-link" type="button" onClick={openSetup}>
                    set up your payment method
                  </button>{" "}
                  before you can invite tenants.
                </>
              )}
            </PayoutRequiredNotice>
          ) : null}
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

          <form className="resident-form-grid" onSubmit={submitTenantInvite} style={formMutedStyle}>
            <label className="resident-field">
              <span>Tenant name</span>
              <input value={tenantForm.full_name} onChange={(event) => setTenantForm({ ...tenantForm, full_name: event.target.value })} required />
            </label>
            <label className="resident-field">
              <span>Email</span>
              <input value={tenantForm.email} onChange={(event) => setTenantForm({ ...tenantForm, email: event.target.value })} />
            </label>
            <label className="resident-field">
              <span>Phone</span>
              <input value={tenantForm.phone} onChange={(event) => setTenantForm({ ...tenantForm, phone: event.target.value })} />
            </label>
            <label className="resident-field">
              <span>Property</span>
              <select value={tenantForm.property} onChange={(event) => setTenantForm({ ...tenantForm, property: event.target.value, unit: "" })}>
                <option value="" hidden></option>
                <option value="__none">No specific property</option>
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
                <option value="" hidden></option>
                <option value="__none">No specific unit</option>
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
            <button
              className="resident-primary-btn"
              type="submit"
              disabled={payoutLoading || !payoutConfigured}
              style={disabledButtonStyle}
            >
              <UserPlus size={15} />
              <span>Send Invite</span>
            </button>
          </form>
        </SectionCard>

        <SectionCard icon={ShieldCheck} title="Invite Manager">
          <div ref={managerSectionRef} />
          {!payoutLoading && !payoutConfigured ? (
            <PayoutRequiredNotice onNavigate={goToPayoutSetup}>
              {(openSetup) => (
                <>
                  You need to{" "}
                  <button className="payout-inline-link" type="button" onClick={openSetup}>
                    set up your payment method
                  </button>{" "}
                  before you can invite a manager.
                </>
              )}
            </PayoutRequiredNotice>
          ) : null}
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

          <form className="resident-form-grid" onSubmit={submitManagerInvite} style={formMutedStyle}>
            <label className="resident-field">
              <span>Name</span>
              <input value={managerForm.name} onChange={(event) => setManagerForm({ ...managerForm, name: event.target.value })} required />
            </label>
            <label className="resident-field">
              <span>Phone</span>
              <input value={managerForm.phone} onChange={(event) => setManagerForm({ ...managerForm, phone: event.target.value })} required />
            </label>
            <label className="resident-field">
              <span>Email</span>
              <input type="email" value={managerForm.email} onChange={(event) => setManagerForm({ ...managerForm, email: event.target.value })} />
            </label>
            <button
              className="resident-primary-btn"
              type="submit"
              disabled={payoutLoading || !payoutConfigured}
              style={disabledButtonStyle}
            >
              <ShieldCheck size={15} />
              <span>Send Invite</span>
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
                          <UserPlus size={16} />
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
    </>
  );
}
