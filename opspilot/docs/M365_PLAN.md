# Microsoft 365 Integration Plan (implemented in v0.3)

Goal: per-client read-only visibility into M365 — users, licenses, MFA/security
status — using **least-privilege** Microsoft Graph scopes. No write access in the
initial integration.

## Connection model
One **Entra app registration** owned by BVTech, using the **admin-consent /
multi-tenant** pattern. Each client admin grants consent once; OpsPilot stores a
per-tenant refresh token (encrypted at rest) keyed to that client's `client_id`.

## App registration (BVTech tenant)
1. Entra admin center → App registrations → New registration.
2. Name: `BVTech OpsPilot`. Supported accounts: *multitenant*.
3. Redirect URI (web): `https://opspilot.bvtech.org/api/m365/callback`.
4. Certificates & secrets → new client secret → store in OpsPilot secrets (encrypted).
5. API permissions → add the **least-privilege** scopes below → grant admin consent.

## Least-privilege Graph scopes (read-only)
| Scope | Why |
|-------|-----|
| `User.Read.All` | List tenant users |
| `Directory.Read.All` | License assignments, group/role membership |
| `Organization.Read.All` | Tenant + subscribed SKU (license) info |
| `Reports.Read.All` | Usage / activity reports |
| `SecurityEvents.Read.All` | Secure Score, security alerts (where licensed) |
| `IdentityRiskyUser.Read.All` | Risky sign-ins (requires Entra ID P2) |

Do **not** request `*.ReadWrite.*`, `Mail.*`, or `Files.*` for this read-only
visibility feature. Add narrower write scopes only when a specific Phase-4
automation justifies it, with its own consent and audit entry.

## What OpsPilot pulls (per client, on a schedule)
- Users (display name, UPN, account enabled)
- Assigned licenses vs. available SKUs → feeds the License module
- Per-user MFA registration state (via authentication methods / reports)
- Secure Score (current + max) where the tenant is licensed for it
- Risky sign-ins (P2 only) — surfaced as dashboard alerts

## Token storage & safety
- Refresh tokens encrypted at rest (envelope encryption; see SECURITY.md ☐).
- Each token scoped to exactly one client; never shared across tenants.
- Every Graph pull writes an audit entry (`m365.sync`, client_id, counts).
- A client admin can revoke consent in their own tenant at any time; OpsPilot
  detects the revocation and marks the connection inactive.

## Build steps (v0.3)
1. `services/m365.py`: OAuth code exchange + refresh + Graph GET helpers.
2. `api/routes/m365.py`: connect (staff initiates), callback, sync, status.
3. Encrypt token column; add `m365_connections` table (client_id, tenant_id,
   enc_refresh_token, scopes, status, last_sync).
4. License module: map Graph `subscribedSkus` → `licenses` rows automatically.
5. Dashboard: "M365 tenant status" card (users, license usage, secure score).
