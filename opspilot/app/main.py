"""BVTech OpsPilot — application entrypoint."""
from __future__ import annotations

import secrets
import time
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .core.config import get_settings
from .core.db import Base, SessionLocal, engine
from .core.security import hash_password
from .models import Role, User
from .api.routes import (
    auth, resources, agent, ui, tickets, alerts, billing, kb, automation, security,
    scripts, signup, m365, invoices, networking, netdiag, download, contracts, reports,
    channels, report_schedules, integrations, search, oauth, projects, overview,
    time_tracking, assets, action_center, foresight, client_health, content,
    maintenance, analytics, mailbox, publishers, comms, rmm, crm, prospecting,
    campaigns, remote, quickbooks, gbp, hubspot, docs, payments, dialer, posture,
    remediation, inventory, autopost, setup, ai, branding, practice, status, users,
    library, academy, website, patching, copilot, psa, vcio, autonomy, incidents,
    content_autopilot, browser, public_tools, onboarding, answers, coop, kart,
)

_s = get_settings()
app = FastAPI(title=_s.APP_NAME, version=_s.APP_VERSION, docs_url=None, redoc_url=None)

_static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# v1.105: the BVTech Breach Protocol game (Rust -> WebAssembly) ships as a tiny
# static bundle (wasm + macroquad JS loader). Served at /arena. The bind-mounted
# path exists only in the running container/dev tree; guard so imports never fail.
import mimetypes as _mime
_mime.add_type("application/wasm", ".wasm")
_arena_dir = Path(__file__).resolve().parent.parent / "games" / "arena-web"
if _arena_dir.is_dir():
    app.mount("/arena", StaticFiles(directory=str(_arena_dir), html=True), name="arena")
# Graveyard Shift — our original 3D action-RPG (Godot 4 -> WebAssembly), served
# statically at its branded path /graveyard-shift (v1.113; the earlier macroquad
# arcade build in games/graveyard-web is kept as an archive). The Godot web
# export is a threadless build, so it needs no cross-origin-isolation headers.
_game_dir = Path(__file__).resolve().parent.parent / "games" / "graveyard-3d"
if not _game_dir.is_dir():
    # fall back to the archived arcade build if the 3D export is absent
    _game_dir = Path(__file__).resolve().parent.parent / "games" / "graveyard-web"
if _game_dir.is_dir():
    app.mount("/graveyard-shift", StaticFiles(directory=str(_game_dir), html=True), name="graveyard")

# Graveyard Shift: Reanimated — the new Three.js remaster, served at a STAGING
# path for QA. Production (/graveyard-shift) is left untouched until it passes.
# ("/graveyard-shift-beta" is not a sub-path of "/graveyard-shift/", so the two
# static mounts never collide.)
_beta_dir = Path(__file__).resolve().parent.parent / "games" / "graveyard-shift-beta"
if _beta_dir.is_dir():
    app.mount("/graveyard-shift-beta", StaticFiles(directory=str(_beta_dir), html=True), name="graveyard-beta")

# VOLT RUSH — original 3D multiplayer kart racer. The client is a static Vite
# bundle served here at /kart (single-player works fully offline); its realtime
# socket /kart/ws is bridged by kart.router to the authoritative `volt-rush` Node
# race service (separate compose service, internal-only). The ws route is
# registered BEFORE the /kart static mount so the mount never shadows it.
app.include_router(kart.router)
_kart_dir = Path(__file__).resolve().parent.parent / "games" / "volt-rush" / "dist"
if _kart_dir.is_dir():
    app.mount("/kart", StaticFiles(directory=str(_kart_dir), html=True), name="volt-rush")

# Keep the retired /signal path working: redirect it to the new home.
from fastapi.responses import RedirectResponse as _Redir  # noqa: E402
@app.get("/signal")
@app.get("/signal/")
async def _signal_root_redirect():
    return _Redir("/graveyard-shift/", status_code=308)
@app.get("/signal/{path:path}")
async def _signal_redirect(path: str):
    return _Redir("/graveyard-shift/" + path, status_code=308)


