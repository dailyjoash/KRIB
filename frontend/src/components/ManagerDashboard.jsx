import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ClipboardList, Users, Wrench } from "lucide-react";
import api from "../services/api";
import { formatDateTime } from "../utils/format";
import Greeting from "./Greeting";
import StatusBadge from "./StatusBadge";
import { PageLayout, SectionCard } from "./ui";

export default function ManagerDashboard() {
  const navigate = useNavigate();
  const [maintenance, setMaintenance] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);

  const load = async () => {
    try {
      const [maintenanceRes, notificationsRes] = await Promise.all([
        api.get("/api/maintenance/"),
        api.get("/api/notifications/"),
      ]);
      setMaintenance(maintenanceRes.data || []);
      setNotifications(notificationsRes.data || []);
    } catch {
      setError("Failed to load manager data");
      setMaintenance([]);
      setNotifications([]);
    } finally {
      setLoaded(true);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const updateStatus = async (id, status) => {
    try {
      await api.patch(`/api/maintenance/${id}/`, { status });
      await load();
    } catch {
      setError("Failed to update maintenance status");
    }
  };

  const openMaintenance = maintenance.filter((item) => item.status !== "resolved");
  const unreadNotifications = notifications.filter((item) => !item.is_read);

  if (!loaded) {
    return <p className="loading">Loading...</p>;
  }

  return (
    <PageLayout variant="executive" kicker="Welcome" title={<Greeting />} chip={`${openMaintenance.length} open tickets / ${unreadNotifications.length} unread notifications`}>
      {error ? <p className="error">{error}</p> : null}

      <SectionCard title="Actions">
        <div className="manager-home-gradient-grid">
          <button className="resident-gradient-card purple manager-home-gradient-card" type="button" onClick={() => navigate("/invites/new")}>
            <div className="resident-feature-head">
              <h3>Invite Tenant</h3>
              <span className="resident-round-icon">
                <Users size={18} />
              </span>
            </div>
          </button>
          <button className="resident-gradient-card blue manager-home-gradient-card" type="button" onClick={() => navigate("/leases/new")}>
            <div className="resident-feature-head">
              <h3>Create Lease</h3>
              <span className="resident-round-icon">
                <ClipboardList size={18} />
              </span>
            </div>
          </button>
        </div>
      </SectionCard>

      <SectionCard icon={Wrench} title="Priority Queue" action={<span className="resident-chip">{openMaintenance.length} open</span>}>
        <div className="resident-table-list">
          {openMaintenance.length === 0 ? (
            <p className="subtitle">No open maintenance tickets right now.</p>
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
                  <span>{formatDateTime(item.updated_at)}</span>
                  <select onChange={(e) => updateStatus(item.id, e.target.value)} defaultValue="">
                    <option value="" disabled>Update</option>
                    <option value="open">Open</option>
                    <option value="in_progress">In Progress</option>
                    <option value="resolved">Resolved</option>
                  </select>
                </div>
              </article>
            ))
          )}
        </div>
      </SectionCard>
    </PageLayout>
  );
}
