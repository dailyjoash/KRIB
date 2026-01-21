import React, { useEffect, useState } from "react";
import api from "../services/api";
import { useNavigate, Link } from "react-router-dom";

export default function ManagerDashboard() {
  const [properties, setProperties] = useState([]);
  const [leases, setLeases] = useState([]);
  const [maintenance, setMaintenance] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const fetchData = async () => {
    try {
      const token = localStorage.getItem("access");
      if (!token) {
        navigate("/");
        return;
      }

      const config = { headers: { Authorization: `Bearer ${token}` } };

      const [pRes, lRes, mRes] = await Promise.all([
        api.get("/api/properties/", config),
        api.get("/api/leases/", config),
        api.get("/api/my-maintenance/", config),
      ]);

      setProperties(pRes.data || []);
      setLeases(lRes.data || []);
      setMaintenance(mRes.data || []);
    } catch (err) {
      console.error("Error fetching dashboard data:", err);
      if (err.response?.status === 401) {
        setError("Session expired. Please log in again.");
        handleLogout();
      } else {
        setError("Failed to load dashboard data.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("access");
    localStorage.removeItem("refresh");
    localStorage.removeItem("role");
    navigate("/");
  };

  useEffect(() => {
    fetchData();
  }, []);

  if (loading) return <p style={{ textAlign: "center" }}>⏳ Loading dashboard...</p>;

  return (
    <div className="dashboard-container">
      <div className="dashboard-header">
        <h2>👨‍💼 Manager Dashboard</h2>
        <button className="btn-secondary" onClick={handleLogout}>
          Logout
        </button>
      </div>

      {error && <p style={{ color: "red", textAlign: "center" }}>{error}</p>}

      <div className="dashboard-grid">
        {/* 🏘️ Properties */}
        <div className="card">
          <h3>Managed Properties</h3>
          {properties.length ? (
            <ul>
              {properties.map((p) => (
                <li key={p.id}>
                  <strong>{p.title}</strong> — {p.address}
                </li>
              ))}
            </ul>
          ) : (
            <p>No properties assigned yet.</p>
          )}
        </div>

        {/* 📜 Leases */}
        <div className="card">
          <h3>Leases Overview</h3>
          {leases.length ? (
            <ul>
              {leases.map((l) => (
                <li key={l.id}>
                  {l.property?.title || "Unnamed Property"} — {l.tenant?.user || "Unknown Tenant"}
                </li>
              ))}
            </ul>
          ) : (
            <p>No active leases yet.</p>
          )}
        </div>

        {/* 🧰 Maintenance */}
        <div className="card">
          <h3>Maintenance Requests</h3>
          {maintenance.length ? (
            <ul>
              {maintenance.map((m) => (
                <li key={m.id}>
                  {m.issue} — <strong>{m.status}</strong>
                </li>
              ))}
            </ul>
          ) : (
            <p>No maintenance requests found.</p>
          )}
        </div>
      </div>
    </div>
  );
}
