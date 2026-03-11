# KRIB MVP (Django + DRF + React/Vite)

Production-focused rental workflow for landlords, managers, and tenants.

## MVP scope
- **Landlord**: create properties/units/leases, invite tenants/managers, view revenue/followups/receipts, request payouts.
- **Manager**: operate only within assigned properties.
- **Tenant**: accept invite, view lease/rent status, initiate rent payment, submit maintenance requests.

## Critical path (happy flow)
1. Login with role-aware redirect.
2. Landlord creates property and unit.
3. Landlord/manager creates active lease for tenant.
4. Tenant initiates STK payment (transaction starts `pending`).
5. Daraja callback marks payment `success` or `failed`.
6. Tenant files maintenance request; manager/landlord updates lifecycle.

## Safety defaults chosen for ambiguous cases
- Existing usernames are **not** reused on invite acceptance (tenant/manager) to prevent accidental account takeover.
- STK initiation is rejected with `503` when Daraja env is incomplete; no new pending payment is created in that case.
- Duplicate callbacks are treated as idempotent no-ops once payment leaves `pending`.

## Local setup
### Backend
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd backend
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Environment variables
Use `.env.example` as baseline.

### Django/runtime
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG` (`1` in local dev)
- `DJANGO_ALLOWED_HOSTS` (comma-separated; e.g. `api.krib.app,localhost,127.0.0.1`)
- `DJANGO_CORS_ALLOWED_ORIGINS` (comma-separated)
- `DJANGO_CSRF_TRUSTED_ORIGINS` (comma-separated)

### Frontend
- `VITE_API_URL` (e.g. `http://127.0.0.1:8000`)

### Daraja (required for payment initiation)
- `MPESA_CONSUMER_KEY`
- `MPESA_CONSUMER_SECRET`
- `MPESA_SHORTCODE`
- `MPESA_PASSKEY`
- `MPESA_CALLBACK_URL` (public URL to `/api/payments/stk/callback/`)
- Optional overrides:
  - `MPESA_OAUTH_URL`
  - `MPESA_STK_PUSH_URL`

## Test commands
From repo root:
```bash
# backend unit/integration tests
python backend/manage.py test

# frontend production build smoke check
npm --prefix frontend run build
```

Pass criteria:
- Django tests: all tests pass (`OK`, no failures/errors).
- Frontend build: exits `0` and outputs built assets in `frontend/dist`.

## Production checklist
- [ ] `DJANGO_DEBUG=0`.
- [ ] `DJANGO_ALLOWED_HOSTS` explicitly set.
- [ ] `DJANGO_CORS_ALLOWED_ORIGINS`/`DJANGO_CSRF_TRUSTED_ORIGINS` explicitly set.
- [ ] JWT lifetimes reviewed for security posture.
- [ ] Daraja callback URL publicly reachable over HTTPS.
- [ ] App logging aggregated (include payment callback transitions).
- [ ] Admin-only payout mark-paid endpoints protected at infra layer.

## Payment rollback / callback failure playbook
If STK initiation occurred but callback did not arrive:
1. Keep transaction in `pending`; do **not** manually mark `success`.
2. Reconcile using `checkout_request_id` with Daraja transaction status query (out-of-band ops step).
3. If provider confirms failure/timeout, mark transaction `failed` with audit note.
4. If callback eventually arrives, idempotency logic prevents double allocation.

## Manual smoke checklist
- [ ] Landlord creates property/unit/lease/invite.
- [ ] Manager only sees assigned-property data.
- [ ] Tenant initiates payment and callback updates status safely.
- [ ] Duplicate callback does not re-allocate money.
- [ ] Tenant creates maintenance request; manager/landlord can see/update in scope.
