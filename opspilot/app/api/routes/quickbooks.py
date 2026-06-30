"""v0.48 QuickBooks Online — connect + push Pulse invoices to QBO. Staff-only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Invoice, InvoiceLineItem, Client, Role, User
from ...services import audit, quickbooks, secure_config

router = APIRouter(prefix="/api/quickbooks", tags=["quickbooks"])

PROVIDER = "quickbooks"
_REQUIRED = ("client_id", "client_secret", "refresh_token", "realm_id")


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _client(db: Session) -> quickbooks.QBOClient:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    if not secure_config.configured(cfg, _REQUIRED):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "QuickBooks not configured — add credentials in Settings → QuickBooks.")
    sandbox = bool(cfg.get("sandbox"))
    return quickbooks.QBOClient(
        str(secure_config.get_secret(cfg, "client_id") or cfg.get("client_id")),
        str(secure_config.get_secret(cfg, "client_secret")),
        str(secure_config.get_secret(cfg, "refresh_token")),
        str(cfg.get("realm_id") or secure_config.get_secret(cfg, "realm_id")),
        sandbox=sandbox)


class QBSettingsIn(BaseModel):
    client_id: str | None = None
    client_secret: str | None = None
    refresh_token: str | None = None
    realm_id: str | None = None
    sandbox: bool | None = None


@router.get("/settings")
def get_settings(db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    return {"configured": secure_config.configured(cfg, _REQUIRED),
            "sandbox": bool(cfg.get("sandbox")), "fields": secure_config.public_view(cfg)}


@router.put("/settings")
def save_settings(body: QBSettingsIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER))):
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    conn = secure_config.upsert_platform(db, PROVIDER, "QuickBooks Online", "Accounting", payload)
    audit.record(db, action="quickbooks.configure", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="integration", target_id=str(conn.id),
                 ip=_ip(request), detail="qbo credentials")
    cfg = conn.config or {}
    return {"ok": True, "configured": secure_config.configured(cfg, _REQUIRED),
            "fields": secure_config.public_view(cfg)}


@router.post("/test")
def test(db: Session = Depends(get_db), user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    qbo = _client(db)
    try:
        name = qbo.company_name()
    except quickbooks.QBOError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    return {"ok": True, "company": name}


@router.post("/invoices/{invoice_id}/push")
def push_invoice(invoice_id: int, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER))):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    client = db.get(Client, inv.client_id)
    lines = db.query(InvoiceLineItem).filter(InvoiceLineItem.invoice_id == inv.id).all()
    if not lines:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invoice has no line items")
    qbo = _client(db)
    try:
        cust_id = qbo.find_or_create_customer(client.name if client else f"Client {inv.client_id}")
        result = qbo.create_invoice(cust_id, quickbooks.build_lines(lines),
                                    doc_number=inv.number)
    except quickbooks.QBOError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    qbo_id = (result.get("Invoice") or {}).get("Id")
    audit.record(db, action="quickbooks.push_invoice", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="invoice", target_id=str(inv.id),
                 client_id=inv.client_id, ip=_ip(request), detail=f"qbo_invoice={qbo_id}")
    return {"ok": True, "qbo_invoice_id": qbo_id, "customer_id": cust_id}