# --------------------------------------------------------------------------- #
# Comprehensive audit trail — record every mutating API call (v0.22).
# Registered before security_headers so it wraps the full request lifecycle.
# --------------------------------------------------------------------------- #
from .services.audit_mw import audit_mutations  # noqa: E402
app.middleware("http")(audit_mutations)


# --------------------------------------------------------------------------- #
# Security headers
# --------------------------------------------------------------------------- #
@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    _game_path = request.url.path.startswith(("/arena", "/graveyard-shift", "/kart"))
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        # the Godot/WASM game shells load their boot splash + icons as blob: images
        "img-src 'self' data:" + (" blob:" if _game_path else "") + "; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        # blob: lets the Content Studio preview its generated page in an iframe
        # (the blob is created by our own page; the framed doc has no extra rights).
        # worker-src blob: powers the Code Dojo sandbox — the learner's own code runs
        # in a terminable Web Worker (their browser, their risk), never on our server.
        "script-src 'self' 'unsafe-inline'"
        + (" 'wasm-unsafe-eval'" if _game_path else "")
        + "; worker-src 'self' blob:; "
        "frame-src 'self' blob:; frame-ancestors 'none'"
    )
    # Game HTML (directory index / *.html) must always revalidate so a new deploy
    # shows up immediately instead of serving a stale edge/browser copy; the
    # fingerprinted JS/CSS/model assets stay freely cacheable.
    if _game_path and (request.url.path.endswith("/") or request.url.path.endswith(".html")):
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
    if _s.is_prod:
        resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return resp


# --------------------------------------------------------------------------- #
# Minimal in-memory rate limit for /api/auth/login (per IP).
# For multi-worker prod, move this to Redis — see docs/SECURITY.md.
# --------------------------------------------------------------------------- #
_login_hits: dict[str, list[float]] = defaultdict(list)


_RATE_LIMITED = {
    "/api/auth/login": lambda: _s.RATE_LIMIT_LOGIN_PER_MIN,
    "/api/signup": lambda: _s.RATE_LIMIT_SIGNUP_PER_MIN,
    "/api/academy/register": lambda: _s.RATE_LIMIT_SIGNUP_PER_MIN,
}


