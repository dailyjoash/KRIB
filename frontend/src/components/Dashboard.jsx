import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2, ClipboardList, ShieldCheck, Users, Wrench } from "lucide-react";
import api from "../services/api";
import Greeting from "./Greeting";
import StatusBadge from "./StatusBadge";
import { PageLayout, SectionCard } from "./ui";

export default function Dashboard() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [properties, setProperties] = useState([]);
  const [units, setUnits] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const [summaryRes, propertiesRes, unitsRes] = await Promise.all([
          api.get("/api/dashboard/summary/"),
          api.get("/api/properties/"),
          api.get("/api/units/"),
        ]);
        setSummary(summaryRes.data);
        setProperties(propertiesRes.data || []);
        setUnits(unitsRes.data || []);
      } catch {
        setError("Failed to load dashboard");
        setSummary({ period: "-", totals: { expected: 0, collected: 0, outstanding: 0 }, maintenance: [] });
        setProperties([]);
        setUnits([]);
      }
    };
    load();
  }, []);

  const occupancy = useMemo(() => {
    const occupied = units.filter((unit) => unit.status === "occupied").length;
    return { occupied, vacant: Math.max(units.length - occupied, 0) };
  }, [units]);

  const openMaintenance = (summary?.maintenance || []).filter((item) => item.status !== "resolved");

  if (!summary) {
    return <p className="loading">Loading dashboard...</p>;
  }

  return (
    <PageLayout variant="executive" kicker="Welcome" title={<Greeting />} chip={`${properties.length} properties / ${units.length} units`}>
      {error ? <p className="error">{error}</p> : null}

      <section className="resident-summary-card">
        <div className="resident-summary-main">
          <div className="resident-summary-thumb">
            <Building2 size={28} />
          </div>
          <div>
            <h3>Portfolio</h3>
            <p>{occupancy.occupied} occupied / {occupancy.vacant} vacant</p>
          </div>
        </div>
      </section>

      <SectionCard title="Actions">
        <div className="landlord-home-action-grid">
          <button className="resident-gradient-card purple landlord-home-action-card" type="button" onClick={() => navigate("/landlord/invites?section=tenant")}>
            <div className="resident-feature-head">
              <h3>Invite Tenant</h3>
              <span className="resident-round-icon">
                <Users size={18} />
              </span>
            </div>
          </button>
          <button className="resident-gradient-card blue landlord-home-action-card" type="button" onClick={() => navigate("/leases/new")}>
            <div className="resident-feature-head">
              <h3>Create Lease</h3>
              <span className="resident-round-icon">
                <ClipboardList size={18} />
              </span>
            </div>
          </button>
          <button className="resident-gradient-card mint landlord-home-action-card" type="button" onClick={() => navigate("/landlord/invites?section=manager")}>
            <div className="resident-feature-head">
              <h3>Invite Manager</h3>
              <span className="resident-round-icon">
                <ShieldCheck size={18} />
              </span>
            </div>
          </button>
        </div>
      </SectionCard>

      <SectionCard icon={Wrench} title="Maintenance Requests" action={<button className="resident-link-btn" type="button" onClick={() => navigate("/notifications")}>Open Alerts</button>}>
        <div className="resident-table-list">
          {openMaintenance.length === 0 ? (
            <p className="subtitle">No maintenance requests right now.</p>
          ) : (
            openMaintenance.slice(0, 4).map((item, index) => (
              <article className="resident-row-card" key={item.id}>
                <div className="resident-row-id">{index + 1}</div>
                <div className="resident-row-main">
                  <h4>{item.tenant?.username || "Tenant"}</h4>
                  <p>{item.lease?.unit ? `${item.lease.unit.property?.name || "-"} / ${item.lease.unit.unit_number}` : "-"}</p>
                  <p>{item.issue}</p>
                </div>
                <div className="resident-row-meta">
                  {item.urgency ? <StatusBadge status={item.urgency} /> : null}
                  <StatusBadge status={item.status} />
                </div>
              </article>
            ))
          )}
        </div>
      </SectionCard>
    </PageLayout>
  );
}
