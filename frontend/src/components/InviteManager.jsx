import React, { useEffect, useState } from "react";
import { AlertCircle } from "lucide-react";
import { useNavigate } from "react-router-dom";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";

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

const hasPayoutSetup = (payload) => Boolean(payload?.payout_method && payload?.payout_destination);
const isPayoutGateError = (error) => error?.response?.status === 403 && error?.response?.data?.code === "payout_not_configured";

function PayoutRequiredNotice({ children, onNavigate, role = "status" }) {
  return (
    <div className="payout-required-notice" role={role}>
      <AlertCircle size={15} />
      <span>{children(onNavigate)}</span>
    </div>
  );
}

export default function InviteManager() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [inviteLink, setInviteLink] = useState("");
  const [error, setError] = useState("");
  const [payoutConfigured, setPayoutConfigured] = useState(false);
  const [payoutLoading, setPayoutLoading] = useState(true);
  const [payoutGateError, setPayoutGateError] = useState(false);

  useEffect(() => {
    let active = true;

    const loadPayoutStatus = async () => {
      setPayoutLoading(true);
      try {
        const response = await api.get("/api/landlord/settings/");
        const configured = hasPayoutSetup(response.data);
        if (!active) return;
        setPayoutConfigured(configured);
        if (configured) {
          setPayoutGateError(false);
        }
      } catch {
        if (!active) return;
        setPayoutConfigured(false);
      } finally {
        if (active) {
          setPayoutLoading(false);
        }
      }
    };

    // The UI mirrors the backend rule so landlords see why invites are disabled,
    // while the API remains the real security boundary.
    loadPayoutStatus();

    return () => {
      active = false;
    };
  }, []);

  const goToPayoutSetup = () => navigate(PAYOUT_SETUP_PATH);
  const inviteBlocked = !payoutLoading && !payoutConfigured;

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    setPayoutGateError(false);
    if (!payoutConfigured) {
      setPayoutGateError(true);
      return;
    }
    try {
      const response = await api.post("/api/manager-invites/", { name, email, phone });
      setInviteLink(response.data.invite_link || "");
    } catch (err) {
      if (isPayoutGateError(err)) {
        setPayoutConfigured(false);
        setPayoutGateError(true);
        return;
      }
      setError(getErrorMessage(err, "Failed to create invite."));
    }
  };

  return (
    <>
      <style>{payoutGateStyles}</style>
      <div className="dashboard-container">
        <h2>Invite Manager</h2>
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
        <div className="card">
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
          <form onSubmit={submit} style={inviteBlocked ? { opacity: 0.72 } : undefined}>
            <input value={name} onChange={(event) => setName(event.target.value)} aria-label="Manager name" required />
            <input value={phone} onChange={(event) => setPhone(event.target.value)} aria-label="Phone number" required />
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} aria-label="Personal email" />
            <button
              type="submit"
              disabled={payoutLoading || !payoutConfigured}
              style={{
                opacity: inviteBlocked ? 0.45 : 1,
                cursor: inviteBlocked ? "not-allowed" : "pointer",
              }}
            >
              Send Invite
            </button>
          </form>
          {inviteLink ? (
            <p>
              Invite link: <code>{inviteLink}</code>{" "}
              <button type="button" onClick={() => navigator.clipboard.writeText(inviteLink)}>Copy</button>
            </p>
          ) : null}
        </div>
      </div>
    </>
  );
}
