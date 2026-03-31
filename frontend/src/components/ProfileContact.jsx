import React, { useContext, useEffect, useMemo, useRef, useState } from "react";
import { Mail } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { AuthContext } from "../context/AuthContext";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { PageLayout, SectionCard } from "./ui";

export default function ProfileContact() {
  const { user } = useContext(AuthContext);
  const navigate = useNavigate();
  const phoneInputRef = useRef(null);
  const [me, setMe] = useState(null);
  const [form, setForm] = useState({ email: "", phone_number: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    api.get("/api/me/")
      .then((res) => {
        if (cancelled) return;
        setMe(res.data);
        setForm({
          email: res.data.email || "",
          phone_number: res.data.phone_number || "",
        });
      })
      .catch((err) => {
        if (!cancelled) {
          setError(getErrorMessage(err, "Failed to load contact details."));
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!me) return undefined;
    const timeoutId = window.setTimeout(() => phoneInputRef.current?.focus(), 140);
    return () => window.clearTimeout(timeoutId);
  }, [me]);

  const contactChanged = useMemo(() => (
    form.email !== (me?.email || "") || form.phone_number !== (me?.phone_number || "")
  ), [form.email, form.phone_number, me?.email, me?.phone_number]);

  const resetForm = () => {
    setForm({
      email: me?.email || "",
      phone_number: me?.phone_number || "",
    });
  };

  const saveProfile = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");

    try {
      const res = await api.patch("/api/me/", form);
      setMe(res.data);
      setForm({
        email: res.data.email || "",
        phone_number: res.data.phone_number || "",
      });
      setMessage("Contact details updated successfully.");
    } catch (err) {
      setError(getErrorMessage(err, "Failed to update contact details."));
    }
  };

  if (!me) {
    if (error) {
      return (
        <div className={user?.role === "landlord" ? "dashboard-container" : "resident-page"}>
          <p className="error">{error}</p>
        </div>
      );
    }
    return <p className="loading">Loading...</p>;
  }

  const isExecutive = user?.role === "landlord";
  const accountLabel = isExecutive ? "landlord" : user?.role === "manager" ? "manager" : "tenant";
  const content = (
    <>
      {message ? <p className="success">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}

      <SectionCard
        icon={Mail}
        title="Update Contact Details"
        action={<button className="resident-link-btn" type="button" onClick={() => navigate("/profile")}>Back to profile</button>}
      >
        <div className="resident-profile-inline-summary">
          <div className="resident-profile-inline-item">
            <span>Current phone</span>
            <strong>{me.phone_number || "Add phone"}</strong>
          </div>
          <div className="resident-profile-inline-item">
            <span>Current email</span>
            <strong>{me.email || "Add email"}</strong>
          </div>
        </div>
        <form className="resident-form-grid" onSubmit={saveProfile}>
          <p className="resident-form-note">
            Update the phone number and email linked to your {accountLabel} account.
          </p>
          <label className="resident-field">
            <span>Phone number</span>
            <input ref={phoneInputRef} type="tel" value={form.phone_number} onChange={(e) => setForm({ ...form, phone_number: e.target.value })} placeholder="Phone number" />
          </label>
          <label className="resident-field">
            <span>Email address</span>
            <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="Email address" />
          </label>
          <div className="resident-form-actions resident-profile-form-actions">
            <button className="resident-link-btn" type="button" onClick={resetForm} disabled={!contactChanged}>Reset</button>
            <button className="resident-primary-btn" type="submit" disabled={!contactChanged}>Save Changes</button>
          </div>
        </form>
      </SectionCard>
    </>
  );

  if (isExecutive) {
    return (
      <PageLayout variant="executive" kicker="Account" title="Contact Details">
        {content}
      </PageLayout>
    );
  }

  return (
    <div className="resident-page">
      {content}
    </div>
  );
}
