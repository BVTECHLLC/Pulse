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
    scripts,
)

_s = get_settings()
app = FastAPI(title=_s.APP_NAME, version=_s.APP_VERSION, docs_url=None, redoc_url=None)

_static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


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
        "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
        "frame-ancestors 'none'"
    )
    if _s.is_prod:
        resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return resp


# --------------------------------------------------------------------------- #
# Minimal in-memory rate limit for /api/auth/login (per IP).
# For multi-worker prod, move this to Redis — see docs/SECURITY.md.
# --------------------------------------------------------------------------- #
_login_hits: dict[str, list[float]] = defaultdict(list)


@app.middleware("http")
async def login_rate_limit(request: Request, call_next):
    if request.url.path == "/api/auth/login" and request.method == "POST":
        ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")
        now = time.time()
        window = [t for t in _login_hits[ip] if now - t < 60]
        if len(window) >= _s.RATE_LIMIT_LOGIN_PER_MIN:
            return JSONResponse(
                {"detail": "Too many attempts. Wait a minute."},
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        window.append(now)
        _login_hits[ip] = window
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
        existing = db.query(User).filter(User.role == Role.OWNER).first()
        if not existing:
            pw = _s.BOOTSTRAP_ADMIN_PASSWORD or secrets.token_urlsafe(16)
            owner = User(
                email=_s.BOOTSTRAP_ADMIN_EMAIL.lower(),
                full_name="BVTech Owner",
                password_hash=hash_password(pw),
                role=Role.OWNER,
                is_active=True,
            )
            db.add(owner)
            db.commit()
            print("=" * 60)
            print(f"  BOOTSTRAP OWNER CREATED: {owner.email}")
            if not _s.BOOTSTRAP_ADMIN_PASSWORD:
                print(f"  TEMP PASSWORD (shown once): {pw}")
            print("  -> Log in, enable MFA, then rotate this password.")
            print("=" * 60)
    finally:
        db.close()
