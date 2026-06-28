# BVTech OpsPilot â€” Roadmap

Self-hosted MSP client portal. FastAPI + Jinja2 (server-rendered), Postgres,
Redis, exposed via Cloudflare Tunnel. This roadmap tracks what has shipped and
what is planned, grouped by version milestone.

Version source of truth: `opspilot/app/core/config.py` (`APP_VERSION`).
Releases are numbered `0.1`, `0.2`, `0.3`, ...

---

## Shipped

### v0.1 â€” Base portal
- FastAPI backend, server-rendered Jinja2 templates (login / dashboard / portal).
- Session auth with secure cookies; bootstrap admin from env on first run.
- Postgres + Redis via docker compose; Alembic migrations (head
  `cdef051e7149`, self-contained schema).
- Health endpoint `GET /api/health` -> `{"ok":true,...}`.

### v0.2 â€” Tickets + agent check-ins
- Ticket creation, listing, and status tracking in the client portal.
- Agent enrollment + periodic check-ins (shared `AGENT_ENROLL_SECRET`).
- Dashboard surfaces ticket and agent state.

---

## In progress (now)

### Security hardening
- Rotate the root password that was exposed in chat earlier.
- Disable root SSH login and password auth; key-only `deploy` user remains.
- Keep inbound firewall to SSH (22) only â€” public traffic flows through the
  Cloudflare Tunnel, so 80/443 stay closed.
- Audit `.env` permissions (chmod 600) and secret handling.

### CI/CD
- GitHub Actions on push/merge to `main`: SSH to `deploy@45.33.29.100`,
  `git pull --ff-only`, `alembic upgrade head`, `docker compose up -d --build api`,
  then `docker image prune -f`.
- Server-only `docker-compose.override.yml` (cloudflared) persists across pulls.
- Repo secrets: `LINODE_HOST`, `LINODE_USER`, `LINODE_SSH_KEY`, `LINODE_APP_DIR`.

---

## Near-term plans

### v0.3 â€” Account security
- **MFA / TOTP** for portal and admin logins, with recovery codes.
- Session management: device list, forced logout, idle/absolute expiry.
- Per-client role separation (admin vs. client-user scoping).

### v0.4 â€” Operations & visibility
- **Audit log UI**: searchable view of auth events, ticket changes, and admin
  actions (backed by a persisted audit table).
- **RMM agent expansion**: richer host metrics, software inventory, alerting
  thresholds, and remote command queueing.
- **Backups**: scheduled Postgres dumps with offsite retention and a
  documented restore runbook.

### v0.5 â€” Billing & integrations
- **Client billing**: contracts/plans, usage-based line items, invoice
  generation and export.
- **Email / M365 integration**: ticket-to-email threading, inbound mail parsing,
  and Microsoft 365 tenant linking for client onboarding.
- Notification routing (email/webhook) for tickets and agent alerts.

---

## Backlog / unscheduled
- Client-facing knowledge base / docs.
- Webhook + public API surface for third-party automation.
- Multi-tenant org isolation hardening.
- Metrics/observability dashboard (Prometheus-style export).
