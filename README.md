# KRIB Rental Workflow

Startup-grade rental management workflow for landlords, managers, and tenants.

## Stack
- Backend: Django + DRF + JWT
- Frontend: React (Vite)
- Payments: Daraja STK Push integration (sandbox/production via env)

## Core implemented workflows
- Role-aware scope:
  - Landlord: full visibility of own portfolio (and global payment listing per requirement).
  - Manager: only assigned properties.
  - Tenant: self-only access.
- Property (building level) + Unit (rentable level).
- Lease with:
  - rent snapshot from unit,
  - due day fixed to 15 (stored),
  - single active lease per unit,
  - unit occupancy sync when lease activates/deactivates.
- Tenant invites:
  - create invite,
  - public token lookup,
  - optional OTP verification,
  - invite accept to activate/create tenant user + tenant profile.
- Payments:
  - tenant STK initiate endpoint,
  - public Daraja callback endpoint,
  - transaction persistence and status updates.
- Rent status (computed without cron):
  - PAID / PARTIAL / UNPAID / OVERDUE,
  - one-time overdue notification per lease+period,
  - status updates dynamically when payments arrive.
- Maintenance:
  - tenant can create only with active lease,
  - landlord/manager can view/update in scope,
  - notifications on create and status change.
- Dashboards:
  - Landlord/Manager: paid/partial/unpaid/overdue lists + totals.
  - Tenant: active lease, rent status, overdue banner, STK pay flow, payment history, maintenance.

## Setup
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd backend
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

## Daraja configuration
Set in environment (or `.env` if loaded externally):
- `DARAJA_ENV=sandbox|production`
- `DARAJA_CONSUMER_KEY`
- `DARAJA_CONSUMER_SECRET`
- `DARAJA_SHORTCODE`
- `DARAJA_PASSKEY`
- `DARAJA_CALLBACK_URL`

### ngrok callback testing
1. Start backend: `python manage.py runserver 0.0.0.0:8000`
2. Start ngrok: `ngrok http 8000`
3. Copy HTTPS forwarding URL.
4. Set callback env to:
   - `DARAJA_CALLBACK_URL=https://<ngrok-id>.ngrok-free.app/api/payments/stk/callback/`
5. Restart backend and initiate STK.

## Manual test checklist
- [ ] Login as landlord/manager/tenant and verify scoped data access.
- [ ] Create property + units.
- [ ] Create active lease and confirm unit becomes OCCUPIED.
- [ ] Deactivate lease and confirm unit becomes VACANT.
- [ ] Create tenant invite and confirm link/OTP returned and logged.
- [ ] Accept invite and confirm tenant user role/profile.
- [ ] Initiate STK payment and confirm pending transaction is created.
- [ ] Simulate callback and confirm SUCCESS/FAILED updates.
- [ ] Check landlord/manager dashboard grouping + totals.
- [ ] Check tenant dashboard overdue banner after 15th when balance > 0.
- [ ] Clear balance and verify status returns to PAID.
- [ ] Create/update maintenance and verify notifications.
