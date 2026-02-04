import React, { useEffect, useState } from "react";
import api from "../services/api";
import { useNavigate, Link } from "react-router-dom";

export default function Dashboard() {
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

      const [pRes, lRes, mRes] = await Promise.all([
        api.get("/api/properties/"),
        api.get("/api/leases/"),
        api.get("/api/maintenance/"),
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

  if (loading) return <p className="loading">⏳ Loading dashboard...</p>;

  return (
    <div className="dashboard-container">
      <header className="dashboard-header">
        <h2>🏠 Landlord Dashboard</h2>
        <button className="btn-secondary" onClick={handleLogout}>
          Logout
        </button>
      </header>

      {error && <p className="error">{error}</p>}

      <div className="dashboard-grid">
        {/* 🏡 Properties */}
        <div className="card">
          <h3>My Properties</h3>
          <Link to="/properties/new" className="btn-primary">
            + Add Property
          </Link>
          {properties.length ? (
            <ul>
              {properties.map((p) => (
                <li key={p.id}>
                  <strong>{p.title}</strong> <br />
                  <small>{p.address}</small>
                </li>
              ))}
            </ul>
          ) : (
            <p>No properties yet.</p>
          )}
        </div>

        {/* 📄 Leases */}
        <div className="card">
          <h3>Active Leases</h3>
          {leases.length ? (
            <ul>
              {leases.map((l) => (
                <li key={l.id}>
                  {l.property?.title || "Unnamed Property"} –{" "}
                  <strong>{l.rent_amount} KES</strong>
                </li>
              ))}
            </ul>
          ) : (
            <p>No active leases.</p>
          )}
        </div>

        {/* 🛠️ Maintenance */}
        <div className="card">
          <h3>Maintenance Requests</h3>
          <Link to="/maintenance/new" className="btn-primary">
            + Report Issue
          </Link>
          {maintenance.length ? (
            <ul>
              {maintenance.map((m) => (
                <li key={m.id}>
                  {m.issue} – <strong>{m.status}</strong>
                </li>
              ))}
            </ul>
          ) : (
            <p>No issues reported yet.</p>
          )}
        </div>
      </div>
    </div>
  );
}
