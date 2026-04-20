# KRIB Rental Management Platform
## Improved User Manual

Version: 2.0  
Last updated: 2026-04-02  
Basis: Original user manual PDF plus the current frontend and backend implementation in this repository.

## 1. Purpose

KRIB is a web-based rental management platform for landlords, managers, and tenants. It helps property teams manage occupancy, leases, payments, maintenance issues, documents, notifications, and portfolio follow-up from one system.

This improved manual reflects the system as it is currently implemented in the codebase. Compared with the older manual, it now includes the manager role, invite-based onboarding, document capture during lease creation, notification workflows, wallet activity, and current deployment-ready behaviour.

## 2. Who Should Use This Manual

| Role | Main use of KRIB | How access is created |
| --- | --- | --- |
| Landlord | Create properties, add units, invite users, create leases, review revenue, manage documents and notifications | Self-signup |
| Manager | Operate only within assigned properties, create leases, invite tenants, manage maintenance, send scoped notifications | Invite from landlord |
| Tenant | View current booking, pay rent, see invoices and receipts, raise maintenance tickets, access shared documents | Invite from landlord or manager |

## 3. Minimum Requirements

- A smartphone, tablet, laptop, or desktop computer
- A modern web browser such as Chrome, Edge, or Firefox
- A stable internet connection
- A valid KRIB account or an active invite link
- For rent payment, a phone number that can complete an M-Pesa STK push

## 4. How Accounts Are Created

### 4.1 Landlord Account

Landlords create their own account from the landlord signup screen. The form requires:

- Business name
- First name
- Last name
- Email address
- Phone number
- Password and password confirmation

After signup, the landlord signs in from the main login page.

### 4.2 Manager Account

Managers do not self-register. A landlord sends a manager invite. The manager opens the invite link, enters first name, last name, password, and password confirmation, then signs in after acceptance.

### 4.3 Tenant Account

Tenants do not self-register. A landlord or manager sends a tenant invite. The tenant opens the invite link, enters first name, last name, password, and password confirmation, then signs in after acceptance.

## 5. Sign In and Password Reset

### 5.1 Signing In

1. Open the KRIB login page.
2. Enter your username or email and password.
3. Select `Sign In`.
4. KRIB redirects you to the correct dashboard based on your role.

### 5.2 Resetting a Forgotten Password

1. On the login page, select `Forgot Password`.
2. Enter the email address attached to your account.
3. Open the reset link sent to your email.
4. Enter and confirm a new password.
5. Return to the login page and sign in.

## 6. Main Areas of the System

| Area | What it does | Typical users |
| --- | --- | --- |
| Dashboard | Shows role-based summary information and next actions | All users |
| Properties | Create and manage properties and units | Landlords |
| Invites | Send manager or tenant onboarding links | Landlords, Managers |
| Leases | Create active leases and generate onboarding records | Landlords, Managers |
| Finance / Payments | Review dues, successful payments, statements, wallet activity | Tenants, Landlords |
| Maintenance | Raise or manage maintenance tickets | Tenants, Landlords, Managers |
| Documents | Access lease agreements, receipts, ID records, and shared documents | All users, based on scope |
| Notifications | Review notices or send updates by in-app, email, or SMS | All users; compose for landlords and managers |
| Profile | Update account and contact details | All users |

## 7. Landlord Guide

### 7.1 Create a Property

1. Sign in as a landlord.
2. Open `Properties`.
3. In `Create Property`, enter the property name, location, and optional description.
4. Select `Create Property`.

### 7.2 Add a Unit

1. Stay in the `Properties` area.
2. Open `Add Unit`.
3. Select the property.
4. Enter the unit number, unit type, monthly rent, and deposit.
5. Select `Create Unit`.

### 7.3 Assign or Remove a Manager

1. In `My Property`, find the property card.
2. Choose a manager from the `Assign manager` list.
3. Select `Assign`.
4. To remove a manager, select `Unassign`.

Important note: Managers only work inside properties assigned to them. If a manager is removed from all properties, KRIB deactivates that manager account until another property is assigned.

### 7.4 Invite a Manager

1. Open `Invite Manager` or `Invites`.
2. Enter the manager contact details.
3. Send the invite.
4. Share the generated invite link if needed.

### 7.5 Invite a Tenant

1. Open `Invites`.
2. Choose the tenant invite flow.
3. Enter the tenant name and at least one contact method.
4. Select the property and unit where applicable.
5. Send the invite.

### 7.6 Create a Lease

1. Open `Leases`.
2. Select an available unit.
3. Select the tenant.
4. Enter the start date, optional end date, and due day.
5. Capture the tenant ID or passport image.
6. Capture the tenant signature.
7. Select `Create Lease`.

What KRIB does after lease creation:

- Marks the unit as occupied
- Stores the tenant identity document
- Generates the signed lease document
- Makes the lease available in the document center

### 7.7 Review Revenue, Receipts, and Follow-up

Landlords can use the finance areas to:

- Monitor successful rent collections
- View follow-up items for unpaid or partial rent
- Review landlord revenue information
- Access payment receipts
- Request landlord payouts where enabled

### 7.8 Manage Maintenance Tickets

