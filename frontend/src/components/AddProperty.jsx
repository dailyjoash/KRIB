import React, { useState } from "react";
import api from "../services/api";
import { useNavigate } from "react-router-dom";

export default function AddProperty() {
  const [title, setTitle] = useState("");
  const [address, setAddress] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage("");

    try {
      const token = localStorage.getItem("access");
      const config = { headers: { Authorization: `Bearer ${token}` } };

      await api.post("/api/properties/", { title, address }, config);

      setMessage("✅ Property added successfully!");
      setTimeout(() => navigate("/dashboard"), 1500);
    } catch (error) {
      console.error("Error adding property:", error);
      setMessage("❌ Failed to add property. Try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="dashboard-container">
      <div className="card" style={{ maxWidth: "500px", margin: "auto" }}>
        <h2>Add New Property 🏠</h2>
        <form onSubmit={handleSubmit}>
          <label>Property Title</label>
          <input
            type="text"
            placeholder="e.g., Sunset Apartments"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />

          <label>Address</label>
          <input
            type="text"
            placeholder="e.g., 123 Nairobi Lane, Kenya"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            required
          />

          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? "Adding..." : "Add Property"}
          </button>
        </form>

        {message && <p style={{ marginTop: "10px" }}>{message}</p>}

        <button
          className="btn-secondary"
          style={{ marginTop: "10px" }}
          onClick={() => navigate("/dashboard")}
        >
          ← Back to Dashboard
        </button>
      </div>
    </div>
  );
}
