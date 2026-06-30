"""v0.21 Integrations & Command Center.

Three interop primitives plus a catalog:
  * API keys      — programmatic access for any external tool (auth as the owner)
  * Webhooks OUT  — signed event delivery to subscriber URLs (the event bus)
  * Inbound ingest— any tool POSTs JSON to /api/ingest/{token} -> ticket/alert
  * Catalog       — a directory of products you can connect, + saved connections
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff, require_roles
from ...core.security import hash_api_key, random_token
from ...models import (
    Alert, AlertSeverity, AlertStatus, APIKey, Client, InboundSource,
    IntegrationConnection, Role, SupportTicket, TicketStatus, User,
    WebhookSubscription, WEBHOOK_EVENTS,
)
from ...services import audit, events

router = APIRouter(prefix="/api/integrations", tags=["integrations"])
ingest_router = APIRouter(prefix="/api/ingest", tags=["integrations-ingest"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


# A curated catalog so the UI can present "connect anything". Connecting is via
# API key / webhook / inbound ingest, which work with literally any product.
INTEGRATION_CATALOG = [
    {"key": "connectwise", "name": "ConnectWise Manage", "category": "PSA"},
    {"key": "autotask", "name": "Datto Autotask", "category": "PSA"},
    {"key": "halopsa", "name": "HaloPSA", "category": "PSA"},
    {"key": "syncro", "name": "Syncro", "category": "PSA/RMM"},
    {"key": "datto_rmm", "name": "Datto RMM", "category": "RMM"},
    {"key": "ninjaone", "name": "NinjaOne", "category": "RMM"},
    {"key": "n_able", "name": "N-able N-central", "category": "RMM"},
    {"key": "itglue", "name": "IT Glue", "category": "Documentation"},
    {"key": "hudu", "name": "Hudu", "category": "Documentation"},
    {"key": "slack", "name": "Slack", "category": "Communication"},
    {"key": "teams", "name": "Microsoft Teams", "category": "Communication"},
    {"key": "m365", "name": "Microsoft 365", "category": "Identity/Email"},
    {"key": "google_workspace", "name": "Google Workspace", "category": "Identity/Email"},
    {"key": "quickbooks", "name": "QuickBooks Online", "category": "Accounting"},
    {"key": "xero", "name": "Xero", "category": "Accounting"},
    {"key": "stripe", "name": "Stripe", "category": "Payments"},
    {"key": "pax8", "name": "Pax8", "category": "Distribution"},
    {"key": "sentinelone", "name": "SentinelOne", "category": "Security/EDR"},
    {"key": "bitdefender", "name": "Bitdefender", "category": "Security/EDR"},
    {"key": "huntress", "name": "Huntress", "category": "Security/MDR"},
    {"key": "zapier", "name": "Zapier", "category": "Automation"},
    {"key": "make", "name": "Make (Integromat)", "category": "Automation"},
    {"key": "webhook", "name": "Custom Webhook / REST API", "category": "Custom"},
]


# --------------------------------------------------------------------------- #
# API keys (staff-managed). Authenticate external callers AS the owner.
# --------------------------------------------------------------------------- #
class APIKeyIn(BaseModel):
    label: str


@router.get("/api-keys")
def list_api_keys(db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    rows = db.query(APIKey).order_by(APIKey.id.desc()).all()
    return [{"id": k.id, "label": k.label, "prefix": k.prefix, "revoked": k.revoked,
             "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
             "created_at": k.created_at.isoformat() if k.created_at else None} for k in rows]


@router.post("/api-keys", status_code=201)
def create_api_key(body: APIKeyIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    raw = "pulse_" + random_token(24)
    prefix = raw[:14]
    k = APIKey(user_id=user.id, label=body.label.strip() or "API key",
               prefix=prefix, key_hash=hash_api_key(raw))
    db.add(k)
    db.commit()
    audit.record(db, action="apikey.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="api_key", target_id=str(k.id),
                 ip=_ip(request), detail=f"label={k.label}")
    # Plaintext returned exactly once.
    return {"id": k.id, "label": k.label, "api_key": raw,
            "note": "Store this now — it will not be shown again. Send it as the X-API-Key header."}


@router.delete("/api-keys/{key_id}", status_code=204)
def revoke_api_key(key_id: int, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    k = db.get(APIKey, key_id)
    if not k:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Key not found")
    k.revoked = True
    db.commit()
    audit.record(db, action="apikey.revoke", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="api_key", target_id=str(k.id), ip=_ip(request))


# --------------------------------------------------------------------------- #
# Outbound webhook subscriptions (the event bus)
# --------------------------------------------------------------------------- #
class WebhookIn(BaseModel):
    url: str
    events: list[str] = []
    client_id: int | None = None


@router.get("/events")
def list_events():
    return {"events": WEBHOOK_EVENTS}


@router.get("/webhooks")
def list_webhooks(db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    rows = db.query(WebhookSubscription).order_by(WebhookSubscription.id.desc()).all()
    return [{"id": w.id, "url": w.url, "events": w.events or [], "client_id": w.client_id,
             "enabled": w.enabled, "last_status": w.last_status,
             "last_fired_at": w.last_fired_at.isoformat() if w.last_fired_at else None} for w in rows]


@router.post("/webhooks", status_code=201)
def create_webhook(body: WebhookIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not body.url.lower().startswith(("http://", "https://")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "url must be http(s)")
    bad = [e for e in body.events if e not in WEBHOOK_EVENTS]
    if bad:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown events: {bad}")
    w = WebhookSubscription(url=body.url.strip(), events=body.events,
                            secret=random_token(16), client_id=body.client_id, enabled=True)
    db.add(w)
    db.commit()
    audit.record(db, action="webhook.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="webhook", target_id=str(w.id), ip=_ip(request))
    return {"id": w.id, "secret": w.secret,
            "note": "Verify deliveries with the X-OpsPilot-Signature: sha256=HMAC(secret, body) header."}


@router.post("/webhooks/{wid}/test")
def test_webhook(wid: int, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    w = db.get(WebhookSubscription, wid)
    if not w:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found")
    status_code = events._deliver(w, "ping", {"message": "OpsPilot test event"})
    w.last_status = status_code
    w.last_fired_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": status_code is not None and 200 <= status_code < 300, "status": status_code}


@router.post("/webhooks/{wid}/toggle")
def toggle_webhook(wid: int, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    w = db.get(WebhookSubscription, wid)
    if not w:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found")
    w.enabled = not w.enabled
    db.commit()
    return {"id": w.id, "enabled": w.enabled}


@router.delete("/webhooks/{wid}", status_code=204)
def delete_webhook(wid: int, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    w = db.get(WebhookSubscription, wid)
    if not w:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found")
    db.delete(w)
    db.commit()


# --------------------------------------------------------------------------- #
# Inbound ingest sources
# --------------------------------------------------------------------------- #
class InboundIn(BaseModel):
    name: str
    client_id: int
    action: str = "ticket"   # ticket|alert


@router.get("/inbound")
def list_inbound(request: Request, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    rows = db.query(InboundSource).order_by(InboundSource.id.desc()).all()
    base = _base_url(request)
    return [{"id": s.id, "name": s.name, "client_id": s.client_id, "action": s.action,
             "enabled": s.enabled, "received_count": s.received_count,
             "url": f"{base}/api/ingest/{s.token}",
             "last_received_at": s.last_received_at.isoformat() if s.last_received_at else None}
            for s in rows]


@router.post("/inbound", status_code=201)
def create_inbound(body: InboundIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if body.action not in ("ticket", "alert"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "action must be ticket|alert")
    if not db.get(Client, body.client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    s = InboundSource(name=body.name.strip() or "Inbound", token=random_token(20),
                      client_id=body.client_id, action=body.action, enabled=True)
    db.add(s)
    db.commit()
    audit.record(db, action="inbound.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="inbound_source", target_id=str(s.id),
                 client_id=s.client_id, ip=_ip(request))
    return {"id": s.id, "url": f"{_base_url(request)}/api/ingest/{s.token}",
            "note": "POST any JSON here. Recognized fields: subject/title, body/message, severity, priority."}


@router.post("/inbound/{sid}/toggle")
def toggle_inbound(sid: int, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    s = db.get(InboundSource, sid)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
    s.enabled = not s.enabled
    db.commit()
    return {"id": s.id, "enabled": s.enabled}


@router.delete("/inbound/{sid}", status_code=204)
def delete_inbound(sid: int, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    s = db.get(InboundSource, sid)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
    db.delete(s)
    db.commit()


def _base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


# --------------------------------------------------------------------------- #
# Integration catalog + saved connections (the command-center hub)
# --------------------------------------------------------------------------- #
@router.get("/catalog")
def catalog():
    return {"catalog": INTEGRATION_CATALOG}


# --------------------------------------------------------------------------- #
# Platform integrations status hub (v0.50) — one place to see what's connected.
# Each entry maps a vault provider to the keys it needs + where to configure it,
# so the UI can render a live "connected / not configured" board. This is what
# turns a silently-expired key into something you can SEE.
# --------------------------------------------------------------------------- #
PLATFORM_INTEGRATIONS = [
    {"key": "m365_mailbox", "name": "Microsoft 365 Mailbox", "category": "Email",
     "required": ["tenant_id", "client_id", "client_secret"], "icon": "📬", "tab": "settings"},
    {"key": "pub_linkedin", "name": "LinkedIn Publisher", "category": "Marketing",
     "required": ["access_token", "person_urn"], "icon": "💼", "tab": "settings"},
    {"key": "gbp", "name": "Google Business Profile", "category": "Marketing",
     "required": ["client_id", "client_secret", "refresh_token", "account_name", "location_name"],
     "icon": "📍", "tab": "settings"},
    {"key": "dialpad", "name": "Dialpad (calls + SMS)", "category": "Telephony",
     "required": ["api_key", "user_id"], "icon": "📞", "tab": "settings"},
    {"key": "tacticalrmm", "name": "Tactical RMM connector", "category": "RMM",
     "required": ["base_url", "api_key"], "icon": "🖥️", "tab": "rmm"},
    {"key": "google_places", "name": "Prospecting (Google Places)", "category": "Sales",
     "required": ["api_key"], "icon": "🔎", "tab": "crm"},
    {"key": "hubspot", "name": "HubSpot", "category": "CRM",
     "required": ["token"], "icon": "🟠", "tab": "settings"},
    {"key": "quickbooks", "name": "QuickBooks Online", "category": "Accounting",
     "required": ["client_id", "client_secret", "refresh_token", "realm_id"],
     "icon": "💵", "tab": "settings"},
    {"key": "pub_web_bvtech", "name": "BVTech.org Auto-Publisher", "category": "Marketing",
     "required": ["site_url"], "icon": "🌐", "tab": "settings"},
    {"key": "pub_web_jp", "name": "JordanPolasek.com Auto-Publisher", "category": "Marketing",
     "required": ["site_url"], "icon": "🌐", "tab": "settings"},
]


@router.get("/status")
def platform_status(db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    from ...services import secure_config  # local import avoids cycle
    out = []
    connected = 0
    for spec in PLATFORM_INTEGRATIONS:
        conn = secure_config.get_platform(db, spec["key"])
        cfg = (conn.config if conn else None) or {}
        ok = secure_config.configured(cfg, spec["required"]) if spec["required"] else bool(conn)
        if ok:
            connected += 1
        out.append({"key": spec["key"], "name": spec["name"], "category": spec["category"],
                    "icon": spec["icon"], "tab": spec["tab"], "configured": ok,
                    "enabled": bool(conn.enabled) if conn else False})
    return {"integrations": out, "connected": connected, "total": len(PLATFORM_INTEGRATIONS)}


class ConnectionIn(BaseModel):
    provider: str
    name: str | None = None
    category: str | None = None
    config: dict = {}
    client_id: int | None = None


@router.get("/connections")
def list_connections(db: Session = Depends(get_db),
                     user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    rows = db.query(IntegrationConnection).order_by(IntegrationConnection.id.desc()).all()
    # Never echo secret-ish config values back; just report which keys are set.
    return [{"id": c.id, "provider": c.provider, "name": c.name, "category": c.category,
             "config_keys": sorted((c.config or {}).keys()), "client_id": c.client_id,
             "enabled": c.enabled} for c in rows]


@router.post("/connections", status_code=201)
def create_connection(body: ConnectionIn, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    known = {c["key"]: c for c in INTEGRATION_CATALOG}
    meta = known.get(body.provider)
    name = body.name or (meta["name"] if meta else body.provider)
    category = body.category or (meta["category"] if meta else None)
    c = IntegrationConnection(provider=body.provider, name=name, category=category,
                              config=body.config or {}, client_id=body.client_id, enabled=True)
    db.add(c)
    db.commit()
    audit.record(db, action="integration.connect", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="integration", target_id=str(c.id),
                 ip=_ip(request), detail=f"provider={c.provider}")
    return {"id": c.id, "provider": c.provider, "name": c.name}


@router.post("/connections/{cid}/toggle")
def toggle_connection(cid: int, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    c = db.get(IntegrationConnection, cid)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
    c.enabled = not c.enabled
    db.commit()
    return {"id": c.id, "enabled": c.enabled}


@router.delete("/connections/{cid}", status_code=204)
def delete_connection(cid: int, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    c = db.get(IntegrationConnection, cid)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
    db.delete(c)
    db.commit()


# --------------------------------------------------------------------------- #
# Public ingest endpoint — the token IS the auth. No session required.
# --------------------------------------------------------------------------- #
class IngestIn(BaseModel):
    subject: str | None = None
    title: str | None = None
    body: str | None = None
    message: str | None = None
    severity: str | None = None
    priority: str | None = None


@ingest_router.post("/{token}")
def ingest(token: str, body: IngestIn, request: Request, db: Session = Depends(get_db)):
    src = (db.query(InboundSource)
           .filter(InboundSource.token == token, InboundSource.enabled.is_(True)).first())
    if not src:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown or disabled ingest token")
    subject = (body.subject or body.title or "Inbound event").strip()[:200]
    text = (body.body or body.message or "").strip()
    now = datetime.now(timezone.utc)
    src.last_received_at = now
    src.received_count = (src.received_count or 0) + 1

    if src.action == "alert":
        sev = (body.severity or "warning").lower()
        sev_enum = {"info": AlertSeverity.INFO, "warning": AlertSeverity.WARNING,
                    "critical": AlertSeverity.CRITICAL}.get(sev, AlertSeverity.WARNING)
        row = Alert(client_id=src.client_id, kind="inbound", severity=sev_enum,
                    status=AlertStatus.ACTIVE, message=(subject + ("\n" + text if text else "")))
        db.add(row)
        db.commit()
        events.emit(db, "alert.opened", {"id": row.id, "client_id": src.client_id,
                    "kind": "inbound", "message": subject}, client_id=src.client_id)
        return {"ok": True, "created": "alert", "id": row.id}

    pri = (body.priority or "normal").lower()
    if pri not in ("low", "normal", "high", "urgent"):
        pri = "normal"
    t = SupportTicket(client_id=src.client_id, subject=subject, body=text or subject,
                      priority=pri, status=TicketStatus.OPEN)
    db.add(t)
    db.commit()
    events.emit(db, "ticket.created", {"id": t.id, "client_id": src.client_id,
                "subject": subject, "priority": pri}, client_id=src.client_id)
    return {"ok": True, "created": "ticket", "id": t.id}
