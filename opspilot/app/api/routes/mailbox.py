"""v0.41 Secure mailbox — read & send the MSP's own Microsoft 365 mail in Pulse.

Credentials for the house Microsoft 365 tenant (tenant_id / client_id /
client_secret + default mailbox) are entered once through the Settings UI and
stored ENCRYPTED on a singleton platform IntegrationConnection — never in the
repo, never echoed to the browser. The app uses an app-only Graph token
(Mail.Read / Mail.Send, admin-consented) to list, read, and send mail.

Staff-only (OWNER/TECH). All access is audited.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Role, User
from ...services import audit, m365, secure_config

router = APIRouter(prefix="/api/mailbox", tags=["mailbox"])

PROVIDER = "m365_mailbox"
_REQUIRED = ("tenant_id", "client_id", "client_secret")


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _client_for(db: Session) -> tuple[m365.GraphClient, str]:
    """Build a Graph client from the stored platform credentials + default mailbox."""
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    if not secure_config.configured(cfg, _REQUIRED):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Mailbox not configured — add tenant/app credentials in Settings → Mailbox.")
    tenant = secure_config.get_secret(cfg, "tenant_id") or cfg.get("tenant_id")
    client_id = secure_config.get_secret(cfg, "client_id") or cfg.get("client_id")
    client_secret = secure_config.get_secret(cfg, "client_secret")
    mailbox = cfg.get("mailbox") or ""
    return m365.GraphClient(str(tenant), str(client_id), str(client_secret)), str(mailbox)


def _resolve_mailbox(db: Session, requested: str | None) -> tuple[m365.GraphClient, str]:
    graph, default_mb = _client_for(db)
    mb = (requested or default_mb).strip()
    if not mb:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "No mailbox specified and no default mailbox saved in Settings.")
    return graph, mb


# --------------------------------------------------------------------------- #
# Settings (credentials)
# --------------------------------------------------------------------------- #
class MailboxSettingsIn(BaseModel):
    tenant_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    mailbox: str | None = None


@router.get("/settings")
def get_settings(db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    return {
        "configured": secure_config.configured(cfg, _REQUIRED),
        "fields": secure_config.public_view(cfg),
        "mailbox": cfg.get("mailbox"),
    }


@router.put("/settings")
def save_settings(body: MailboxSettingsIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER))):
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    conn = secure_config.upsert_platform(db, PROVIDER, "Microsoft 365 Mailbox",
                                         "Identity/Email", payload)
    audit.record(db, action="mailbox.configure", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="integration", target_id=str(conn.id),
                 ip=_ip(request), detail="updated mailbox credentials")
    cfg = conn.config or {}
    return {"ok": True, "configured": secure_config.configured(cfg, _REQUIRED),
            "fields": secure_config.public_view(cfg), "mailbox": cfg.get("mailbox")}


@router.post("/test")
def test_connection(request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    graph, mb = _resolve_mailbox(db, None)
    try:
        folders = graph.list_mail_folders(mb)
    except m365.GraphError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Graph test failed: {e}")
    return {"ok": True, "mailbox": mb, "folders": len(folders)}


# --------------------------------------------------------------------------- #
# Mail
# --------------------------------------------------------------------------- #
@router.get("/folders")
def folders(mailbox: str | None = Query(None), db: Session = Depends(get_db),
            user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    graph, mb = _resolve_mailbox(db, mailbox)
    try:
        return {"mailbox": mb, "folders": graph.list_mail_folders(mb)}
    except m365.GraphError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))


@router.get("/messages")
def messages(mailbox: str | None = Query(None), folder: str = Query("inbox"),
             top: int = Query(25, le=100, ge=1), skip: int = Query(0, ge=0),
             search: str | None = Query(None), db: Session = Depends(get_db),
             user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    graph, mb = _resolve_mailbox(db, mailbox)
    try:
        items = graph.list_messages(mb, folder=folder, top=top, skip=skip, search=search)
    except m365.GraphError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    return {"mailbox": mb, "folder": folder, "messages": items}


@router.get("/messages/{message_id}")
def message(message_id: str, mailbox: str | None = Query(None), db: Session = Depends(get_db),
            user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    graph, mb = _resolve_mailbox(db, mailbox)
    try:
        return graph.get_message(mb, message_id)
    except m365.GraphError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))


class SendIn(BaseModel):
    to: list[str]
    subject: str
    body: str
    html: bool = False
    cc: list[str] | None = None
    mailbox: str | None = None


@router.post("/send", status_code=202)
def send(body: SendIn, request: Request, db: Session = Depends(get_db),
         user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not body.to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one recipient is required.")
    graph, mb = _resolve_mailbox(db, body.mailbox)
    try:
        graph.send_mail(mb, body.to, body.subject, body.body, html=body.html, cc=body.cc)
    except m365.GraphError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    audit.record(db, action="mailbox.send", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="mailbox", target_id=mb,
                 ip=_ip(request), detail=f"to={','.join(body.to)[:160]} subj={body.subject[:80]}")
    return {"ok": True, "sent_from": mb, "to": body.to}


class ReadIn(BaseModel):
    is_read: bool = True
    mailbox: str | None = None


@router.post("/messages/{message_id}/read")
def set_read(message_id: str, body: ReadIn, db: Session = Depends(get_db),
             user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    graph, mb = _resolve_mailbox(db, body.mailbox)
    try:
        graph.mark_read(mb, message_id, body.is_read)
    except m365.GraphError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    return {"ok": True}
