"""v0.57 Payments — Stripe Checkout for invoices + auto-reconcile webhook."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Invoice, InvoiceStatus, Role, User
from ...services import audit, secure_config, stripe_pay

router = APIRouter(prefix="/api/payments", tags=["payments"])

PROVIDER = "stripe"


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


class StripeSettingsIn(BaseModel):
    secret_key: str | None = None
    webhook_secret: str | None = None


@router.get("/settings")
def get_settings(db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    return {"configured": secure_config.configured(cfg, ("secret_key",)),
            "has_webhook_secret": bool(secure_config.get_secret(cfg, "webhook_secret")),
            "fields": secure_config.public_view(cfg)}


@router.put("/settings")
def save_settings(body: StripeSettingsIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER))):
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    conn = secure_config.upsert_platform(db, PROVIDER, "Stripe", "Payments", payload)
    audit.record(db, action="stripe.configure", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="integration", target_id=str(conn.id),
                 ip=_ip(request), detail="stripe credentials")
    cfg = conn.config or {}
    return {"ok": True, "configured": secure_config.configured(cfg, ("secret_key",))}


@router.post("/invoices/{invoice_id}/checkout")
def create_checkout(invoice_id: int, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    if inv.status == InvoiceStatus.PAID:
        raise HTTPException(status.HTTP_409_CONFLICT, "Invoice is already paid")
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    secret = secure_config.get_secret(cfg, "secret_key")
    if not secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Stripe not configured — add your secret key in Settings → Payments.")
    base = _base_url(request)
    try:
        sess = stripe_pay.create_checkout(str(secret), inv,
                                          f"{base}/dashboard?paid={inv.id}", f"{base}/dashboard")
    except stripe_pay.StripeError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    audit.record(db, action="stripe.checkout", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="invoice", target_id=str(inv.id),
                 client_id=inv.client_id, ip=_ip(request), detail=sess.get("id") or "")
    return {"ok": True, "url": sess.get("url"), "session_id": sess.get("id")}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Public endpoint Stripe POSTs events to. The signature IS the auth."""
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    signing = secure_config.get_secret(cfg, "webhook_secret")
    if not signing:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Stripe webhook secret not configured")
    raw = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe_pay.verify_webhook(raw, sig, str(signing))
    except stripe_pay.StripeError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Webhook verification failed: {e}")

    etype = event.get("type")
    if etype in ("checkout.session.completed", "checkout.session.async_payment_succeeded",
                 "payment_intent.succeeded"):
        inv_id = stripe_pay.invoice_id_from_event(event)
        if inv_id:
            inv = db.get(Invoice, inv_id)
            if inv and inv.status != InvoiceStatus.PAID:
                inv.status = InvoiceStatus.PAID
                inv.paid_at = datetime.now(timezone.utc)
                db.commit()
                audit.record(db, action="stripe.invoice_paid", target_type="invoice",
                             target_id=str(inv.id), client_id=inv.client_id, ip=_ip(request),
                             detail=f"event={etype}")
                return {"ok": True, "invoice_paid": inv.id}
    return {"ok": True, "ignored": etype}
