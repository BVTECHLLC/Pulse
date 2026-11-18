"""Guardz (MDR / managed security) integration.

Connect a Guardz account (API token, stored encrypted in the secure vault) and
pull its open detections into Pulse — view them, and file them as security
findings under a client so they flow through the normal scorecard/alert/
remediation pipeline. Reads/sync are staff (OWNER/TECH); saving credentials is
OWNER-only and audited.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Client, FindingSeverity, FindingStatus, Role, SecurityFinding, User
from ...services import audit, guardz, secure_config, security

router = APIRouter(prefix="/api/guardz", tags=["guardz"])

PROVIDER = "guardz"
_REQUIRED = ("api_key",)


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _client(db: Session) -> guardz.GuardzClient:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    if not secure_config.configured(cfg, _REQUIRED):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Guardz not configured — add an API token in Settings → Integrations → Guardz.")
    key = secure_config.get_secret(cfg, "api_key")
    base = cfg.get("base_url") or (secure_config.get_secret(cfg, "base_url") if "base_url" in cfg else None)
    path = cfg.get("detections_path") or (secure_config.get_secret(cfg, "detections_path") if "detections_path" in cfg else None)
    try:
        return guardz.GuardzClient(str(key), base_url=base, detections_path=path)
    except guardz.GuardzError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


def _call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except guardz.GuardzError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))


class GuardzSettingsIn(BaseModel):
    api_key: str | None = None
    base_url: str | None = None          # optional override (default https://api.guardz.com)
    detections_path: str | None = None   # optional override (default /v1/detections)


@router.get("/settings")
def get_settings(db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    return {"configured": secure_config.configured(cfg, _REQUIRED),
            "fields": secure_config.public_view(cfg)}


@router.put("/settings")
def save_settings(body: GuardzSettingsIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER))):
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    conn = secure_config.upsert_platform(db, PROVIDER, "Guardz", "Security/MDR", payload)
    audit.record(db, action="guardz.configure", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="integration", target_id=str(conn.id),
                 ip=_ip(request), detail="guardz credentials")
    cfg = conn.config or {}
    return {"ok": True, "configured": secure_config.configured(cfg, _REQUIRED),
            "fields": secure_config.public_view(cfg)}


@router.post("/test")
def test(db: Session = Depends(get_db), user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return _call(_client(db).test_connection)


@router.get("/detections")
def detections(limit: int = 100, db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    raw = _call(_client(db).get_detections, limit=limit)
    return {"detections": [guardz.normalize_detection(d) for d in raw]}


class GuardzSyncIn(BaseModel):
    client_id: int
    limit: int = 100
    client_visible: bool = False


@router.post("/sync")
def sync(body: GuardzSyncIn, request: Request, db: Session = Depends(get_db),
         user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Pull Guardz detections and file them as security findings under a client
    (skipping ones already open with the same title), raising alerts on high/
    critical through the existing engine."""
    if not db.get(Client, body.client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    raw = _call(_client(db).get_detections, limit=body.limit)
    dets = [guardz.normalize_detection(d) for d in raw]
    existing = {f.title for f in db.query(SecurityFinding).filter(
        SecurityFinding.client_id == body.client_id,
        SecurityFinding.source == "guardz",
        SecurityFinding.status == FindingStatus.OPEN).all()}
    created = 0
    for d in dets:
        if d["title"] in existing:
            continue
        f = SecurityFinding(
            client_id=body.client_id, title=d["title"][:200], category="guardz",
            severity=FindingSeverity(d["severity"]),
            description=(d["description"] or "") + (f"\n\nEntity: {d['entity']}" if d.get("entity") else ""),
            recommendation="Review and remediate this detection in Guardz, then resolve it here.",
            source="guardz", client_visible=body.client_visible,
            created_by_user_id=user.id, author_email=user.email,
        )
        db.add(f)
        db.flush()
        security.raise_finding_alert(db, f)
        created += 1
    db.commit()
    audit.record(db, action="guardz.sync", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="client", target_id=str(body.client_id),
                 client_id=body.client_id, ip=_ip(request),
                 detail=f"detections={len(dets)} new_findings={created}")
    return {"ok": True, "detections": len(dets), "findings_created": created,
            "scorecard": security.scorecard(db, body.client_id)}
