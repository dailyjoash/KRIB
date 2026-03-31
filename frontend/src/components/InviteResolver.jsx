import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api from "../services/api";

export default function InviteResolver() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    const resolveInvite = async () => {
      try {
        await api.get(`/api/invites/${token}/`);
        if (active) {
          navigate(`/invite/tenant/${token}`, { replace: true });
        }
      } catch {
        if (active) {
          navigate(`/invite/manager/${token}`, { replace: true });
        }
      }
    };

    if (!token) {
      setError("Invite token is missing.");
      return () => {
        active = false;
      };
    }

    resolveInvite();
    return () => {
      active = false;
    };
  }, [navigate, token]);

  return (
    <div className="dashboard-container">
      {error ? <p className="error">{error}</p> : <p className="loading">Resolving invite...</p>}
    </div>
  );
}
