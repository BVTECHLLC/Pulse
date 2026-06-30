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
    maintenance, analytics, mailbox, publishers, comms, rmm,
)

_s = get_settings()
app = FastAPI(title=_s.APP_NAME, version=_s.APP_VERSION, docs_url=None, redoc_url=None)

_static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


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
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        # blob: lets the Content Studio preview its generated page in an iframe
        # (the blob is created by our own page; the framed doc has no extra rights).
        "script-src 'self' 'unsafe-inline'; frame-src 'self' blob:; frame-ancestors 'none'"
    )
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
app.include_router(ui.router)


@app.get("/api/health")
def health():
    return {"ok": True, "app": _s.APP_NAME, "version": _s.APP_VERSION, "env": _s.ENV}


# --------------------------------------------------------------------------- #
# Startup: create tables (dev) + bootstrap the first owner account.
# In production, prefer Alembic migrations over create_all (see migrations/).
# --------------------------------------------------------------------------- #
@app.on_event("startup")
def _startup():
    if not _s.is_prod:
        Base.metadata.create_all(bind=engine)

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
    finally:
        db.close()
