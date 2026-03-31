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
pip install -r backend/requirements.txt
cd backend
python manage.py migrate
python manage.py seed_krib
python manage.py runserver 0.0.0.0:8000
```

If `DATABASE_URL` is left blank locally, KRIB falls back to SQLite using [db.sqlite3](/C:/Users/hstre/Downloads/KRIB_project_enhanced/backend/db.sqlite3). For hosted deployment, use PostgreSQL.

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
- `DJANGO_GUNICORN_WORKERS`
- `DJANGO_GUNICORN_TIMEOUT`
- `DJANGO_COLLECTSTATIC`
- `SCHEDULER_INTERVAL_SECONDS`
- `KRIB_LOAD_DEMO_DATA` (`0` for production)
- SMTP email settings:
  - `DEFAULT_FROM_EMAIL`
  - `EMAIL_BACKEND`
  - `EMAIL_HOST`
  - `EMAIL_PORT`
  - `EMAIL_HOST_USER`
  - `EMAIL_HOST_PASSWORD`
  - `EMAIL_USE_TLS`
  - `EMAIL_USE_SSL`

### Frontend
- `VITE_API_URL` (e.g. `http://127.0.0.1:8000`)
- `VITE_PAYPAL_CLIENT_ID`
- `VITE_PAYPAL_CURRENCY`

For same-domain production deploys behind the included Nginx config, leave `VITE_API_URL` blank so the app uses relative `/api/...` requests.

### Daraja (required for payment initiation)
- `MPESA_CONSUMER_KEY`
- `MPESA_CONSUMER_SECRET`
- `MPESA_SHORTCODE`
- `MPESA_PASSKEY`
- `MPESA_CALLBACK_URL` (public URL to `/api/payments/stk/callback/`)
- Optional overrides:
  - `MPESA_OAUTH_URL`
  - `MPESA_STK_PUSH_URL`

### PayPal
- `PAYPAL_CLIENT_ID`
- `PAYPAL_SECRET`
- `PAYPAL_MODE`
- `PAYPAL_API_BASE`
- `PAYPAL_CURRENCY`

### Stripe
- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_CURRENCY`

### Africa's Talking
- `AFRICASTALKING_USERNAME`
- `AFRICASTALKING_API_KEY`
- `AFRICASTALKING_SENDER_ID`
- `AFRICASTALKING_SMS_URL`

### Business metadata
- `PUBLIC_BASE_URL`
- `FRONTEND_URL`
- `BACKEND_URL`
- `BUSINESS_NAME`
- `SUPPORT_PHONE`
- `SUPPORT_EMAIL`
- `BUSINESS_ADDRESS`

## Test commands
From the `backend` directory:
```bash
# backend unit/integration tests
python manage.py test

# seed demo data
python manage.py seed_krib
```

Pass criteria:
- Django tests: all tests pass (`OK`, no failures/errors).

## Production checklist
- [ ] `DJANGO_DEBUG=0`.
- [ ] `DJANGO_ALLOWED_HOSTS` explicitly set.
- [ ] `DJANGO_CORS_ALLOWED_ORIGINS`/`DJANGO_CSRF_TRUSTED_ORIGINS` explicitly set.
- [ ] Strong `DJANGO_SECRET_KEY` configured.
- [ ] JWT lifetimes reviewed for security posture.
- [ ] Daraja callback URL publicly reachable over HTTPS.
- [ ] SMTP/email backend configured for password reset + invite emails.
- [ ] Scheduler/worker process running for arrears checks.
- [ ] Persistent media storage configured (named volume or object storage).
- [ ] App logging aggregated (include payment callback transitions).
- [ ] Admin-only payout mark-paid endpoints protected at infra layer.
- [ ] Stripe and PayPal keys added for live sandbox testing.
- [ ] Africa's Talking credentials added if SMS delivery is required.

## Docker Compose (Dev)
From repo root:
```bash
docker compose up --build
```

This starts:
- PostgreSQL on `localhost:5432`
- Django backend on `http://localhost:8000`
- Vite frontend on `http://localhost:5173`

This file intentionally stays in dev mode: Django `runserver`, Vite dev server, and demo seeding.

## Docker Compose (Prod-like)
From repo root:
```bash
docker compose --env-file .env -f docker-compose.prod.yml up --build -d
```

This starts:
- PostgreSQL
- Django via `gunicorn`
- A lightweight scheduler process via `python manage.py run_periodic_tasks`
- Nginx serving the built frontend on port `80`

Notes:
- `docker-compose.prod.yml` does **not** seed demo data unless `KRIB_LOAD_DEMO_DATA=1`.
- Static files are collected at container boot and served with WhiteNoise inside Django.
- Uploaded files persist in the `media_data` Docker volume and are served by the frontend Nginx container at `/media/...`. For hosted environments, S3-compatible object storage is still recommended.
- `/api`, `/admin`, and `/static` are proxied from Nginx to the backend service, so the frontend and backend can share one origin.

## Fast Release Check
Windows PowerShell:
```powershell
./scripts/release_check.ps1
```

POSIX shell:
```bash
./scripts/release_check.sh
```

This runs:
- backend tests
- Django production deploy checks
- static asset collection
- frontend production build
- Docker Compose prod config validation when Docker is available

## Hosting Before Tuesday
Fastest reliable path:
1. Host the Django API on Render, Railway, or DigitalOcean App Platform.
2. Host the React frontend on Netlify, Vercel, or Cloudflare Pages.
3. Point `VITE_API_URL` at the live API domain if frontend and backend are split across domains.

Backend deploy essentials:
```bash
pip install -r backend/requirements.txt
cd backend
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn krib_backend.wsgi:application
```

Worker/scheduler essentials:
```bash
python manage.py run_periodic_tasks
```

Backend env essentials:
- `DJANGO_DEBUG=0`
- `DJANGO_SECRET_KEY=<strong-secret>`
- `DJANGO_ALLOWED_HOSTS=<your-api-domain>`
- `DJANGO_CORS_ALLOWED_ORIGINS=<your-frontend-domain>`
- `DJANGO_CSRF_TRUSTED_ORIGINS=<your-frontend-domain>`
- `DATABASE_URL=<managed-postgres-url>` if using Postgres
- `DEFAULT_FROM_EMAIL` plus SMTP env if email flows are required
- Daraja variables if live M-Pesa is required

Smoke-check endpoints after deploy:
- `GET /api/health/`
- `POST /api/token/`
- `GET /api/dashboard/summary/` with a valid JWT

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
