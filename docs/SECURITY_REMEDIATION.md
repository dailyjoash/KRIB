# Security Remediation — change log and operator checklist

This document is the operator-facing companion to the security hardening
patches. It lists what changed, why it matters, what to test, and what you
must rotate manually before going live.

## What changed (file-by-file)

| File | Change |
| --- | --- |
| `frontend/nginx.conf` | `/media/` is no longer served directly by nginx. Requests proxy to Django, which re-runs object-level permission checks. CSP / X-Frame-Options / Referrer-Policy / X-Content-Type-Options headers added. |
| `backend/krib_backend/urls.py` | New `/media/<path>` route hits `MediaProxyView`. `/api/token/` now goes through `ThrottledTokenObtainPairView`. |
| `backend/krib_backend/settings.py` | Startup-time validation: `DJANGO_SECRET_KEY` ≥ 32 chars and `INTASEND_WEBHOOK_SECRET` ≥ 32 chars when `DJANGO_DEBUG=0`. `SECURE_SSL_REDIRECT` defaults to True in prod. Cookies marked HttpOnly+SameSite=Lax. `token_blacklist` app added. SimpleJWT rotates refresh tokens and blacklists the previous one. `CALLBACK_PATH_SECRET` is no longer interpolated into the M-Pesa callback URL (it was misleading; only the HMAC actually protected the webhook). `.env` is only allowed to override shell vars in DEBUG. |
| `backend/core/views.py` | New `MediaProxyView` serving uploads as `Content-Disposition: attachment`. `DocumentDownloadView` and `PaymentReceiptView` updated to send as attachment too. `LandlordPayoutRequestView` now requires the submitted destination to match the saved `LandlordSettings`. Payout audit columns populated. `LandlordPayoutMarkPaidView` records the auditor user/timestamp and refuses double-marks. Stripe webhook fails closed when `STRIPE_WEBHOOK_SECRET` is unset. `DocumentListView` no longer leaks co-tenants' lease/other documents. `_user_can_access_document` no longer grants tenants property-wide lease access. `register` no longer reveals whether an email is already registered. `DocumentUploadView` allow-list permission check (pre-existing bug). `MeSerializer` invoked with request context. New `ThrottledTokenObtainPairView` and `LogoutView` (refresh-token blacklist). |
| `backend/core/serializers.py` | `ScopedPrimaryKeyRelatedField` + scope helpers. `PropertySerializer.manager_id`, `UnitSerializer.property_id`, `LeaseSerializer.unit_id`, `DocumentSerializer.{property,lease,tenant}` all scoped to the requester. New centralized `_validate_signup_password` enforces min-12 + Django's `validate_password`. `RegisterSerializer.validate_email` no longer leaks existence. `MeSerializer.validate_email` rejects duplicates against other accounts. `validate_uploaded_file` now blocks HTML/SVG/script even when renamed to `.pdf` / `.jpg` / `.png`. |
| `backend/core/models.py` | `LandlordPayout` gained `requested_by`, `marked_paid_by`, `marked_paid_at` audit columns. |
| `backend/core/migrations/0011_payout_audit_fields.py` | Migration for the new audit columns. |
| `backend/core/throttles.py` | New `TokenObtainRateThrottle` (binds the `/api/token/` throttle to per-user identity). |
| `backend/core/urls.py` | Added `path("auth/logout/", LogoutView.as_view(), ...)`. |
| `backend/core/services.py` | IntaSend payouts now request `requires_approval="YES"`. Provider dashboard becomes a second human-in-the-loop check. |
| `backend/core/management/commands/seed_krib.py` | Refuses to seed when `DJANGO_DEBUG=0` unless `KRIB_ALLOW_PROD_SEED=1` is explicitly set. Default password bumped to satisfy the new min-12 rule. |
| `backend/entrypoint.sh` | Refuses to seed when `DJANGO_DEBUG=0`. |
| `backend/Dockerfile` | Installs `libmagic1` so `python-magic` can sniff uploads. |
| `backend/requirements.txt` | Repaired (was corrupted by a UTF-16 paste at the bottom); explicitly pins `python-magic==0.4.27`. |
| `backend/krib_backend/settings_test.py` | Throttles set to unreachably-high rates so security tests are deterministic. |
| `backend/core/tests/test_security_hardening.py` | 26 new tests covering every hardening change. |
| `backend/core/tests/test_mvp_hardening.py` | Two old payout tests now seed `LandlordSettings` so they exercise the new destination guard. Two old scope tests now accept either 400 (serializer rejection) or 403 (view rejection); both are valid security responses. |
| `frontend/src/context/AuthContext.jsx` | `logout()` calls `POST /api/auth/logout/` so the refresh token is blacklisted server-side. |
| `.github/workflows/release-check.yml` | Installs `libmagic1` on the CI runner. Sets the new `INTASEND_WEBHOOK_SECRET` env var for the deploy check. Adds advisory-mode `pip-audit` and `npm audit`. |

