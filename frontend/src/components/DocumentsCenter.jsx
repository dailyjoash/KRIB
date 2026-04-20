import React, { useContext, useEffect, useMemo, useRef, useState } from "react";
import { Download, Eye, FileBadge2, FileText, Search, ShieldCheck, UserMinus, X } from "lucide-react";
import api from "../services/api";
import { AuthContext } from "../context/AuthContext";
import { getErrorMessage } from "../utils/errors";
import { downloadBlob, fetchBlobFile } from "../utils/files";
import { formatDate, formatKES } from "../utils/format";
import GlassCard from "./GlassCard";
import StatusBadge from "./StatusBadge";

const typeLabel = {
  lease: "Lease Document",
  identity: "ID / Passport",
  receipt: "Receipt Archive",
  other: "Document",
};

const matchesDocumentQuery = (document, query) => {
  if (!query) return true;
  const haystack = [
    document.property_name,
    document.tenant_name,
    document.unit_label,
    document.uploaded_by_name,
    document.document_type,
    document.upload_date,
    document.file_name,
  ].filter(Boolean).join(" ").toLowerCase();
  return haystack.includes(query);
};

const sortLeasesByUnit = (left, right) => {
  const leftLabel = `${left.unit?.property?.name || ""}-${left.unit?.unit_number || ""}`;
  const rightLabel = `${right.unit?.property?.name || ""}-${right.unit?.unit_number || ""}`;
  return leftLabel.localeCompare(rightLabel, undefined, { numeric: true, sensitivity: "base" });
};

const buildDocumentIndex = (rows, keyBuilder) => {
  const index = new Map();
  rows.forEach((row) => {
    const key = keyBuilder(row);
    if (key === null || key === undefined || key === "") return;
    if (!index.has(key)) {
      index.set(key, row);
    }
  });
  return index;
};

const HOUSE_RULE_KEYWORDS = ["house rule", "house rules", "tenant rule", "tenant rules", "building rules", "rules and regulations"];

