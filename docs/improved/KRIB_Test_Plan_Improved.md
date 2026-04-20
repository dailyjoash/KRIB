# KRIB Rental Management Platform
## Improved Test Plan

Version: 2.0  
Last updated: 2026-04-02  
Basis: Original test plan PDF plus the current repository implementation and automated regression coverage.

## 1. Purpose

This document defines how KRIB should be tested before release. It covers functional, integration, security, operational, and user-facing checks for the current product implementation.

The improved plan is grounded in the actual codebase, including:

- Django REST API with JWT authentication
- React and Vite frontend
- PostgreSQL data storage
- M-Pesa STK integration
- Optional PayPal and Stripe backend payment endpoints
- Email and SMS notification paths
- Document generation and download flows
- Wallet and landlord payout workflows

## 2. Quality Objectives

KRIB should:

- Enforce strict role-based access for landlords, managers, and tenants
- Preserve correct financial behaviour for rent, arrears, and receipts
- Prevent duplicate payment allocation on repeated callbacks
- Protect documents and data by portfolio, lease, and tenant scope
- Support clean onboarding through landlord signup and invite acceptance
- Allow tenants to complete essential self-service tasks without admin intervention
- Remain deployable in both local and hosted environments

## 3. System Under Test

| Layer | Technology | Scope |
| --- | --- | --- |
| Frontend | React 18, React Router, Vite 5 | User journeys, routing, role-specific screens |
| Backend | Django 6, DRF, SimpleJWT | Business rules, permissions, integrations, receipts, notifications |
| Database | PostgreSQL or local SQLite fallback | Persistence, migrations, relational integrity |
| Payments | M-Pesa Daraja, PayPal, Stripe | Transaction initiation, callback handling, status updates |
| Messaging | SMTP email, Africa's Talking SMS | Password reset, invites, notices |
| Deployment | Render backend, Vercel-compatible frontend, Docker Compose | Build, runtime health, environment correctness |

## 4. Test Scope

### 4.1 In Scope

- Landlord signup and login
- Manager and tenant invite creation, acceptance, resend, cancellation, and expiry
- Property and unit management
- Lease creation, identity capture, signature capture, and lease document generation
- Tenant payment initiation and payment callback processing
- Arrears calculation and carry-forward logic
- Receipt generation and receipt access control
- Maintenance ticket creation, filtering, and role-based updates
- Notification creation, delivery routing, read state, and cleanup
- Document upload, listing, preview, download, and access control
- Password reset and contact/profile flows
- Wallet balances, withdrawal requests, landlord payouts
- Build, test, and production-readiness scripts

### 4.2 Out of Scope

- Internal reliability of third-party provider infrastructure
- Native mobile app testing because KRIB is a web application
- Large-scale performance benchmarking beyond practical project limits
- Full payment settlement verification against production finance systems

## 5. Risk-Based Priorities

| Priority | Area | Why it matters |
| --- | --- | --- |
| P0 | Authentication, role scoping, lease activation, payment correctness | Direct security and money impact |
| P1 | Maintenance, notifications, document access, password reset | Strong user and support impact |
| P2 | Reporting, exports, layout polish, non-critical messaging copy | Lower operational risk |

## 6. Test Strategy

### 6.1 Automated Backend Regression

The repository already contains a backend regression suite in `backend/core/tests/test_mvp_hardening.py`. At the time of this update, the suite contains 42 named tests covering:

- Role and permission scoping
- Invite acceptance and lifecycle rules
- Lease onboarding document requirements
- M-Pesa payment idempotency and amount validation
- Arrears and rent status calculations
- Maintenance access rules
- Document access control
- Notification fan-out and cleanup
- Password reset
- Public health endpoint behaviour

Primary command:

```powershell
cd backend
python manage.py test
```

### 6.2 Frontend and End-to-End Smoke Testing

Manual smoke testing should confirm that the frontend can complete the main user journeys:

- Landlord creates property, unit, and lease
- Manager can act only within assigned scope
- Tenant can pay rent and submit maintenance
- Notifications and documents are visible to the correct user

### 6.3 Integration Testing

Integration checks should verify the handoff between:

- Frontend form submission and backend API response
- Lease creation and generated documents
- Payment initiation and callback handling
- Notification composition and delivery channels
- Password reset request and reset confirmation flow

### 6.4 Security and Authorization Testing

Testing must confirm that:

- Tenants cannot access other tenants' identity documents
- Managers cannot operate outside assigned properties
- Unscoped document and payment receipt access is blocked
- Inactive manager accounts cannot sign in until re-assigned

### 6.5 Operational Readiness Testing

Use the included release checks before deployment:

```powershell
./scripts/release_check.ps1
```

Expected outcomes:

- Backend tests pass
- Django deployment checks pass
- Static files collect successfully
- Frontend production build succeeds
- Docker Compose production configuration validates when Docker is available

## 7. Test Environments

