import React, { useEffect, useMemo, useState } from "react";
import { ReceiptText } from "lucide-react";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";
import { formatDateTime, formatKES } from "../utils/format";
import StatusBadge from "./StatusBadge";
import { PageLayout, SectionCard } from "./ui";

export default function ManagerReview() {
  const [payments, setPayments] = useState([]);
  const [period, setPeriod] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const params = { status: "SUCCESS" };
        if (period) params.period = period;
        const res = await api.get("/api/payments/", { params });
        setPayments(res.data || []);
      } catch (err) {
        setError(getErrorMessage(err, "Failed to load payment review."));
      }
    };
    load();
  }, [period]);

  const rows = useMemo(() => {
    const latestByLease = new Map();

    payments.forEach((payment) => {
      const leaseId = payment.lease?.id || `${payment.tenant?.id || payment.tenant?.username}-${payment.lease?.unit?.property?.name || ""}-${payment.lease?.unit?.unit_number || ""}`;
      const paymentDate = new Date(payment.transaction_date || payment.created_at || 0).getTime();
      const current = latestByLease.get(leaseId);
      const currentDate = current ? new Date(current.transaction_date || current.created_at || 0).getTime() : 0;

      if (!current || paymentDate >= currentDate) {
        latestByLease.set(leaseId, payment);
      }
    });

    return Array.from(latestByLease.values()).sort((left, right) => {
      const leftProperty = left.lease?.unit?.property?.name || "";
      const rightProperty = right.lease?.unit?.property?.name || "";
      const propertySort = leftProperty.localeCompare(rightProperty, undefined, { sensitivity: "base" });
      if (propertySort !== 0) return propertySort;

      const leftUnit = left.lease?.unit?.unit_number || "";
      const rightUnit = right.lease?.unit?.unit_number || "";
      const unitSort = leftUnit.localeCompare(rightUnit, undefined, { numeric: true, sensitivity: "base" });
      if (unitSort !== 0) return unitSort;

      const leftTenant = left.tenant?.username || left.tenant?.email || "";
      const rightTenant = right.tenant?.username || right.tenant?.email || "";
      return leftTenant.localeCompare(rightTenant, undefined, { sensitivity: "base" });
    });
  }, [payments]);

  return (
    <PageLayout variant="executive" kicker="Manager Review" title="Paid Rent Review" chip={`${rows.length} paid tenants`}>
      {error ? <p className="error">{error}</p> : null}

      <SectionCard icon={ReceiptText} title="Paid Tenants" action={<input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />}>
        <div className="resident-table-list">
          {rows.length === 0 ? (
            <p className="resident-helper-text">No paid tenants found for this period.</p>
          ) : (
            rows.map((row, index) => (
              <article className="resident-row-card" key={row.id}>
                <div className="resident-row-id">{index + 1}</div>
                <div className="resident-profile-columns manager-review-columns">
                  <div className="resident-profile-item">
                    <span>Name</span>
                    <strong>{row.tenant?.username || row.tenant?.email || "-"}</strong>
                  </div>
                  <div className="resident-profile-item">
                    <span>Unit</span>
                    <strong>{row.lease?.unit ? `${row.lease.unit.property?.name || "-"} / ${row.lease.unit.unit_number}` : "-"}</strong>
                  </div>
                  <div className="resident-profile-item">
                    <span>Last rent transaction date</span>
                    <strong>{formatDateTime(row.transaction_date || row.created_at)}</strong>
                  </div>
                  <div className="resident-profile-item">
                    <span>M-Pesa code</span>
                    <strong>{row.mpesa_receipt || row.transaction_code || "-"}</strong>
                  </div>
                  <div className="resident-profile-item">
                    <span>Status</span>
                    <StatusBadge status={row.status} />
                  </div>
                </div>
              </article>
            ))
          )}
        </div>
      </SectionCard>
    </PageLayout>
  );
}
