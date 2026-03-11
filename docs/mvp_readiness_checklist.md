# KRIB MVP Readiness Checklist

## Phase 1 baseline mapping

| Area | Current status | Gap before hardening | Action taken |
|---|---|---|---|
| Auth + role isolation | JWT auth and role model present. | Create paths for units/leases not fully scoped by assigned property. | Added scoped create checks in `UnitViewSet` and `LeaseViewSet`. |
| Property/unit/lease invariants | Single active lease per unit exists in model clean method. | API create path allowed unauthorized cross-scope creation. | Added permission checks + tests. |
| Invite acceptance | Invite flow present. | Existing username could be reused and password overwritten. | Reject existing usernames on tenant/manager invite accept. |
| Payment initiate/callback | STK initiate + callback implemented. | Missing env could create dead pending payments; callbacks not fully idempotent/logged. | Added env sanity gate, callback transition logging, duplicate callback ignore logic. |
| Maintenance visibility | Queryset scope mostly role-aware. | Needed automated coverage for tenant-only create and manager visibility. | Added integration tests for scope and lifecycle visibility. |
| Frontend route reliability | Protected routes exist. | Missing wildcard fallback and missing role guard can create confusing redirects. | Added fallback route and role guard; API URL now env-driven with timeout. |
| Security/ops config | CORS open globally in settings. | Not safe-by-default outside dev. | Tied CORS allow-all to DEBUG and added explicit CORS/CSRF env lists. |

## Critical-path flow validation targets
- [x] Login -> role redirect
- [x] Landlord creates property/unit/lease/invite
- [x] Tenant payment initiation requires Daraja env
- [x] Callback success/failure with duplicate callback idempotency
- [x] Tenant maintenance create + manager visibility scope

## Remaining risks
- Frontend automated tests are not configured; only build/smoke checks are possible in current setup.
- Production JWT key length warning indicates secret policy must enforce >= 32-byte key.
