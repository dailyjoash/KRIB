# Custody Settlement & Cutover Runbook (Phase 2A)

Operational guide for draining the legacy KRIB-custody float for a landlord and
safely switching them to `direct_paybill`. Custody cutover is **admin-driven**:
a human settles the balance, confirms receipt off-platform, then flips the mode.
There is no self-service landlord switch.

All `/api/staff/...` endpoints require a **staff** account. All settlement and
cutover actions write a `CustodyAuditLog` row (visible in Django admin).

---

## 0. Concepts

- **`LandlordBalance`** — custody money KRIB holds for a landlord:
  `available_balance` (withdrawable now) + `locked_balance` (held until the
  per-credit hold expires, then auto-unlocked by the `unlock_balances` cron).
- **`LandlordPayout`** — a transfer to the landlord via IntaSend. Non-final
  states (`REQUESTED`, `PROCESSING`, `PENDING`) mean money is in flight.
- **Cutover safety rail** — the system refuses to set
  `collection_mode = direct_paybill` while a landlord has `available_balance > 0`,
  `locked_balance > 0`, or any non-final payout. Enforced on the API, the
  settings serializer, and the Django admin form (returns HTTP 409 on the API).

---

## 1. When to settle a landlord

Settle before cutover whenever `custody_inspect` shows the landlord has a
non-zero balance or an in-flight payout. A landlord already at zero on every
axis needs no settlement — go straight to cutover (§5).

---

## 2. Inspect the float (read-only)

```bash
cd backend
python manage.py custody_inspect
```

Shows aggregate available/locked totals, every landlord with a non-zero
balance, successful-but-unallocated payments, in-flight payouts, and the tenant
wallet float. Safe to run anytime.

Per-landlord detail via API:

```
GET /api/staff/custody/landlords/            # overview of everyone outstanding
GET /api/staff/custody/landlords/<id>/       # balance + ledger + in-flight payouts
```

**If `custody_inspect` reports successful-but-unallocated PaymentTransactions**,
those payments never credited a balance. Run the allocation reconciler first so
the balance is correct before you settle:

```bash
python manage.py reconcile_payment_allocations
```

---

## 3. Unlock held funds (if `locked_balance > 0`)

Locked credits auto-unlock once their hold expires. To unlock everything due now:

```bash
python manage.py unlock_balances
```

Funds still locked (hold not yet expired) cannot be paid out yet — wait for the
hold, or settle only the available portion now and the rest later.

---

## 4. Trigger the settlement payout

The landlord must have a saved payout target (`payout_method` +
`payout_destination`, plus `payout_bank_code` for bank). The settlement pays
that saved target — reusing the same IntaSend rail as a normal payout.

```
POST /api/staff/custody/landlords/<id>/settle/
{
  "amount": "5000.00",     // optional; defaults to full available_balance
  "note": "Phase 2A cutover settlement"
}
```

- Reserves the amount, creates a `LandlordPayout`, submits to IntaSend, writes a
  `CustodyAuditLog` (`settlement_payout`).
- Response `202` = submitted, now `PROCESSING` (await settlement).
- Response `502` = provider rejected; funds were released back to the balance.

Repeat per landlord until `available_balance` reaches 0.

---

## 5. Confirm receipt off-platform, then finalize the payout

IntaSend M-Pesa/bank transfers settle asynchronously. **Verify the money
actually landed** (IntaSend dashboard, bank/M-Pesa statement, or landlord
confirmation) before finalizing:

- Settled OK → mark the payout paid:
  ```
  POST /api/landlord/payouts/<payout_id>/mark-paid/
  ```
  (Only `PROCESSING` payouts that carry a provider reference can be marked paid.)

- Did **not** settle → reverse it (releases the reservation back to the balance):
  ```
  POST /api/landlord/payouts/<payout_id>/reverse/
  ```

The reconciler can also poll provider status for in-flight payouts:

```bash
python manage.py reconcile_payouts
```

---

## 6. Flip `collection_mode` to direct_paybill (the cutover)

Only after the balance is 0/0 and no payout is in flight:

```
POST /api/staff/custody/landlords/<id>/cutover/
{ "note": "settled & confirmed 2026-05-29" }
```

- `200` → switched; writes a `CustodyAuditLog` (`cutover_to_direct_paybill`).
- `409` → still outstanding; the body states the outstanding amount. Go back to
  §2. A blocked attempt is also recorded (`cutover_blocked`).

The landlord now collects via their own Paybill (record-only); the legacy
custody flow is untouched for everyone still on it.

---

## 7. Tenant wallet policy (decision: defer / legacy-redeemable)

Tenant wallet credits (legacy overpayments) belong to tenants and are **never
deleted or hidden** by a landlord cutover. Policy: *tenant wallet credits remain
redeemable against future legacy custody rent. A tenant whose landlord switches
to direct_paybill keeps their wallet balance visible but can only apply it on the
legacy custody flow.* `custody_inspect` reports the tenant wallet float so it
stays visible. (No tenant-refund tooling is built in Phase 2A; revisit if a real
case needs cash refunds.)

---

## 8. If something goes wrong

| Symptom | Action |
|---|---|
| Cutover returns 409 but you expected zero | Re-run `custody_inspect`; check for `locked_balance` (run `unlock_balances`) or an in-flight payout (finalize/reverse it, §5). |
| `custody_inspect` shows unallocated successful payments | Run `reconcile_payment_allocations`, then re-inspect. |
| Settlement payout stuck `PROCESSING` | Verify settlement off-platform; `reconcile_payouts`, then mark-paid (settled) or reverse (not settled). |
| Settlement returned 502 (rejected) | Funds already released back to balance; fix the payout destination and retry §4. |
| Need to undo a cutover | Switching back to `custody_legacy` is always allowed (no rail) via the landlord settings update / admin form. |
| Audit trail | `CustodyAuditLog` in Django admin: every settlement, cutover, and blocked attempt with actor, landlord, amounts, timestamp. |

**Never** edit `LandlordBalance` rows or `collection_mode` directly in the DB to
work around the rail — that is exactly the stranded-funds risk this phase closes.
