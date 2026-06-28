# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This is **BVTech OpsPilot** — a secure, self-hosted MSP/MSSP command center (RMM + PSA +
defensive security) for BVTech LLC. The operator drives changes from a phone; assume every
command may be copy-pasted into **Windows PowerShell**.

---

## 0. Golden rules (read first)

1. **GitHub is the single source of truth.** Nothing is "done" until it is merged to `main`.
2. **NEVER deploy directly.** Do not SSH to the server to change the app, do not run
   `docker compose ... up` on the host by hand, do not edit files on the Linode. The ONLY
   path to production is: **open a PR → merge to `main` → GitHub Actions deploys.**
3. **Never commit secrets.** No `.env`, tokens, passwords, or keys — not in code, docs, or
   examples. Use placeholders like `<SECRET_KEY>`. If a secret leaks into chat/a file, treat
   it as compromised and tell the operator to rotate it.
4. **Repo layout matters.** The app lives in `opspilot/`. Control-center files (`CLAUDE.md`,
   `README.md`, `docs/*`, `.github/workflows/*`, `ops/*`) live at the **repo root**, NOT inside
   `opspilot/`.
5. The app is **server-rendered** (FastAPI + Jinja2). There is **no separate static frontend**
   and **no Cloudflare Pages**. Public access is via **Cloudflare Tunnel**, not Caddy.

---

## 1. Repository layout

```
/ (repo root)         control center: CLAUDE.md, README.md, docs/, .github/workflows/, ops/
opspilot/             the application (everything below is relative to here)
  app/
    main.py           FastAPI entrypoint: middleware, router wiring, startup bootstrap
    core/             config.py · db.py · deps.py (auth/RBAC) · security.py (JWT/Argon2/TOTP)
    models/__init__.py  ALL SQLAlchemy models live in this one file (versioned by section)
    api/routes/       one router file per domain (auth, resources, tickets, alerts, ...)
    services/         business logic: audit, monitoring, sla, automation, security, m365, email, crypto
    templates/        Jinja2 pages (login, dashboard, portal, signup, invoice)
    static/           css/img (no build step)
  migrations/         Alembic; versions/ named <hash>_v0_N_<feature>.py
  agent/              opspilot_agent.py — Windows telemetry agent (Phase-1: read-only)
  scripts/smoke_test.py  end-to-end test against an in-process app
  docker-compose.yml  db (postgres:16) + redis + api (uvicorn :8000) + caddy (unused)
```

---

## 2. Common commands

All commands run from **`opspilot/`** unless noted.

### Local development
```powershell
cd opspilot
python -m venv .venv ; .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # then edit: ENV=development, DATABASE_URL=sqlite:///./pulse_dev.db,
                          # COOKIE_SECURE=false, SECRET_KEY/AGENT_ENROLL_SECRET=long random,
                          # BOOTSTRAP_ADMIN_PASSWORD=ChooseOne123!
uvicorn app.main:app --reload --port 8000
```
Open http://localhost:8000 and log in as the bootstrap owner. In **development** tables
auto-create on startup; in **production** they do not — you run Alembic instead.

### Tests
```powershell
python scripts/smoke_test.py    # full enroll→checkin→alert→ticket→billing flow, in-process
```
There is no pytest suite — `smoke_test.py` is the test. It boots the app via
`fastapi.testclient.TestClient` against the configured DB (sqlite dev `.env` is fine) and
asserts the cross-cutting flows. Run it after any change touching auth, models, or routes.

### Migrations (Alembic)
```powershell
alembic revision -m "v0_N short description"   # create a migration after changing models
alembic upgrade head                            # apply (CI runs this on deploy)
alembic current ; alembic history               # inspect
```
**Current head: `b8c9d0e1f2a3` (v0.10 invoicing).** The chain is linear, one migration per
release (`cdef051e7149` → `a1b2c3d4e5f6` → `b2c3d4e5f6a7` → `c3d4e5f6a7b8` → `d4e5f6a7b8c9`
→ `e5f6a7b8c9d0` → `f6a7b8c9d0e1` → `a7b8c9d0e1f2` → `b8c9d0e1f2a3`). Any model change needs
a matching migration so `alembic upgrade head` stays correct in production.

### Docker (mirrors production; rarely needed locally)
```powershell
docker compose run --rm api alembic upgrade head   # migrate, then:
docker compose up -d --build api
```

---

## 3. Architecture

**Multi-tenant by `client_id`.** Almost every business row carries a `client_id`. BVTech
staff (`OWNER`, `TECH` — see `STAFF_ROLES`) see across all clients; client users
(`CLIENT_ADMIN`, `CLIENT_VIEWER`) are constrained to their own `client_id`. There is **no
ORM-level row filter** — tenant scoping is enforced explicitly in every route via the
`app.core.deps` helpers. Forgetting it is a data-leak bug.

