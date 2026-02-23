
# KRIB - Digital Rental Management (MVP)

This repository contains a minimal, working skeleton to bring the **KRIB** project to life:
- **Backend**: Django + Django REST Framework (simple JWT auth), app `core`
- **Frontend**: React (Vite/ESM style) with basic pages (Login, Dashboard)

This is a starter MVP intended for development and iteration. Payment integrations (M-Pesa, PayPal, cards) are stubbed and should be implemented with real credentials and secure server-side endpoints.

## What's included
- `backend/` - Django project `krib_backend` and app `core` (models, serializers, views, urls)
- `frontend/` - React app skeleton (src components, API service)
- `requirements.txt` - Python dependencies for backend
- `README.md` - this file

## Quick setup (backend)
```bash
# create venv
python -m venv venv
source venv/bin/activate    # mac/linux
venv\Scripts\activate     # windows

pip install -r requirements.txt
cd backend
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Quick setup (frontend)
```bash
cd frontend
# if using npm
npm install
npm run dev
```

## Notes
- Database defaults to SQLite for quick dev. Change to Postgres in settings for production.
- Add real payment provider credentials and webhook handling before going live.
- This skeleton focuses on core entities: Property, Tenant, Lease, Payment, MaintenanceRequest, basic JWT auth.

If you want, I can expand any part (full M-Pesa integration, admin UI, deployment scripts, or tests). Enjoy — let's build this into a real app. 🚀


## Added features (role-based & uploads)
- `Profile` model with `role` (landlord | tenant). A Profile is auto-created when a User is created.
- `/api/auth/me/` endpoint returns current user and profile (used by frontend to control UI).
- Lease model supports `agreement` file uploads (stored in `media/agreements/`).
- CORS enabled for frontend dev.
- Frontend includes AuthContext, ProtectedRoute, role-based NavBar, forms for Properties, Leases (with file upload), and Maintenance reports.

## Dev notes
- After migrations, create users and set `profile.role` to `landlord` or `tenant` in Django admin or via shell.
- Media files served in DEBUG mode at `/media/`.

## Manual test checklist (tenant invites)
1. Landlord/manager logs in and opens **Invite Tenant** page.
2. Create an invite with email or phone (optional property).
3. Copy the invite link displayed after submission.
4. Open the invite link in a new browser session, verify status is **PENDING**.
5. If OTP is enabled, verify OTP then set password and accept invite.
6. Log in with the invited tenant account and confirm Tenant Dashboard loads.
7. Landlord creates a lease for the tenant and confirm lease details appear for the tenant.