@app.middleware("http")
async def basic_rate_limit(request: Request, call_next):
    limit_fn = _RATE_LIMITED.get(request.url.path)
    if limit_fn and request.method == "POST":
        ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")
        key = f"{request.url.path}:{ip}"
        now = time.time()
        window = [t for t in _login_hits[key] if now - t < 60]
        if len(window) >= limit_fn():
            return JSONResponse(
                {"detail": "Too many attempts. Wait a minute."},
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        window.append(now)
        _login_hits[key] = window
    return await call_next(request)


# --------------------------------------------------------------------------- #
# v1.94 Request guard (PHP2Shell response) — registered LAST so it is the
# outermost layer: oversized bodies (413), inbound multipart (415) and PHP/
# WordPress probe paths (404) are dropped before audit, rate limit or the DB.
# --------------------------------------------------------------------------- #
from .core.request_guard import RequestGuard  # noqa: E402
app.add_middleware(RequestGuard)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
app.include_router(auth.router)
app.include_router(resources.router)
app.include_router(agent.router)
app.include_router(tickets.router)
app.include_router(alerts.router)
app.include_router(billing.router)
app.include_router(kb.router)
app.include_router(automation.router)
app.include_router(automation.notif_router)
app.include_router(security.router)
app.include_router(scripts.router)
app.include_router(signup.router)
app.include_router(m365.router)
app.include_router(invoices.router)
app.include_router(networking.router)
app.include_router(netdiag.router)
app.include_router(download.router)
app.include_router(contracts.router)
app.include_router(psa.router)
app.include_router(vcio.router)
app.include_router(onboarding.router)
app.include_router(coop.router)
app.include_router(autonomy.router)
app.include_router(incidents.router)
app.include_router(content_autopilot.router)
app.include_router(browser.router)
app.include_router(reports.router)
app.include_router(channels.router)
app.include_router(report_schedules.router)
app.include_router(integrations.router)
app.include_router(integrations.ingest_router)
app.include_router(search.router)
app.include_router(oauth.router)
app.include_router(projects.router)
app.include_router(overview.router)
app.include_router(time_tracking.router)
app.include_router(assets.router)
app.include_router(action_center.router)
app.include_router(foresight.router)
app.include_router(client_health.router)
app.include_router(content.router)
app.include_router(maintenance.router)
app.include_router(analytics.router)
app.include_router(mailbox.router)
app.include_router(publishers.router)
app.include_router(comms.router)
app.include_router(rmm.router)
app.include_router(crm.router)
app.include_router(prospecting.router)
app.include_router(campaigns.router)
app.include_router(remote.router)
app.include_router(quickbooks.router)
app.include_router(gbp.router)
app.include_router(hubspot.router)
app.include_router(docs.router)
app.include_router(payments.router)
app.include_router(dialer.router)
app.include_router(posture.router)
app.include_router(remediation.router)
app.include_router(inventory.router)
app.include_router(autopost.router)
app.include_router(setup.router)
app.include_router(ai.router)
app.include_router(branding.router)
app.include_router(practice.router)
app.include_router(status.router)
app.include_router(users.router)
app.include_router(library.router)
app.include_router(academy.router)
app.include_router(website.router)
app.include_router(patching.router)
app.include_router(copilot.router)
app.include_router(public_tools.router)
app.include_router(answers.router)


# --- BVTech Answers community pages (server-rendered, same-origin session auth) ---
from fastapi.responses import HTMLResponse as _HTMLResp
from .services import pages_answers as _pa


@app.get("/answers", response_class=_HTMLResp)
def answers_home():
    return _HTMLResp(_pa.page())


@app.get("/answers/{qid}", response_class=_HTMLResp)
def answers_question(qid: int):
    return _HTMLResp(_pa.page(initial_qid=qid))


app.include_router(ui.router)


@app.get("/api/health")
def health():
    """Liveness + version, PLUS public proof-of-life for the content autopilot —
    'is the scheduler ticking and did today's posts go out' is answerable from
    anywhere (a browser, the daily GitHub cron, an uptime monitor) with no login.
    Nothing sensitive is exposed: a timestamp age, booleans, per-channel dates."""
    out = {"ok": True, "app": _s.APP_NAME, "version": _s.APP_VERSION, "env": _s.ENV}
    try:
        from datetime import datetime, timezone
        from .core.db import SessionLocal
        from .models import SchedulerRun
        from .services import content_autopilot
        db = SessionLocal()
        try:
            last = db.query(SchedulerRun).order_by(SchedulerRun.id.desc()).first()
            age = None
            if last and last.ran_at:
                ran = last.ran_at if last.ran_at.tzinfo else last.ran_at.replace(tzinfo=timezone.utc)
                age = int((datetime.now(timezone.utc) - ran).total_seconds())
            cfg = content_autopilot.get_config(db)
            out["autopilot"] = {
                "ticking": age is not None and age < 360,
                "last_tick_age_seconds": age,
                "daily_enabled": cfg["enabled"],
                "post_hour_utc": cfg["hour_utc"],
                "last_success": cfg["last"],          # {channel: ISO date}
            }
        finally:
            db.close()
    except Exception:  # noqa: BLE001 — health must never 500 over telemetry
        out["autopilot"] = {"ticking": None}
    return out


# --------------------------------------------------------------------------- #
# Startup: create tables (dev) + bootstrap the first owner account.
# In production, prefer Alembic migrations over create_all (see migrations/).
# --------------------------------------------------------------------------- #
def _reconcile_schema():
    """Self-heal schema drift on boot so the running code never queries a column
    or table the DB lacks. Alembic is still the source of truth, but deploy.sh
    runs it best-effort (|| WARN) and the API starts BEFORE migrations apply — so
    a failed/half-applied migration would otherwise break every query against the
    affected table (e.g. integration_connections), making saved settings read as
    "not connected". This makes startup idempotently reconcile:
      1. create_all() — adds any MISSING tables (checkfirst; never touches existing)
      2. ensure the recently-added COLUMNS exist (create_all can't add columns)
    Both are safe to run every boot and on every dialect."""
    from sqlalchemy import inspect, text
    try:
        Base.metadata.create_all(bind=engine)   # missing tables only
    except Exception as e:  # noqa: BLE001
        print(f"[schema] create_all warning: {e}")

    # Auto-heal COLUMN drift: for every mapped table that already exists, add any
    # column the model declares but the DB lacks. This is generated from the model
    # metadata (not a hand-kept list), so a newly-added column can never silently
    # 500 every query against its table on an older prod DB. Added columns are
    # nullable + no default (safe to add to a populated table); the app supplies
    # values on write. Best-effort per column — one failure never aborts the rest.
    insp = inspect(engine)
    try:
        existing_tables = set(insp.get_table_names())
    except Exception:  # noqa: BLE001
        existing_tables = set()

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue   # create_all just made it (with all columns) or will
        try:
            have = {c["name"] for c in insp.get_columns(table.name)}
        except Exception:  # noqa: BLE001
            continue
        for col in table.columns:
            if col.name in have:
                continue
            try:
                coltype = col.type.compile(dialect=engine.dialect)
            except Exception:  # noqa: BLE001
                coltype = "VARCHAR(255)"
            try:
                with engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {coltype}'))
                print(f"[schema] added missing column {table.name}.{col.name} ({coltype})")
            except Exception as e:  # noqa: BLE001
                print(f"[schema] could not add {table.name}.{col.name}: {e}")


@app.on_event("startup")
def _startup():
    # Always reconcile (prod + dev): the cost is one cheap inspection per boot and
    # it guarantees the schema matches the deployed code.
    _reconcile_schema()

    db = SessionLocal()
    try:
        # Idempotently ensure the CONFIGURED owner account exists. Keying on the
        # email (not "any owner") means upgrading an existing deployment still
        # provisions BOOTSTRAP_ADMIN_EMAIL so you can always sign in.
        email = _s.BOOTSTRAP_ADMIN_EMAIL.lower()
        existing = db.query(User).filter(User.email == email).first()
        if not existing:
            pw = _s.BOOTSTRAP_ADMIN_PASSWORD or secrets.token_urlsafe(16)
            owner = User(
                email=email,
                full_name="BVTech Owner",
                password_hash=hash_password(pw),
                role=Role.OWNER,
                is_active=True,
            )
            db.add(owner)
            db.commit()
            print("=" * 60)
            print(f"  OWNER ACCOUNT READY: {owner.email}")
            if not _s.BOOTSTRAP_ADMIN_PASSWORD:
                print(f"  TEMP PASSWORD (shown once): {pw}")
            print("  -> Log in, enable MFA, then rotate this password.")
            print("=" * 60)

        # Seed the document library catalog (missing entries only; visibility
        # edits made in the UI are never overwritten).
        try:
            from .services import library as _library
            n = _library.seed(db)
            if n:
                print(f"[library] catalogued {n} document(s)")
        except Exception as e:  # noqa: BLE001
            print(f"[library] seed warning: {e}")

        # Bridge integration credentials from .env into the vault, so keys set in
        # the environment light up their integrations without the Settings UI.
        try:
            from .services import env_credentials
            applied = env_credentials.load(db)
            if applied:
                print("[env-creds] loaded from env: " +
                      ", ".join(f"{k}({len(v)})" for k, v in applied.items()))
        except Exception as e:  # noqa: BLE001
            print(f"[env-creds] warning: {e}")
    finally:
        db.close()

    # Autopilot (v1.1): the in-process scheduler that drives every recurring
    # check (SLA breaches, offline sweeps, digests, invoices, posts, AI triage)
    # with no external cron. Disable with SCHEDULER_ENABLED=0.
    try:
        from .services import scheduler
        if scheduler.start():
            print(f"[autopilot] running — first tick in {scheduler.FIRST_DELAY_SEC}s, "
                  f"then every {scheduler.INTERVAL_SEC}s")
        else:
            print("[autopilot] disabled via SCHEDULER_ENABLED")
    except Exception as e:  # noqa: BLE001
        print(f"[autopilot] failed to start: {e}")
