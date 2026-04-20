import React, { useEffect, useMemo, useState } from "react";
import { Download, Search, WalletCards } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import api from "../services/api";
import { downloadBlob, downloadCsv } from "../utils/files";
import { getErrorMessage } from "../utils/errors";
import { formatDate, formatDateTime, formatKES } from "../utils/format";
import StatusBadge from "./StatusBadge";

const tabs = [
  { id: "invoices", label: "Invoices" },
  { id: "payments", label: "Payments" },
  { id: "wallet", label: "Rent Credit" },
];

const resolveTab = (tab) => {
  if (tab === "payments" || tab === "wallet") return tab;
  if (tab === "refunds") return "wallet";
  return "invoices";
};

const downloadInvoiceRow = (row) => {
  downloadCsv(
    `krib-invoice-${String(row.id).replaceAll("/", "-")}.csv`,
    ["Reference", "Amount", "Due Date", "Status", "Statement"],
    [[row.reference, row.amount, formatDate(row.dueDate), row.status, row.statement]]
  );
};

export default function TenantFinance() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = useMemo(() => resolveTab(searchParams.get("tab")), [searchParams]);
  const [search, setSearch] = useState("");
  const [month, setMonth] = useState("");
  const [summary, setSummary] = useState(null);
  const [payments, setPayments] = useState([]);
  const [wallet, setWallet] = useState(null);
  const [withdrawAmount, setWithdrawAmount] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const [summaryRes, paymentsRes, walletRes] = await Promise.all([
          api.get("/api/dashboard/summary/"),
          api.get("/api/payments/"),
          api.get("/api/wallet/"),
        ]);
        setSummary(summaryRes.data);
        setPayments(paymentsRes.data || []);
        setWallet(walletRes.data || { recent: [], pending_withdrawals: [], wallet_available: 0, wallet_locked: 0 });
      } catch (err) {
        setError(getErrorMessage(err, "Failed to load financial records."));
        setSummary({ active_lease: null, rent: {} });
        setPayments([]);
        setWallet({ recent: [], pending_withdrawals: [], wallet_available: 0, wallet_locked: 0 });
      }
    };
    load();
  }, []);

  const setActiveTab = (tab) => {
    const next = new URLSearchParams(searchParams);
    if (tab === "invoices") next.delete("tab");
    else next.set("tab", tab);
    setSearchParams(next, { replace: true });
  };

  const downloadReceipt = async (paymentId) => {
    try {
      await downloadBlob(`/api/payments/receipt/${paymentId}/`, `krib-receipt-${paymentId}.pdf`);
    } catch (err) {
      setError(getErrorMessage(err, "Unable to download receipt."));
    }
  };

  const requestWithdrawal = async () => {
    setError("");
    setSuccess("");

    try {
      await api.post("/api/wallet/withdraw/", { amount: withdrawAmount });
      setWithdrawAmount("");
      setSuccess("Withdrawal request submitted.");

      const walletRes = await api.get("/api/wallet/");
      setWallet(walletRes.data || { recent: [], pending_withdrawals: [], wallet_available: 0, wallet_locked: 0 });
    } catch (err) {
      setError(getErrorMessage(err, "Unable to submit withdrawal request."));
    }
  };

  const invoices = useMemo(() => {
    const rows = payments.map((payment, index) => ({
      id: payment.id,
      reference: payment.period ? `${payment.period} rent` : `Invoice ${index + 1}`,
      amount: payment.amount,
      dueDate: payment.transaction_date || payment.created_at,
      status: payment.status,
      statement: payment.mpesa_receipt || payment.checkout_request_id || payment.id,
      period: payment.period || "",
    }));

    if (summary?.rent?.period && Number(summary?.rent?.balance || 0) > 0) {
      const carriedForward = Number(summary?.rent?.carried_forward_balance || 0) > 0;
      rows.unshift({
        id: `due-${summary.rent.period}`,
        reference: carriedForward ? `${summary.rent.period} outstanding balance` : `${summary.rent.period} rent`,
        amount: summary.rent.balance,
        dueDate: summary.active_lease?.start_date,
        status: summary.rent.status?.toLowerCase() || "pending",
        statement: carriedForward ? "Includes carried-forward arrears" : "Pending",
        period: summary.rent.period,
      });
    }

    return rows;
  }, [payments, summary]);

  const filteredRows = useMemo(() => {
    const source = activeTab === "invoices" ? invoices : payments;

    return source.filter((row) => {
      const text = JSON.stringify(row).toLowerCase();
      const matchesSearch = !search || text.includes(search.toLowerCase());
      const matchesMonth = !month || text.includes(month);
      return matchesSearch && matchesMonth;
    });
  }, [activeTab, invoices, month, payments, search]);

  const openWalletItems = useMemo(
    () => (wallet?.pending_withdrawals || []).filter((row) => row.status !== "paid" && row.status !== "completed"),
    [wallet?.pending_withdrawals]
  );

  const downloadStatement = () => {
    if (activeTab === "invoices") {
      downloadCsv(
        "krib-invoices.csv",
        ["Reference", "Amount", "Due Date", "Status", "Statement"],
        filteredRows.map((row) => [row.reference, row.amount, formatDate(row.dueDate), row.status, row.statement])
      );
      return;
    }

    downloadCsv(
      "krib-payments.csv",
      ["Receipt", "Amount", "Period", "Status", "Date"],
      filteredRows.map((row) => [row.mpesa_receipt || row.checkout_request_id || row.id, row.amount, row.period, row.status, formatDateTime(row.transaction_date || row.created_at)])
    );
  };

  if (!summary || !wallet) {
    return <p className="loading">Loading...</p>;
  }

  return (
    <div className="resident-page">
      {success ? <p className="success">{success}</p> : null}
      {error ? <p className="error">{error}</p> : null}

      <section className="resident-section-card">
        <div className="resident-tabbar">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`resident-tab ${activeTab === tab.id ? "active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab !== "wallet" ? (
          <div className="resident-toolbar">
            <label className="resident-search">
              <Search size={16} />
              <input value={search} onChange={(e) => setSearch(e.target.value)} aria-label={`Search ${activeTab}`} />
            </label>
            <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
            <button className="resident-primary-btn" type="button" onClick={downloadStatement}>
              <Download size={16} />
              <span>Download Statement</span>
            </button>
          </div>
        ) : null}

        {activeTab === "invoices" ? (
          <div className="resident-table-list">
            {filteredRows.length === 0 ? (
              <p className="subtitle">No invoices found.</p>
            ) : (
              filteredRows.map((row, index) => (
                <article className="resident-row-card" key={row.id}>
                  <div className="resident-row-id">{index + 1}</div>
                  <div className="resident-row-main">
                    <h4>{row.reference}</h4>
                    <p>{formatKES(row.amount)}</p>
                  </div>
                  <div className="resident-row-meta">
                    <span>{formatDate(row.dueDate)}</span>
                    <StatusBadge status={row.status} />
                    <button className="resident-link-btn" type="button" onClick={() => downloadInvoiceRow(row)}>Download</button>
                  </div>
                </article>
              ))
            )}
          </div>
        ) : null}

        {activeTab === "payments" ? (
          <div className="resident-table-list">
            {filteredRows.length === 0 ? (
              <p className="subtitle">No payments found.</p>
            ) : (
              filteredRows.map((row) => (
                <article className="resident-row-card" key={row.id}>
                  <div className="resident-row-id">
                    <WalletCards size={18} />
                  </div>
                  <div className="resident-row-main">
                    <h4>{row.mpesa_receipt || row.checkout_request_id || "Payment"}</h4>
                    <p>{formatKES(row.amount)} / {row.period || "Current cycle"}</p>
                  </div>
                  <div className="resident-row-meta">
                    <span>{formatDateTime(row.transaction_date || row.created_at)}</span>
                    <StatusBadge status={row.status} />
                    {row.status === "success" ? (
                      <button className="resident-link-btn" type="button" onClick={() => downloadReceipt(row.id)}>
                        Receipt
                      </button>
                    ) : null}
                  </div>
                </article>
              ))
            )}
          </div>
        ) : null}

        {activeTab === "wallet" ? (
          <div className="resident-table-list">
            <div className="resident-profile-columns">
              <div className="resident-profile-item">
                <span>Available Credit</span>
                <strong>{formatKES(wallet?.wallet_available || 0)}</strong>
              </div>
              <div className="resident-profile-item">
                <span>Locked Balance</span>
                <strong>{formatKES(wallet?.wallet_locked || 0)}</strong>
              </div>
              <div className="resident-profile-item">
                <span>Pending Withdrawals</span>
                <strong>{String(openWalletItems.length).padStart(2, "0")}</strong>
              </div>
            </div>

            <div className="resident-composer">
              <div className="resident-title-row">
                <WalletCards size={18} />
                <h3>Request Withdrawal</h3>
              </div>
              <div className="resident-form-grid">
                <input
                  type="number"
                  min="0"
                  value={withdrawAmount}
                  onChange={(e) => setWithdrawAmount(e.target.value)}
                  aria-label="Withdrawal amount"
                />
                <button className="resident-primary-btn" type="button" onClick={requestWithdrawal}>
                  Request Withdrawal
                </button>
              </div>
            </div>

            <div className="resident-table-list">
              <div className="resident-section-head">
                <div className="resident-title-row">
                  <WalletCards size={18} />
                  <h3>Pending Requests</h3>
                </div>
                <span className="resident-chip">{openWalletItems.length} open</span>
              </div>

              {openWalletItems.length === 0 ? (
                <p className="subtitle">No pending withdrawal requests.</p>
              ) : (
                openWalletItems.map((row) => (
                  <article className="resident-row-card" key={row.id}>
                    <div className="resident-row-id">
                      <WalletCards size={18} />
                    </div>
                    <div className="resident-row-main">
                      <h4>{formatKES(row.amount)}</h4>
                      <p>{row.reference_text || "Rent credit withdrawal request"}</p>
                    </div>
                    <div className="resident-row-meta">
                      <span>{formatDateTime(row.created_at)}</span>
                      <StatusBadge status={row.status} />
                    </div>
                  </article>
                ))
              )}
            </div>

            <div className="resident-table-list">
              <div className="resident-section-head">
                <div className="resident-title-row">
                  <WalletCards size={18} />
                  <h3>Recent Rent Credit Activity</h3>
                </div>
                <span className="resident-chip">{wallet?.recent?.length || 0} entries</span>
              </div>

              {wallet?.recent?.length === 0 ? (
                <p className="subtitle">No rent credit transactions yet.</p>
              ) : (
                wallet.recent.map((row) => (
                  <article className="resident-row-card" key={row.id}>
                    <div className="resident-row-id">
                      <WalletCards size={18} />
                    </div>
                    <div className="resident-row-main">
                      <h4>{row.kind.replaceAll("_", " ")}</h4>
                      <p>{formatKES(row.amount)}</p>
                    </div>
                    <div className="resident-row-meta">
                      <span>{formatDateTime(row.created_at)}</span>
                      <StatusBadge status={row.status} />
                    </div>
                  </article>
                ))
              )}
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