const isHouseRulesDocument = (document) => {
  const haystack = [
    document.file_name,
    document.property_name,
    document.unit_label,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  return HOUSE_RULE_KEYWORDS.some((keyword) => haystack.includes(keyword));
};

const matchesLeaseStorageQuery = ({ lease, leaseDocument, identityDocument }, query) => {
  if (!query) return true;
  const haystack = [
    lease.tenant?.username,
    lease.unit?.property?.name,
    lease.unit?.unit_number,
    leaseDocument?.file_name,
    identityDocument?.file_name,
  ].filter(Boolean).join(" ").toLowerCase();
  return haystack.includes(query);
};

const sortLeasesByCurrentTenantPriority = (left, right) => {
  const leftActive = String(left.status || "").toLowerCase() === "active";
  const rightActive = String(right.status || "").toLowerCase() === "active";
  if (leftActive !== rightActive) return leftActive ? -1 : 1;

  const leftStart = left.start_date ? new Date(left.start_date).getTime() : 0;
  const rightStart = right.start_date ? new Date(right.start_date).getTime() : 0;
  return rightStart - leftStart;
};

export default function DocumentsCenter() {
  const { user } = useContext(AuthContext);
  const previewUrlRef = useRef(null);

  const [leases, setLeases] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [query, setQuery] = useState("");
  const [viewFilter, setViewFilter] = useState("all");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [preview, setPreview] = useState(null);
  const [leaseToRemove, setLeaseToRemove] = useState(null);
  const [removingTenant, setRemovingTenant] = useState(false);

  const clearPreview = () => {
    if (previewUrlRef.current) {
      window.URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = null;
    }
    setPreview(null);
  };

  useEffect(() => () => clearPreview(), []);

  const load = async () => {
    try {
      const [leasesRes, documentsRes] = await Promise.all([
        api.get("/api/leases/"),
        api.get("/api/documents/"),
      ]);
      setLeases(leasesRes.data || []);
      setDocuments(documentsRes.data || []);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load document center."));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const confirmRemoveTenant = async () => {
    if (!leaseToRemove) return;

    setRemovingTenant(true);
    setError("");
    setSuccess("");

    try {
      await api.post(`/api/leases/${leaseToRemove.id}/remove-tenant/`);
      setSuccess(
        `Tenant removed from ${leaseToRemove.unit?.property?.name || "the property"} / Unit ${leaseToRemove.unit?.unit_number || "-"}.`
      );
      setLeaseToRemove(null);
      clearPreview();
      await load();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to remove tenant."));
    } finally {
      setRemovingTenant(false);
    }
  };

  const visibleLeases = useMemo(() => {
    if (user?.role === "tenant") {
      return leases
        .filter((lease) => lease.status === "active")
        .slice()
        .sort(sortLeasesByCurrentTenantPriority)
        .slice(0, 1);
    }
    return leases.filter((lease) => lease.status === "active");
  }, [leases, user?.role]);

  const currentLease = visibleLeases[0] || null;
  const allLeaseDocuments = useMemo(
    () => documents.filter((document) => document.document_type === "lease"),
    [documents]
  );
  const allOtherDocuments = useMemo(
    () => documents.filter((document) => document.document_type === "other"),
    [documents]
  );
  const activePropertyId = currentLease?.unit?.property?.id || null;
  const activeTenantId = currentLease?.tenant?.id || null;
  const identityDocument = useMemo(() => {
    if (!currentLease) return null;
    return (
      documents.find(
        (document) =>
          document.document_type === "identity" &&
          document.lease === currentLease.id
      ) ||
      documents.find(
        (document) =>
          document.document_type === "identity" &&
          document.tenant === activeTenantId &&
          document.property === activePropertyId
      ) ||
      documents.find(
        (document) =>
          document.document_type === "identity" &&
          document.tenant === activeTenantId
      ) ||
      null
    );
  }, [activePropertyId, activeTenantId, currentLease, documents]);
  const agreementDocument = useMemo(() => {
    if (!currentLease) return null;
    return (
      allLeaseDocuments.find((document) => document.lease === currentLease.id) ||
      allLeaseDocuments.find(
        (document) =>
          document.tenant === activeTenantId &&
          document.property === activePropertyId
      ) ||
      null
    );
  }, [activePropertyId, activeTenantId, allLeaseDocuments, currentLease]);
  const houseRulesDocument = useMemo(() => {
    if (!activePropertyId) return null;
    return (
      allOtherDocuments.find(
        (document) =>
          document.property === activePropertyId &&
          isHouseRulesDocument(document)
      ) || null
    );
  }, [activePropertyId, allOtherDocuments]);
  const loweredQuery = query.trim().toLowerCase();
  const leaseDocumentByLease = useMemo(
    () => buildDocumentIndex(allLeaseDocuments, (document) => document.lease),
    [allLeaseDocuments]
  );
  const identityDocumentByLease = useMemo(
    () => buildDocumentIndex(
      documents.filter((document) => document.document_type === "identity" && document.lease),
      (document) => document.lease
    ),
    [documents]
  );
  const identityDocumentByTenant = useMemo(
    () => buildDocumentIndex(
      documents.filter((document) => document.document_type === "identity" && document.tenant),
      (document) => document.tenant
    ),
    [documents]
  );
  const leaseStorageRows = useMemo(
    () => visibleLeases
      .filter((lease) => String(lease.status || "").toLowerCase() === "active")
      .slice()
      .sort(sortLeasesByUnit)
      .map((lease) => ({
        lease,
        leaseDocument: leaseDocumentByLease.get(lease.id) || null,
        identityDocument: identityDocumentByLease.get(lease.id) || identityDocumentByTenant.get(lease.tenant?.id) || null,
      }))
      .filter((row) => matchesLeaseStorageQuery(row, loweredQuery)),
    [visibleLeases, leaseDocumentByLease, identityDocumentByLease, identityDocumentByTenant, loweredQuery]
  );

  const downloadDocument = async (document) => {
    try {
      await downloadBlob(`/api/documents/${document.id}/download/`, `krib-document-${document.id}.pdf`);
    } catch (err) {
      setError(getErrorMessage(err, "Unable to download document."));
    }
  };

  const openPreview = async (sourceUrl, title, fallbackName) => {
    setError("");
    try {
      const { blob, filename, contentType } = await fetchBlobFile(sourceUrl, fallbackName);
      clearPreview();
      const objectUrl = window.URL.createObjectURL(blob);
      previewUrlRef.current = objectUrl;
      const lowerName = String(filename || fallbackName || "").toLowerCase();
      const kind = contentType.includes("pdf") || lowerName.endsWith(".pdf") ? "pdf" : "image";
      setPreview({ title, url: objectUrl, filename, kind });
    } catch (err) {
      setError(getErrorMessage(err, "Unable to open document preview."));
    }
  };

  const openDocumentPreview = async (document) => openPreview(
    `/api/documents/${document.id}/download/`,
    `${typeLabel[document.document_type] || "Document"}${document.tenant_name ? ` / ${document.tenant_name}` : ""}`,
    document.file_name || `krib-document-${document.id}.pdf`
  );

  const downloadPreviewFile = () => {
    if (!preview?.url || !preview?.filename) return;
    const link = document.createElement("a");
    link.href = preview.url;
    link.download = preview.filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  const filteredDocuments = useMemo(
    () => documents.filter((document) => matchesDocumentQuery(document, loweredQuery)),
    [documents, loweredQuery]
  );

  const otherDocuments = useMemo(() => {
    if (!["all", "other"].includes(viewFilter)) return [];
    return filteredDocuments.filter((document) => document.document_type === "other");
  }, [filteredDocuments, viewFilter]);

  if (user?.role === "tenant") {
    return (
      <div className="resident-page">
        {error ? <p className="error">{error}</p> : null}

        <section className="resident-section-card">
          <div className="resident-title-row">
            <ShieldCheck size={18} />
            <h3>Shared Documents</h3>
          </div>

          <div className="resident-document-grid">
            <article className="resident-document-card">
              <div className="resident-document-title">
                <span className="resident-mini-icon"><ShieldCheck size={14} /></span>
                <h4>Identification Document</h4>
              </div>
              <div className="resident-document-preview">
                <StatusBadge status={identityDocument ? "approved" : "pending"} />
                <div className="resident-pdf-icon">{identityDocument?.file_name?.toLowerCase().endsWith(".pdf") ? "PDF" : "ID"}</div>
              </div>
              <div className="resident-document-meta">
                <div>
                  <span>Property</span>
                  <strong>{identityDocument?.property_name || currentLease?.unit?.property?.name || "-"}</strong>
                </div>
                <div>
                  <span>Uploaded</span>
                  <strong>{identityDocument ? formatDate(identityDocument.upload_date) : "Pending"}</strong>
                </div>
              </div>
              {identityDocument ? (
                <div className="resident-form-actions">
                  <button className="resident-link-btn" type="button" onClick={() => openDocumentPreview(identityDocument)}>View</button>
                  <button className="resident-link-btn" type="button" onClick={() => downloadDocument(identityDocument)}>Download</button>
                </div>
              ) : null}
            </article>

            <article className="resident-document-card">
              <div className="resident-document-title">
                <span className="resident-mini-icon"><FileBadge2 size={14} /></span>
                <h4>Tenant Agreement / Lease Document</h4>
              </div>
              <div className="resident-document-preview">
                <StatusBadge status={agreementDocument ? "approved" : "pending"} />
                <div className="resident-pdf-icon">PDF</div>
              </div>
              <div className="resident-document-meta">
                <div>
                  <span>Property</span>
                  <strong>{agreementDocument?.property_name || currentLease?.unit?.property?.name || "-"}</strong>
                </div>
                <div>
                  <span>Uploaded</span>
                  <strong>{agreementDocument ? formatDate(agreementDocument.upload_date) : "Pending"}</strong>
                </div>
                <div>
                  <span>Unit</span>
                  <strong>{currentLease?.unit?.unit_number || "-"}</strong>
                </div>
                <div>
                  <span>Monthly Rent</span>
                  <strong>{currentLease ? formatKES(currentLease.rent_amount) : "-"}</strong>
                </div>
              </div>
              {agreementDocument ? (
                <div className="resident-form-actions">
                  <button className="resident-link-btn" type="button" onClick={() => openDocumentPreview(agreementDocument)}>View</button>
                  <button className="resident-link-btn" type="button" onClick={() => downloadDocument(agreementDocument)}>Download</button>
                </div>
              ) : null}
            </article>

            <article className="resident-document-card">
              <div className="resident-document-title">
                <span className="resident-mini-icon"><FileText size={14} /></span>
                <h4>House Rules</h4>
              </div>
              <div className="resident-document-preview">
                <StatusBadge status={houseRulesDocument ? "approved" : "pending"} />
                <div className="resident-pdf-icon">PDF</div>
              </div>
              <div className="resident-document-meta">
                <div>
                  <span>Property</span>
                  <strong>{houseRulesDocument?.property_name || currentLease?.unit?.property?.name || "-"}</strong>
                </div>
                <div>
                  <span>Uploaded</span>
                  <strong>{houseRulesDocument ? formatDate(houseRulesDocument.upload_date) : "Pending"}</strong>
                </div>
              </div>
              {houseRulesDocument ? (
                <div className="resident-form-actions">
                  <button className="resident-link-btn" type="button" onClick={() => openDocumentPreview(houseRulesDocument)}>View</button>
                  <button className="resident-link-btn" type="button" onClick={() => downloadDocument(houseRulesDocument)}>Download</button>
                </div>
              ) : null}
            </article>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="dashboard-container">
      {error ? <p className="error">{error}</p> : null}
      {success ? <p className="success">{success}</p> : null}

      <GlassCard
        title="Document Tools"
        actions={<span className="subtitle">{filteredDocuments.length} files</span>}
      >
        <div className="resident-toolbar">
          <label className="resident-search">
            <Search size={16} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Search units, tenants, or documents" />
          </label>
          <label className="resident-inline-control">
            <FileText size={16} />
            <select value={viewFilter} onChange={(event) => setViewFilter(event.target.value)}>
              <option value="all">All</option>
              <option value="other">Other files</option>
            </select>
          </label>
        </div>

      </GlassCard>

      <GlassCard title="Current Lease Storage" actions={<span className="subtitle">{leaseStorageRows.length} active leases</span>}>
        {leaseStorageRows.length === 0 ? (
          <p>No active leases are available yet.</p>
        ) : (
          <div className="lease-storage-register">
            <div className="lease-storage-register-head">
              <span>Unit</span>
              <span>Name</span>
              <span>Identification</span>
              <span>Lease Agreement</span>
              <span>Actions</span>
            </div>
            {leaseStorageRows.map(({ lease, leaseDocument, identityDocument }) => (
              <article className="lease-storage-row" key={lease.id}>
                <div className="lease-storage-cell">
                  <div>
                    <h4>{lease.unit?.unit_number || "-"}</h4>
                    <p className="subtitle">{lease.unit?.property?.name || "Property"}</p>
                  </div>
                </div>

                <div className="lease-storage-cell">
                  <div>
                    <h4>{lease.tenant?.username || "Tenant"}</h4>
                    <p className="subtitle">
                      Start {formatDate(lease.start_date)} / {formatKES(lease.rent_amount)}
                    </p>
                  </div>
                </div>

                <div className="lease-storage-cell">
                  {identityDocument ? (
                    <div className="lease-storage-actions">
                      <button className="btn" type="button" onClick={() => openDocumentPreview(identityDocument)}>
                        <Eye size={16} />
                        <span>View</span>
                      </button>
                      <button className="btn btn-primary" type="button" onClick={() => downloadDocument(identityDocument)}>
                        <Download size={16} />
                        <span>Download</span>
                      </button>
                      <p className="subtitle">Captured {formatDate(identityDocument.upload_date)}</p>
                    </div>
                  ) : (
                    <p className="subtitle">Pending capture</p>
                  )}
                </div>

                <div className="lease-storage-cell">
                  {leaseDocument ? (
                    <div className="lease-storage-actions">
                      <button className="btn" type="button" onClick={() => openDocumentPreview(leaseDocument)}>
                        <Eye size={16} />
                        <span>View</span>
                      </button>
                      <button className="btn btn-primary" type="button" onClick={() => downloadDocument(leaseDocument)}>
                        <Download size={16} />
                        <span>Download</span>
                      </button>
                      <p className="subtitle">Generated {formatDate(leaseDocument.upload_date)}</p>
                    </div>
                  ) : (
                    <p className="subtitle">Pending generation</p>
                  )}
                </div>

                <div className="lease-storage-cell lease-storage-cell--actions">
                  <div className="lease-storage-actions lease-storage-actions--danger">
                    <button className="btn btn-glass" type="button" onClick={() => setLeaseToRemove(lease)}>
                      <UserMinus size={16} />
                      <span>Remove Tenant</span>
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </GlassCard>

      {otherDocuments.length || viewFilter === "other" ? (
        <GlassCard title="Other Records" actions={<FileText size={16} />}>
          {otherDocuments.length === 0 ? (
            <p>No supporting files match the current search.</p>
          ) : (
            <div className="stack-list">
              {otherDocuments.map((document) => (
                <article className="stack-item" key={document.id}>
                  <div className="stack-item-main">
                    <div className="stack-item-icon"><FileText size={18} /></div>
                    <div>
                      <h4>{document.property_name || "Document"}</h4>
                      <p className="subtitle">{typeLabel[document.document_type] || "Record"} / {formatDate(document.upload_date)}</p>
                      <p className="subtitle">Shared by {document.uploaded_by_name || "KRIB"}</p>
                    </div>
                  </div>
                  <div className="stack-item-side">
                    <button className="btn" type="button" onClick={() => openDocumentPreview(document)}>
                      <Eye size={16} />
                      <span>View</span>
                    </button>
                    <button className="btn btn-glass" type="button" onClick={() => downloadDocument(document)}>
                      <Download size={16} />
                      <span>Download</span>
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </GlassCard>
      ) : null}

      {preview ? (
        <div className="resident-modal-backdrop" role="presentation" onClick={clearPreview}>
          <div className="document-preview-modal" role="dialog" aria-modal="true" aria-labelledby="document-preview-title" onClick={(event) => event.stopPropagation()}>
            <div className="document-preview-head">
              <div>
                <h3 id="document-preview-title">{preview.title}</h3>
                <p>{preview.filename}</p>
              </div>
              <button className="icon-btn" type="button" onClick={clearPreview} aria-label="Close preview">
                <X size={16} />
              </button>
            </div>
            <div className="document-preview-frame">
              {preview.kind === "pdf" ? (
                <iframe title={preview.title} src={preview.url} className="document-preview-embed" />
              ) : (
                <img src={preview.url} alt={preview.title} className="document-preview-image" />
              )}
            </div>
            <div className="resident-form-actions document-preview-actions">
              <button className="btn" type="button" onClick={clearPreview}>Close</button>
              <button className="btn btn-primary" type="button" onClick={downloadPreviewFile}>
                <Download size={16} />
                <span>Download</span>
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {leaseToRemove ? (
        <div className="resident-modal-backdrop" role="presentation" onClick={() => setLeaseToRemove(null)}>
          <div className="resident-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="remove-tenant-storage-title" onClick={(event) => event.stopPropagation()}>
            <div className="resident-confirm-copy">
              <h3 id="remove-tenant-storage-title">Remove tenant from unit?</h3>
              <p>
                This will end the active lease for {leaseToRemove.tenant?.username || "the tenant"} in {leaseToRemove.unit?.property?.name || "the property"} / Unit {leaseToRemove.unit?.unit_number || "-"} and mark the unit as vacant. The tenant account, payment history, and document history will stay in KRIB.
              </p>
            </div>
            <div className="resident-form-actions resident-confirm-actions">
              <button className="btn" type="button" onClick={() => setLeaseToRemove(null)} disabled={removingTenant}>
                Cancel
              </button>
              <button className="btn btn-primary" type="button" onClick={confirmRemoveTenant} disabled={removingTenant}>
                {removingTenant ? "Removing..." : "Remove Tenant"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