| Environment | Purpose | Notes |
| --- | --- | --- |
| Local developer setup | Fast feedback during implementation | Frontend on Vite, backend on localhost |
| Docker Compose | Production-like validation | Shared services, static files, scheduler, Nginx proxy |
| Hosted preview or production | Final release validation | Render backend and Vercel-compatible frontend configuration |

## 8. Entry and Exit Criteria

### 8.1 Entry Criteria

- Database migrations applied
- Required environment variables set for the scenario under test
- Seed or fixture data available where needed
- Payment and messaging sandbox credentials configured if relevant

### 8.2 Exit Criteria

- All P0 test cases pass
- No unresolved critical or high-severity defects remain
- Payment callbacks behave idempotently
- Access control passes for documents, properties, and maintenance
- Frontend production build succeeds
- `/api/health/` responds successfully in the target environment

## 9. Test Data Requirements

Prepare at minimum:

- 1 landlord account
- 2 manager accounts
- 3 tenant accounts
- 2 properties
- 4 units with mixed vacancy and occupancy
- Active and inactive leases
- Open and resolved maintenance tickets
- Successful, pending, and failed payment records
- Read and unread notifications
- Lease, identity, receipt, and other document samples

## 10. Core Test Matrix

| ID | Scenario | Expected result | Method |
| --- | --- | --- | --- |
| TP-01 | Landlord signup | Account created and able to sign in | Manual plus API |
| TP-02 | Manager invite acceptance | Manager account created and scoped login works | Automated plus manual |
| TP-03 | Tenant invite acceptance | Tenant account created and login works | Automated plus manual |
| TP-04 | Expired or cancelled invite | Invite blocked with clear message | Automated plus manual |
| TP-05 | Property and unit creation | Records save correctly and appear in setup pages | Manual plus API |
| TP-06 | Lease creation without ID or signature | Request rejected with validation error | Automated |
| TP-07 | Lease creation with ID and signature | Lease saved and lease document generated | Automated plus manual |
| TP-08 | M-Pesa initiation with valid amount | Payment enters pending and can be reconciled | Automated plus sandbox |
| TP-09 | Duplicate successful callback | No double allocation occurs | Automated |
| TP-10 | Payment above remaining balance | Request rejected | Automated |
| TP-11 | Arrears carry-forward logic | Old balance is reflected correctly in summary | Automated |
| TP-12 | Tenant maintenance for other lease | Access denied | Automated |
| TP-13 | Manager maintenance scope | Manager sees only assigned property tickets | Automated plus manual |
| TP-14 | Tenant document access | Tenant sees only own scoped records | Automated plus manual |
| TP-15 | Notification send by landlord or manager | Correct audience receives in-app, email, or SMS notices | Automated plus manual |
| TP-16 | Password reset | Reset email flow completes and new password works | Automated plus manual |
| TP-17 | Wallet withdrawal request | Request is created and balances refresh correctly | Manual plus API |
| TP-18 | Production build and health check | Build succeeds and health endpoint responds | Operational |

## 11. Defect Severity Model

| Severity | Meaning | Example |
| --- | --- | --- |
| Critical | Release blocker with security, data loss, or payment risk | Duplicate payment allocation |
| High | Major workflow blocked for a core role | Tenant cannot pay or landlord cannot create lease |
| Medium | Important but not release-blocking | Notification email not sent while in-app still works |
| Low | Cosmetic or minor usability issue | Layout spacing problem with no functional impact |

## 12. Deliverables

- Updated test plan
- Executed test log
- Defect register
- Screenshot evidence for major user journeys
- Release check output summary
- Final test summary report

## 13. Roles and Responsibilities

| Role | Responsibility |
| --- | --- |
| Developer | Execute automated tests, fix defects, run release checks |
| Tester or reviewer | Perform manual smoke and acceptance testing |
| Supervisor or approver | Review results and decide release readiness |

## 14. Suggested Execution Order

1. Run backend automated tests.
2. Run frontend production build.
3. Perform landlord workflow smoke test.
4. Perform manager workflow smoke test.
5. Perform tenant workflow smoke test.
6. Validate payment sandbox paths.
7. Validate notifications and documents.
8. Run deployment health and release checks.

## 15. Key Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Daraja sandbox instability | Payment tests may fail for external reasons | Keep mocked automated tests and separate sandbox evidence |
| Missing environment variables | Payment or notification features appear broken | Use `.env.example` and deployment checklists |
| Scope regressions after feature changes | Users may see or modify unauthorized data | Keep permission tests mandatory in release gate |
| Callback duplication | Double allocation or incorrect balances | Preserve idempotency tests as P0 coverage |
| Late deployment-only bugs | Release failure after local success | Validate with Docker Compose or hosted preview before go-live |

## 16. Summary

KRIB should be released only after automated backend tests, manual role-based smoke tests, payment validation, and production-readiness checks all pass. The current repository already provides strong regression coverage, and this plan turns that coverage into a clearer release gate for real deployments.