**Request lifecycle / conventions** (copy an existing route in `app/api/routes/` rather than
inventing a new shape):
- Each router declares `router = APIRouter(prefix="/api", tags=[...])` and is wired in
  `app/main.py` (`app.include_router(...)`). UI/page routes live in `ui.py`.
- DB access: `db: Session = Depends(get_db)` (one session per request, from `core/db.py`).
- Identity: `user: User = Depends(current_user)` resolves the `access_token` cookie or
  `Authorization: Bearer` header → session check → `User`.
- Authorization: `Depends(require_roles(Role.OWNER, Role.TECH))` for staff-only writes;
  inside handlers call `is_staff(user)` to branch list queries, and
  `assert_client_access(user, client_id)` before touching a specific client's row.
- Auditing: funnel every sensitive mutation through `services.audit.record(db, action=..., ...)`.
  `AuditLog` is append-only — never UPDATE/DELETE it. Client IP comes from the
  `cf-connecting-ip` header (Cloudflare Tunnel) with a `request.client.host` fallback.
- Request/response bodies are Pydantic `BaseModel` classes defined inline in the route file;
  handlers return plain dicts/lists (no global response models).

**Auth & security** (`core/security.py`): Argon2id password hashing, JWT access/refresh
tokens, DB-backed `AuthSession` rows so sessions are *revocable* (logout-everywhere),
TOTP MFA. Agents enroll/check in with a separate signing secret (`AGENT_ENROLL_SECRET`),
not user JWTs.

**Services layer** (`app/services/`) holds engine logic kept out of the routes:
- `monitoring.py` — threshold sweep → opens at most one non-resolved `Alert` per
  `(device, kind)`; auto-resolves when the condition clears. Thresholds resolve per-client
  `AlertPolicy` → global → built-in defaults.
- `sla.py` — stamps response/resolution due times on tickets from `SLAPolicy`; tracks breach.
- `automation.py` — event→action rules (`alert.opened`, `ticket.created`,
  `ticket.sla_breached`). Actions are **safe, in-platform only** (create_ticket, ack_alert,
  notify, assign, set_priority, add_note) — never remote code execution.
- `security.py` — assessments/findings/scorecard; high/critical findings raise an alert.
- `m365.py` + `crypto.py` — read-only app-only Graph sync; cached tokens encrypted at rest.
- `email.py` — SMTP; a safe no-op that just logs when `SMTP_HOST` is unset.

**Models** are all in `app/models/__init__.py`, organized in `# v0.N` sections matching the
release that introduced them. Convention: SQLAlchemy 2.0 typed `Mapped[...]` /
`mapped_column`, `client_id` FK on tenant rows, timezone-aware `_utcnow` defaults, and string
enums (`Role`, `*Status`, `*Severity`) plus module-level constant tuples for valid values.

**Script-deployment safety model** (v0.7, see the big comment in `models/__init__.py`): a
`Script` is inert until an OWNER enables it; deploying snapshots the exact content+version,
requires consent + reason, and needs OWNER approval where **approver ≠ requester**
(separation of duties); the agent *pulls* only its own approved jobs. Preserve these
invariants — they are the line between an RMM and a remote-shell backdoor.

---

## 4. Versioning & PR workflow

Every change is a branch + PR; no direct pushes to `main`. Branch names: `feat/...`,
`fix/...`, `docs/...`, `chore/...`. Do not merge your own PR without the operator's go-ahead.

**Every release-worthy (app-touching) PR MUST include:**
- A version bump in `opspilot/app/core/config.py` (`APP_VERSION`, currently `0.10.0`).
- A new entry at the top of `opspilot/CHANGELOG.md`.
- If models changed: a matching Alembic migration (keep `alembic upgrade head` valid).

Pure docs/ops PRs may skip the version bump — say so in the PR description.

---

## 5. Deploy pipeline (reference only — Claude does NOT run this)

On merge to `main`, GitHub Actions (`.github/workflows/`) SSHes to `deploy@<LINODE_HOST>` and
runs, in `/opt/bvtech-portal`:
```
git pull --ff-only
cd opspilot
docker compose run --rm api alembic upgrade head
docker compose up -d --build api
docker image prune -f
```
Public access is via **Cloudflare Tunnel** (`cloudflared`, configured by a server-only,
uncommitted `docker-compose.override.yml`) to `portal.bvtech.org`. **Zero open inbound ports
except SSH (22).** Do not add 80/443 rules or Caddy/Nginx exposure. Health check:
`GET /api/health` → `{"ok": true, ...}`.

---

## 6. PowerShell & remote-shell safety

The operator is on Windows PowerShell, often pasting from a phone:
- Chain with `;` (no `&&`/`||`); no ternary / `??` / `?.`. Backtick is the escape char.
- Quote paths with spaces; use forward-slash repo-relative paths in docs.
- **Avoid long/multi-line pastes into remote shells** — they get mangled. Prefer writing a
  script locally and shipping it (`scp ops/task.sh deploy@host:/tmp/` then one short SSH line).
- No interactive/blocking commands (no editors, no `git rebase -i`, no prompts).