## Test commands

```powershell
# Backend
Push-Location backend
& .\.venv\Scripts\python.exe manage.py test --settings=krib_backend.settings_test
& .\.venv\Scripts\python.exe manage.py check --deploy   # run with prod env vars + .env temporarily renamed
Pop-Location

# Frontend
Push-Location frontend
npm run build
npm audit --audit-level=high   # advisory
Pop-Location
```

## Secrets you MUST rotate manually

The previous `.env` contained working credentials. None of the secrets below
are loaded from this repo, so the code change alone does not rotate them.

1. **`EMAIL_HOST_PASSWORD`** — the Gmail App Password for `kipchumbajoashkurgat@gmail.com`. Revoke at https://myaccount.google.com/security and issue a new app password.
2. **`INTASEND_API_TOKEN`, `INTASEND_PUBLISHABLE_KEY`** — rotate from the IntaSend dashboard.
3. **`INTASEND_WEBHOOK_SECRET`** — generate a fresh value:
   ```
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
   The new settings refuse to boot in production if the secret is shorter than 32 characters.
4. **`MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET`, `MPESA_PASSKEY`** — rotate from the Daraja portal.
5. **`PAYPAL_CLIENT_ID`, `PAYPAL_SECRET`** — rotate from the PayPal developer dashboard.
6. **`AFRICASTALKING_API_KEY`** — rotate from the Africa's Talking dashboard.
7. **`DJANGO_SECRET_KEY`** — generate a new 50+ char value:
   ```
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```
8. **Database passwords** — any committed default like `krib_password` / `root` must be replaced before the system holds real tenant data.

## Known remaining risks (work intentionally not done in this pass)

- **Email change is not verified.** We block collision with other users' emails but do not send a confirmation link to the new address. Marked TODO in `MeSerializer.validate_email`. Add a verification token flow before considering this fully closed.
- **OTP/email confirmation on payouts is not yet wired.** The destination whitelist is the new gate; payouts to the saved destination still go through immediately. Add a per-request OTP for amounts above a threshold as a follow-up.
- **JWTs still live in `localStorage`.** The blacklist makes a logout effective server-side, but XSS still exfiltrates tokens. Migrating to `httpOnly` cookies is a larger frontend change tracked separately.
- **The committed `backend/fixtures/sqlite_migration.json`** contains hashed superuser passwords for real-looking emails. Anonymize or `git filter-repo` it out of history.
- **PII redaction in logs** is not implemented; payment-provider response bodies still log raw.

## Production deploy checklist (must-have before launch)

- [ ] All secrets above rotated and stored only in the deploy platform's secrets store.
- [ ] `DJANGO_DEBUG=0` set on the deploy host (verify with `python manage.py check --deploy`).
- [ ] `DJANGO_SECRET_KEY` ≥ 50 random chars (the boot guard requires 32+).
- [ ] `INTASEND_WEBHOOK_SECRET` ≥ 32 chars (the boot guard enforces this).
- [ ] `DJANGO_ALLOWED_HOSTS`, `DJANGO_CORS_ALLOWED_ORIGINS`, `DJANGO_CSRF_TRUSTED_ORIGINS` explicitly set.
- [ ] `KRIB_LOAD_DEMO_DATA=0` (the new gate refuses to seed in prod anyway).
- [ ] `STRIPE_WEBHOOK_SECRET` set if Stripe is enabled — the endpoint now refuses to process unsigned events.
- [ ] LandlordSettings configured for every landlord that has any wallet balance, otherwise no payouts can succeed.
- [ ] Nginx config redeployed (the legacy `/media/` alias is removed).
- [ ] Run a quick sanity test as an unauthenticated client: `curl https://your-host/media/some-known-doc.pdf` → expect 401, not 200.
