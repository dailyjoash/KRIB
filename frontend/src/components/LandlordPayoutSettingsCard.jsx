import React, { useEffect, useState } from "react";
import { CreditCard, Save } from "lucide-react";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { SectionCard } from "./ui";

const createDefaultPayoutForm = () => ({
  business_name: "",
  collection_mode: "custody_legacy",
  payout_method: "",
  payout_destination: "",
  payout_bank_code: "",
});

const createDefaultCollectionForm = () => ({
  paybill_number: "",
  registered_business_name: "",
  verification_status: "",
});

export default function LandlordPayoutSettingsCard() {
  const [payoutForm, setPayoutForm] = useState(createDefaultPayoutForm);
  const [collectionForm, setCollectionForm] = useState(createDefaultCollectionForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingCollection, setSavingCollection] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    let active = true;

    const loadPayoutSettings = async () => {
      setLoading(true);
      try {
        const response = await api.get("/api/landlord/settings/");
        if (!active) return;
        setPayoutForm({
          business_name: response.data.business_name || "",
          collection_mode: response.data.collection_mode || "custody_legacy",
          payout_method: response.data.payout_method || "",
          payout_destination: response.data.payout_destination || "",
          payout_bank_code: response.data.payout_bank_code || "",
        });
        try {
          const accountResponse = await api.get("/api/landlord/collection-account/");
          if (!active) return;
          setCollectionForm({
            paybill_number: accountResponse.data.paybill_number || "",
            registered_business_name: accountResponse.data.registered_business_name || "",
            verification_status: accountResponse.data.verification_status || "",
          });
        } catch (accountErr) {
          if (!active && accountErr) return;
          setCollectionForm(createDefaultCollectionForm());
        }
      } catch (err) {
        if (!active) return;
        setError(getErrorMessage(err, "Failed to load payout settings."));
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    loadPayoutSettings();

    return () => {
      active = false;
    };
  }, []);

  const savePayoutSettings = async (event) => {
    event.preventDefault();
    setError("");
    setSuccess("");
    setSaving(true);

    try {
      const payload = {
        collection_mode: payoutForm.collection_mode || "custody_legacy",
        payout_method: payoutForm.payout_method || "",
        payout_destination: payoutForm.payout_destination.trim(),
        payout_bank_code: payoutForm.payout_method === "BANK" ? payoutForm.payout_bank_code.trim() : "",
      };
      if (payoutForm.business_name.trim()) {
        payload.business_name = payoutForm.business_name.trim();
      }
      const response = await api.patch("/api/landlord/settings/", payload);
      setPayoutForm({
        business_name: response.data.business_name || "",
        collection_mode: response.data.collection_mode || "custody_legacy",
        payout_method: response.data.payout_method || "",
        payout_destination: response.data.payout_destination || "",
        payout_bank_code: response.data.payout_bank_code || "",
      });
      setSuccess("Payment method saved successfully.");
    } catch (err) {
      setError(getErrorMessage(err, "Failed to save payment method."));
    } finally {
      setSaving(false);
    }
  };

  const saveCollectionAccount = async (event) => {
    event.preventDefault();
    setError("");
    setSuccess("");
    setSavingCollection(true);

    try {
      const response = await api.post("/api/landlord/collection-account/", {
        collection_method: "mpesa_paybill",
        paybill_number: collectionForm.paybill_number.trim(),
        registered_business_name: collectionForm.registered_business_name.trim(),
      });
      setCollectionForm({
        paybill_number: response.data.paybill_number || "",
        registered_business_name: response.data.registered_business_name || "",
        verification_status: response.data.verification_status || "",
      });
      setSuccess("Paybill account saved for verification.");
    } catch (err) {
      setError(getErrorMessage(err, "Failed to save Paybill account."));
    } finally {
      setSavingCollection(false);
    }
  };

  return (
    <SectionCard icon={CreditCard} title="Payout Settings">
      <p className="resident-helper-text">
        Configure where KRIB should send your landlord payouts. Tenant and manager invites stay locked until a payout method and destination are saved.
      </p>
      {error ? <p className="error">{error}</p> : null}
      {success ? <p className="success">{success}</p> : null}
      <form className="resident-form-grid" onSubmit={savePayoutSettings}>
        <label className="resident-field">
          <span>Business name</span>
          <input
            value={payoutForm.business_name}
            onChange={(event) => setPayoutForm({ ...payoutForm, business_name: event.target.value })}
            disabled={loading || saving}
          />
        </label>
        <label className="resident-field">
          <span>Rent collection mode</span>
          <select
            value={payoutForm.collection_mode}
            onChange={(event) => setPayoutForm({ ...payoutForm, collection_mode: event.target.value })}
            disabled={loading || saving}
          >
            <option value="custody_legacy">KRIB custody legacy</option>
            <option value="direct_paybill">Direct landlord Paybill</option>
          </select>
        </label>
        <label className="resident-field">
          <span>Payout method</span>
          <select
            value={payoutForm.payout_method}
            onChange={(event) => setPayoutForm({
              ...payoutForm,
              payout_method: event.target.value,
              payout_bank_code: event.target.value === "BANK" ? payoutForm.payout_bank_code : "",
            })}
            disabled={loading || saving}
          >
            <option value="">Select payout method</option>
            <option value="MPESA">M-Pesa</option>
            <option value="BANK">Bank transfer</option>
          </select>
        </label>
        <label className="resident-field">
          <span>{payoutForm.payout_method === "BANK" ? "Bank account number" : "M-Pesa phone number"}</span>
          <input
            value={payoutForm.payout_destination}
            onChange={(event) => setPayoutForm({ ...payoutForm, payout_destination: event.target.value })}
            placeholder={payoutForm.payout_method === "BANK" ? "Enter the destination account" : "e.g. 254712345678"}
            disabled={loading || saving}
          />
        </label>
        {payoutForm.payout_method === "BANK" ? (
          <label className="resident-field">
            <span>Bank code</span>
            <input
              value={payoutForm.payout_bank_code}
              onChange={(event) => setPayoutForm({ ...payoutForm, payout_bank_code: event.target.value })}
              disabled={loading || saving}
            />
          </label>
        ) : null}
        <button className="resident-primary-btn" type="submit" disabled={loading || saving}>
          <Save size={16} />
          <span>{saving ? "Saving..." : "Save Payment Method"}</span>
        </button>
      </form>
      {payoutForm.collection_mode === "direct_paybill" ? (
        <form className="resident-form-grid" onSubmit={saveCollectionAccount}>
          <label className="resident-field">
            <span>M-Pesa Paybill number</span>
            <input
              value={collectionForm.paybill_number}
              onChange={(event) => setCollectionForm({ ...collectionForm, paybill_number: event.target.value })}
              disabled={loading || savingCollection}
            />
          </label>
          <label className="resident-field">
            <span>Registered business name</span>
            <input
              value={collectionForm.registered_business_name}
              onChange={(event) => setCollectionForm({ ...collectionForm, registered_business_name: event.target.value })}
              disabled={loading || savingCollection}
            />
          </label>
          <label className="resident-field">
            <span>Verification status</span>
            <input value={collectionForm.verification_status || "not submitted"} readOnly />
          </label>
          <button className="resident-primary-btn" type="submit" disabled={loading || savingCollection}>
            <Save size={16} />
            <span>{savingCollection ? "Saving..." : "Save Paybill"}</span>
          </button>
        </form>
      ) : null}
    </SectionCard>
  );
}
