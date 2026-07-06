# BVTech OpsPilot — Security Checklist

This is a living checklist. Items marked ✅ are implemented in v0.1; ☐ are
planned for later phases (tracked in ROADMAP.md).

## Authentication & sessions
- ✅ Argon2id password hashing (memory-hard, auto-rehash on login)
- ✅ JWT access tokens, short TTL (30 min default)
- ✅ DB-backed refresh sessions → revocable (logout-everywhere)
- ✅ TOTP MFA (RFC 6238), setup + confirm flow
- ✅ Login rate limiting (5/min/IP in v0.1; move to Redis for multi-worker)
- ✅ Generic auth errors (never reveal which factor failed)
- ☐ Account lockout after N failures / breached-password check
- ☐ Email-verified password reset flow

## Authorization
- ✅ 4-role RBAC (OWNER / TECH / CLIENT_ADMIN / CLIENT_VIEWER)
- ✅ Per-client tenant isolation enforced at query layer
- ✅ Staff-only guards on client creation, license writes, audit, enroll-token
- ☐ Per-device and per-client policy controls (Phase 3)

## Endpoint agent (Phase 1 posture)
- ✅ No remote command execution endpoint exists at all
- ✅ Signed, time-limited, client-scoped enrollment tokens
- ✅ Per-device agent key; only its hash is stored
- ✅ Telemetry limited to health data; explicit consent language in installer
- ☐ Signed installer / code-signing cert
- ☐ Approval workflow + full audit before ANY remote action (Phase 2)

## Transport & headers
- ✅ HSTS (prod), X-Frame-Options DENY, nosniff, strict CSP, referrer policy
- ✅ Secure + HttpOnly + SameSite cookies (Secure enforced in prod)
- ✅ Cloudflare in front; Tunnel option = zero exposed ports
- ☐ Cloudflare WAF managed rules + rate-limiting rules enabled

## Secrets & data
- ✅ All secrets via environment; `.env` git-ignored; no hardcoded keys
- ✅ Separate signing keys for user sessions vs agent enrollment
- ✅ Non-root container user
- ☑ Encrypt stored 3rd-party API tokens at rest (secure vault, Fernet — shipped v0.45) (envelope encryption) — Phase 3
- ☐ Secrets manager (Doppler / Infisical / Vault) instead of flat .env

## Auditing
- ✅ Append-only audit log of sensitive actions (login, create, enroll, etc.)
- ✅ Captures actor, role, target, client, IP, success/failure
- ☐ Ship audit log to immutable external sink (R2 object-lock / SIEM)
- ☐ Admin confirmation step on destructive actions

## Operations
- ☐ Nightly DB backups (commands in DEPLOYMENT.md — set the cron)
- ☐ Quarterly restore test
- ☐ Off-box backup copy (R2 / B2)
- ✅ SSH hardening + UFW instructions (DEPLOYMENT.md)
- ☐ Fail2ban for SSH

## Pre-go-live gate (do all of these before real client data lands)
1. Rotate the bootstrap owner password and enable MFA on it.
2. Confirm `COOKIE_SECURE=true`, `ENV=production`.
3. Confirm `.env` is `chmod 600` and not in git (`git status` clean).
4. Run a backup, then a restore, on a throwaway DB.
5. Enable Cloudflare WAF + rate limiting on opspilot.bvtech.org.
6. Verify unauthenticated `/api/clients` returns 401 (smoke test does this).
