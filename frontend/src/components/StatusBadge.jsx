import React from "react";

const normalizeStatus = (status = "") => status.toString().toLowerCase().replace(/\s+/g, "_");

export default function StatusBadge({ status }) {
  const normalized = normalizeStatus(status);
  return <span className={`status-badge status-${normalized}`}>{status || "unknown"}</span>;
}
