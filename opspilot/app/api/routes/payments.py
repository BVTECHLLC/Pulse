"""v0.57 Payments — Stripe Checkout for invoices + auto-reconcile webhook."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import current_user, is_staff, require_roles
from ...models import Invoice, InvoiceStatus, Role, User
from ...services import audit, billing_payments, payment_methods, secure_config, stripe_pay

router = APIRouter(prefix="/api/payments", tags=["payments"])

PROVIDER = "stripe"
METHODS_PROVIDER = "payment_methods"


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


# --------------------------------------------------------------------------- #
# Multi-method payments (v0.59): PayPal, Venmo, Cash App, Zelle, bank wire,
# check, QuickBooks, custom — configured once, rendered on every invoice.
# --------------------------------------------------------------------------- #
class PaymentMethodsIn(BaseModel):
    # All fields optional; only the ones submitted are updated (partial save).
    # Mirrors payment_methods.ALL_FIELDS — kept as a free dict so adding a field
    # to the service needs no change here.
    fields: dict = {}


@router.get("/methods/settings")
def get_methods_settings(db: Session = Depends(get_db),
                         user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    conn = secure_config.get_platform(db, METHODS_PROVIDER)
    cfg = (conn.config if conn else None) or {}
    return {"fields": secure_config.public_view(cfg),
            "all_fields": payment_methods.ALL_FIELDS,
            "enabled": payment_methods.enabled_methods(cfg),
            "catalog": {k: {"label": v["label"], "emoji": v["emoji"], "fields": v["fields"]}
                        for k, v in payment_methods.METHODS.items()}}


@router.put("/methods/settings")
def save_methods_settings(body: PaymentMethodsIn, request: Request,
                          db: Session = Depends(get_db),
                          user: User = Depends(require_roles(Role.OWNER))):
    # Accept only known fields; trim to str so the vault stays clean.
    allowed = set(payment_methods.ALL_FIELDS)
    payload = {k: ("" if v is None else str(v).strip())
               for k, v in (body.fields or {}).items() if k in allowed}
    conn = secure_config.upsert_platform(db, METHODS_PROVIDER, "Payment Methods",
                                         "Payments", payload)
    audit.record(db, action="payment_methods.configure", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value,
                 target_type="integration", target_id=str(conn.id), ip=_ip(request),
                 detail="payment methods")
    cfg = conn.config or {}
    return {"ok": True, "enabled": payment_methods.enabled_methods(cfg)}


@router.get("/invoices/{invoice_id}/options")
def invoice_pay_options(invoice_id: int, db: Session = Depends(get_db),
                        user: User = Depends(current_user)):
    """Every way THIS invoice can be paid — used by the client-facing invoice page.
    Scoped exactly like GET /invoices/{id}: a client sees only their own, and
    never a draft."""
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    if not is_staff(user):
        if inv.client_id != user.client_id or inv.status == InvoiceStatus.DRAFT:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")

    amount_paid = billing_payments.amount_paid(db, inv.id)
    bal = billing_payments.balance(inv, amount_paid)
    paid = inv.status == InvoiceStatus.PAID or bal <= 0
    # Pay links bill the REMAINING balance (partial payments shrink it).
    ctx = {"id": inv.id, "number": inv.number, "total": bal, "currency": inv.currency}

    # Stripe (card) shows as a checkout button when the secret key is present.
    stripe_conn = secure_config.get_platform(db, PROVIDER)
    stripe_cfg = (stripe_conn.config if stripe_conn else None) or {}
    stripe_on = secure_config.configured(stripe_cfg, ("secret_key",))

    mconn = secure_config.get_platform(db, METHODS_PROVIDER)
    mcfg = (mconn.config if mconn else None) or {}
    options = [] if paid else payment_methods.pay_options(mcfg, ctx)

    return {"invoice_id": inv.id, "number": inv.number, "total": inv.total,
            "amount_paid": round(amount_paid, 2), "balance": round(max(bal, 0.0), 2),
            "currency": inv.currency, "status": inv.status.value, "paid": paid,
            "stripe": stripe_on and not paid,
            "note": (mcfg.get("methods_note") or "").strip(), "options": options}


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
    bal = billing_payments.balance(inv, billing_payments.amount_paid(db, inv.id))
    if bal <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Invoice has no remaining balance")
    base = _base_url(request)
    try:
        sess = stripe_pay.create_checkout(str(secret), inv,
                                          f"{base}/dashboard?paid={inv.id}", f"{base}/dashboard",
                                          amount=bal)
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
            if inv and inv.status != InvoiceStatus.VOID:
                # Record the card payment (idempotent on the Stripe object id) and
                # let the ledger reconcile the invoice to paid.
                obj = (event.get("data") or {}).get("object") or {}
                ref = obj.get("id") or obj.get("payment_intent")
                amt = obj.get("amount_total")
                amount = round(amt / 100.0, 2) if isinstance(amt, (int, float)) else None
                res = billing_payments.reconcile_from_external(db, inv, amount, "card", ref)
                audit.record(db, action="stripe.invoice_paid", target_type="invoice",
                             target_id=str(inv.id), client_id=inv.client_id, ip=_ip(request),
                             detail=f"event={etype} balance={(res or {}).get('balance')}")
                return {"ok": True, "invoice_paid": inv.id, "reconciled": bool(res)}
    return {"ok": True, "ignored": etype}
