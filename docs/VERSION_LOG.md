# Version Log â€” BVTech OpsPilot

Changelog for versioned releases. The source of truth for the running version is
`APP_VERSION` in `opspilot/app/core/config.py`. Every release gets:

1. an `APP_VERSION` bump in `opspilot/app/core/config.py`,
2. a dated entry in this file, and
3. a git tag on the merge commit.

Versions follow a simple `MAJOR.MINOR.PATCH` scheme (currently in the `0.x`
pre-1.0 line: `0.1`, `0.2`, `0.3`, ...).

---

## Release ritual

Do this on the branch/PR that you merge to `main`:

1. **Bump the version** in `opspilot/app/core/config.py`:

   ```python
   APP_VERSION = "0.3.0"   # was 0.2.0
   ```

2. **Add a dated entry** to the table and a section below (copy the
   [template](#entry-template)). Use today's date in `YYYY-MM-DD` format and
   note any migration / ops steps.

3. **Merge to `main`.** CI/CD deploys automatically
   (`deploy@45.33.29.100` â†’ `git pull --ff-only` â†’ `alembic upgrade head` â†’
   `docker compose up -d --build api`).

4. **Tag the merge commit** once it is on `main`:

   ```powershell
   git checkout main
   git pull --ff-only
   git tag -a v0.3.0 -m "OpsPilot v0.3.0"
   git push origin v0.3.0
   ```

   Keep the tag name (`v0.3.0`) identical to `APP_VERSION` with a `v` prefix.

> If a release adds or changes a DB migration, call it out explicitly in the
> entry. Production does **not** auto-create tables â€” migrations run via
> `docker compose run --rm api alembic upgrade head` (handled by CI/CD).

---

## Releases

| Version | Date       | Summary                                                       | Migration |
| ------- | ---------- | ------------------------------------------------------------- | --------- |
| 0.2.0   | 2026-06-27 | Tickets, device check-in history, tenant isolation.          | Yes       |
| 0.1.0   | 2026-06-27 | Initial release: auth + server-rendered portal, agent enroll.| Yes (base)|

---

### v0.2.0 â€” 2026-06-27

**Summary:** Multi-tenant feature release.

**Added**
- Tickets: clients can open/track support tickets from the portal.
- Device check-in history: agents report in and the dashboard shows a
  per-device check-in timeline.
- Tenant isolation: data is scoped per tenant so clients only ever see their
  own tickets and devices.

**Changed**
- Dashboard and portal templates updated to surface tickets and device status.

**Migration**
- Schema changes are included in the alembic head (`cdef051e7149`).
- Applied automatically on deploy via
  `docker compose run --rm api alembic upgrade head`.

**Ops notes**
- No new environment variables.

---

### v0.1.0 â€” 2026-06-27

**Summary:** First deployable release.

**Added**
- FastAPI backend, server-rendered with Jinja2 (login / dashboard / portal).
- Session auth with bootstrap admin (`BOOTSTRAP_ADMIN_EMAIL` /
  `BOOTSTRAP_ADMIN_PASSWORD`).
- Agent enrollment using `AGENT_ENROLL_SECRET`.
- Health endpoint: `GET /api/health` â†’ `{"ok": true, ...}`.
- Docker Compose stack: `db` (postgres:16-alpine), `redis` (redis:7-alpine),
  `api` (uvicorn :8000). Public access via Cloudflare Tunnel.

**Migration**
- Self-contained base schema at alembic head (`cdef051e7149`,
  `down_revision = None`).
- Production does not auto-create tables; run
  `docker compose run --rm api alembic upgrade head`.

**Ops notes**
- Env read from `opspilot/.env`. Required: `ENV`, `SECRET_KEY`,
  `AGENT_ENROLL_SECRET`, `DATABASE_URL`, `REDIS_URL`, `COOKIE_SECURE`,
  `BOOTSTRAP_ADMIN_EMAIL/PASSWORD`, `POSTGRES_USER/PASSWORD/DB`, `TUNNEL_TOKEN`.

---

## Entry template

Copy this block for each new release. Replace the placeholders, keep the table
row in sync, and remove sections that do not apply.

```markdown
### vX.Y.Z â€” YYYY-MM-DD

**Summary:** one-line description of the release.

**Added**
- ...

**Changed**
- ...

**Fixed**
- ...

**Migration**
- New alembic revision: <revision id> (or "None").
- Applied on deploy via `docker compose run --rm api alembic upgrade head`.

**Ops notes**
- New/changed env vars, manual steps, or "None".
```

And the matching table row:

```markdown
| X.Y.Z   | YYYY-MM-DD | <summary> | Yes/No |
```
