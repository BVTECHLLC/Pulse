"""v0.22 comprehensive audit trail.

A middleware records EVERY mutating API request (POST/PUT/PATCH/DELETE under
/api/), not just logins — capturing who (resolved from the session cookie /
Bearer token / API key), what (method + path), the outcome (HTTP status), and
the source IP. High-frequency machine telemetry (agent check-ins, job/diag
polls, inventory/patch reports) is skipped so the log stays human-meaningful.

This is additive: routes that already write rich, targeted audit rows keep
doing so; this guarantees nothing slips through."""
from __future__ import annotations

from ..core.db import SessionLocal
from ..core.security import decode_token, hash_api_key
from . import audit

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

# Machine telemetry that fires constantly — would flood the trail. These are
# auditable at the moments that matter (e.g. enrollment) by their own routes.
_SKIP_PREFIXES = (
    "/api/agent/checkin", "/api/agent/jobs", "/api/agent/diagnostics",
    "/api/agent/inventory", "/api/agent/patches",
)


def _client_ip(request) -> str:
    return (request.headers.get("cf-connecting-ip")
            or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "?"))


def _resolve_actor(request, db) -> tuple[int | None, str | None, str | None]:
    """Best-effort (user_id, email, role) from the request's credentials. Never
    raises — an unauthenticated/invalid request is logged with actor=None."""
    from ..models import APIKey, User
    # API key
    key = request.headers.get("x-api-key")
    if key:
        row = db.query(APIKey).filter(APIKey.key_hash == hash_api_key(key)).first()
        if row:
            u = db.get(User, row.user_id)
            if u:
                return u.id, u.email, (u.role.value if u.role else None) + " (api-key)"
        return None, "api-key", None
    # Session token (cookie or Bearer)
    token = request.cookies.get("access_token")
    if not token:
        authz = request.headers.get("authorization", "")
        if authz.lower().startswith("bearer "):
            token = authz.split(" ", 1)[1]
    if token:
        try:
            payload = decode_token(token)
            u = db.get(User, int(payload["sub"]))
            if u:
                return u.id, u.email, (u.role.value if u.role else None)
        except Exception:
            pass
    return None, None, None


async def audit_mutations(request, call_next):
    response = await call_next(request)
    try:
        path = request.url.path
        if (request.method in _MUTATING and path.startswith("/api/")
                and not any(path.startswith(p) for p in _SKIP_PREFIXES)):
            db = SessionLocal()
            try:
                uid, email, role = _resolve_actor(request, db)
                audit.record(
                    db,
                    action=f"api.{request.method.lower()}",
                    actor_user_id=uid, actor_email=email, actor_role=role,
                    target_type="endpoint", target_id=path,
                    ip=_client_ip(request),
                    detail=f"{request.method} {path} -> {response.status_code}",
                    success=response.status_code < 400,
                )
            finally:
                db.close()
    except Exception:
        # Auditing must never break the request/response cycle.
        pass
    return response