1. Open the dashboard or maintenance list.
2. Review open tickets.
3. Update each ticket status to `Open`, `In Progress`, or `Resolved`.
4. KRIB notifies the tenant when status changes.

### 7.9 Send Notifications

Landlords can send notices to scoped users by:

- In-app notification
- Email
- SMS

Typical use cases include rent reminders, outage notices, and general portfolio communication.

### 7.10 Use the Document Center

The document center allows landlords to:

- Preview lease agreements
- Download receipts and shared files
- View stored identity documents for relevant active leases
- Remove a tenant by ending the active lease when operationally required

## 8. Manager Guide

### 8.1 Accept the Invite

1. Open the manager invite link.
2. Enter first name, last name, password, and password confirmation.
3. Select `Accept invite`.
4. Sign in using the account created for you.

### 8.2 What a Manager Can Do

Managers can:

- View only the properties assigned to them
- Invite tenants
- Create leases for scoped properties
- Review and update maintenance tickets
- Send notifications to users in their scope
- Access documents for managed properties

Managers cannot:

- Reassign the manager of a property
- Operate on properties outside their scope
- Access landlord-wide data outside assigned properties

## 9. Tenant Guide

### 9.1 Accept the Invite

1. Open the tenant invite link.
2. Enter first name, last name, password, and password confirmation.
3. Select `Accept invite`.
4. Sign in from the login page.

### 9.2 View the Tenant Dashboard

After sign-in, the tenant dashboard shows current booking and summary information such as:

- Active lease details
- Current rent balance
- Recent financial activity
- Maintenance overview
- Notice and document shortcuts

### 9.3 Pay Rent

The current self-service payment flow is M-Pesa first.

1. Open `Pay Rent`.
2. Confirm that an active lease exists.
3. Review the amount due.
4. Enter or confirm the M-Pesa phone number.
5. Select `Pay now`.
6. Complete the STK push on your phone.
7. Wait for KRIB to confirm the payment.
8. Download the receipt once the payment status changes to successful.

Important notes:

- KRIB rejects payments above the remaining balance.
- Partial payment is supported.
- If the payment remains pending, finish the M-Pesa prompt on your phone and refresh after a short wait.

### 9.4 Review Invoices, Payments, and Wallet Activity

Open `Financials` to:

- View current invoices and outstanding balances
- Search past payments
- Download a payment statement
- Download receipts for successful payments
- View wallet balances and recent wallet activity
- Request a wallet withdrawal where available

### 9.5 Raise a Maintenance Ticket

1. Open `Maintenance`.
2. Select `Raise a Ticket`.
3. Enter a clear description of the issue.
4. Choose the urgency level.
5. Attach a photo if available.
6. Submit the ticket.

The maintenance option is only available when the tenant has an active lease.

### 9.6 Access Shared Documents

Open `Documents` to:

- View the current lease agreement
- View or preview uploaded shared documents
- Download receipts
- Access property-specific documents such as house rules when provided

Access is limited to documents that belong to the tenant's own lease or property scope.

### 9.7 Review Notifications and Update Profile

Tenants can:

- Read notices from landlords or managers
- Mark notices as read
- Dismiss notices
- Update profile and contact details

## 10. Troubleshooting

| Problem | Likely meaning | What to do |
| --- | --- | --- |
| `Invalid login details` | Wrong username, email, or password | Re-enter credentials or use password reset |
| `No active lease found` | A payment or maintenance action was attempted before lease activation | Contact the landlord or manager |
| Invite expired or cancelled | The onboarding link is no longer valid | Ask for a fresh invite |
| Payment still pending | The M-Pesa callback has not been confirmed yet | Complete the STK prompt and refresh after a short wait |
| Access denied to document or property data | The user is outside the permitted scope | Sign in with the correct role or contact support |
| Maintenance option unavailable | Tenant has no active lease | Wait until lease activation is completed |

## 11. Frequently Asked Questions

### 11.1 Can tenants create accounts directly?

No. Tenants currently join KRIB through an invite from a landlord or manager.

### 11.2 Can managers work across all properties?

No. Managers only work inside properties explicitly assigned to them.

### 11.3 What happens when a lease is created?

KRIB stores the lease, marks the unit occupied, saves the tenant identity document, captures the signature, and generates a lease document.

### 11.4 What payment method is available in the current tenant flow?

The current tenant self-service screen is built around M-Pesa STK push.

### 11.5 Can tenants see other tenants' documents?

No. Document access is scoped to the correct tenant, lease, property, and role.

### 11.6 Can a landlord remove a tenant from a unit?

Yes. Removing a tenant ends the active lease, marks the unit vacant, and keeps the historical account and payment records in KRIB.

## 12. Good Practice Checklist

- Keep your password private.
- Confirm property, unit, and tenant details before creating a lease.
- Capture a clear ID or passport image before lease activation.
- Ask tenants to complete the signature step before final lease creation.
- Use notifications for rent reminders and maintenance updates.
- Download or preview key documents after major actions such as lease creation or payment confirmation.

## 13. Summary

KRIB supports the full rental workflow from property setup to tenant onboarding, rent collection, maintenance management, and document sharing. Landlords control the portfolio, managers operate within assigned properties, and tenants use guided self-service tools for payments, maintenance, and records access.
