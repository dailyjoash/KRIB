import React, { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "../services/api";

export default function TenantDashboard() {
  const [lease, setLease] = useState(null);
  const [payments, setPayments] = useState([]);
  const [maintenance, setMaintenance] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const token = localStorage.getItem("access");

  const fetchTenantData = async () => {
    if (!token) {
      navigate("/");
      return;
    }

    try {
      const [leaseRes, payRes, maintRes] = await Promise.all([
        api.get("/api/leases/my-lease/"),
        api.get("/api/payments/"),
        api.get("/api/maintenance/"),
      ]);

      setLease(leaseRes.data || null);
      setPayments(payRes.data || []);
      setMaintenance(maintRes.data || []);
    } catch (err) {
      console.error("Error fetching tenant dashboard:", err);
      if (err.response?.status === 401) {
        setError("Session expired. Please log in again.");
        handleLogout();
      } else {
        setError("Failed to load tenant data.");
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
    fetchTenantData();
  }, []);

  if (loading) return <p className="text-center text-gray-500 mt-10">⏳ Loading tenant dashboard...</p>;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-3xl font-bold text-gray-800">👨‍💼 Tenant Dashboard</h2>
        <button
          onClick={handleLogout}
          className="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded-md"
        >
          Logout
        </button>
      </div>

      {error && <p className="text-red-500 text-center">{error}</p>}

      <div className="grid md:grid-cols-3 gap-6">
        {/* 📄 Lease Info */}
        <div className="bg-white shadow-md rounded-xl p-4">
          <h3 className="text-xl font-semibold mb-3">My Lease</h3>
          {lease ? (
            <div>
              <p><strong>Property:</strong> {lease.property?.title}</p>
              <p><strong>Rent:</strong> {lease.rent_amount} KES/month</p>
              <p><strong>Status:</strong>{" "}
                <span className={lease.is_active ? "text-green-600" : "text-gray-500"}>
                  {lease.is_active ? "Active" : "Ended"}
                </span>
              </p>
            </div>
          ) : (
            <p className="text-gray-500">No active lease found.</p>
          )}
        </div>

        {/* 💰 Payments */}
        <div className="bg-white shadow-md rounded-xl p-4">
          <h3 className="text-xl font-semibold mb-3">Rent Payments</h3>
          {payments.length ? (
            <ul className="space-y-2">
              {payments.map((p) => (
                <li key={p.id} className="border-b pb-1">
                  <strong>{p.amount} KES</strong> —{" "}
                  <span className={p.status === "Paid" ? "text-green-600" : "text-yellow-600"}>
                    {p.status}
                  </span>
                  <p className="text-sm text-gray-500">{p.date}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-gray-500">No payments yet.</p>
          )}
        </div>

        {/* 🛠️ Maintenance */}
        <div className="bg-white shadow-md rounded-xl p-4">
          <h3 className="text-xl font-semibold mb-3">Maintenance Requests</h3>
          <Link
            to="/maintenance/new"
            className="inline-block bg-yellow-500 text-white px-3 py-1 rounded-md mb-3"
          >
            + New Request
          </Link>
          {maintenance.length ? (
            <ul className="space-y-2">
              {maintenance.map((m) => (
                <li key={m.id} className="border-b pb-1">
                  {m.issue} —{" "}
                  <span
                    className={`text-sm font-medium ${
                      m.status === "Pending"
                        ? "text-yellow-600"
                        : m.status === "Resolved"
                        ? "text-green-600"
                        : "text-gray-500"
                    }`}
                  >
                    {m.status}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-gray-500">No maintenance requests yet.</p>
          )}
        </div>
      </div>
    </div>
  );
}
