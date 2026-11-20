"""v2.0 Sales engine — deals (pipeline) + quotes (signable proposals).

The close flow our own HubSpot/PSA runs end-to-end:

    prospect (CRM contact) -> Deal -> Quote -> public e-sign accept
        -> Deal won -> Client created -> branded onboarding Invoice drafted

Stage/status are plain strings validated against models.DEAL_STAGES /
QUOTE_STATUSES. All money math lives here (recompute) so the API and UI never
trust client-sent totals. Pure functions where possible; the few that mutate
take a Session and flush but leave the final commit to the caller/route.
"""
from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import (
    Client, CrmContact, Deal, Invoice, InvoiceLineItem, InvoiceStatus,
    DEAL_STAGES, QUOTE_STATUSES, Quote,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _money(x) -> float:
    try:
        return round(float(x or 0), 2)
    except (TypeError, ValueError):
        return 0.0


# --------------------------------------------------------------------------- #
# Line items + totals
# --------------------------------------------------------------------------- #
def clean_line_items(items) -> list[dict]:
    """Normalise a client-sent line_items list into trusted dicts. Each row:
    {description, quantity, unit_price, amount, recurring}. amount is always
    recomputed server-side (never trusted from the client)."""
    out: list[dict] = []
    for raw in (items or []):
        if not isinstance(raw, dict):
            continue
        desc = str(raw.get("description") or "").strip()[:300]
        if not desc:
            continue
        qty = _money(raw.get("quantity") if raw.get("quantity") is not None else 1)
        unit = _money(raw.get("unit_price"))
        out.append({
            "description": desc,
            "quantity": qty,
            "unit_price": unit,
            "amount": _money(qty * unit),
            "recurring": bool(raw.get("recurring")),
        })
    return out


def recompute(quote: Quote) -> Quote:
    """Set subtotal/tax_amount/total from line_items + onboarding_fee in place."""
    items = quote.line_items or []
    line_total = sum(_money(i.get("amount")) for i in items)
    sub = _money(line_total + _money(quote.onboarding_fee))
    quote.subtotal = sub
    quote.tax_amount = _money(sub * _money(quote.tax_rate) / 100.0)
    quote.total = _money(sub + quote.tax_amount)
    return quote


def _one_time_items(quote: Quote) -> list[dict]:
    """The non-recurring charges (setup/hardware/project) — what the onboarding
    invoice bills. Recurring (MRR) rows become the ongoing contract, billed
    separately once QuickBooks/recurring billing is turned on."""
    return [i for i in (quote.line_items or []) if not i.get("recurring")]


def mrr(quote: Quote) -> float:
    """Monthly recurring revenue = sum of recurring line items."""
    return _money(sum(_money(i.get("amount")) for i in (quote.line_items or [])
                      if i.get("recurring")))


# --------------------------------------------------------------------------- #
# Deals
# --------------------------------------------------------------------------- #
def create_deal(db: Session, *, title: str, contact_id: int | None = None,
                value: float = 0.0, stage: str = "new", probability: int | None = None,
                source: str | None = None, notes: str | None = None,
                expected_close: date | None = None, user_id: int | None = None) -> Deal:
    stage = stage if stage in DEAL_STAGES else "new"
    d = Deal(title=(title or "Untitled deal").strip()[:200],
             contact_id=contact_id, value=_money(value), stage=stage,
             probability=_stage_probability(stage) if probability is None else max(0, min(100, probability)),
             source=source, notes=notes, expected_close=expected_close,
             owner_user_id=user_id, created_by_user_id=user_id)
    db.add(d)
    db.flush()
    return d


def _stage_probability(stage: str) -> int:
    return {"new": 10, "qualified": 35, "quote": 60, "won": 100, "lost": 0}.get(stage, 10)


def move_stage(db: Session, deal: Deal, stage: str, *, lost_reason: str | None = None) -> Deal:
    if stage not in DEAL_STAGES:
        raise ValueError(f"invalid stage {stage!r}")
    deal.stage = stage
    deal.probability = _stage_probability(stage)
    now = _utcnow()
    if stage == "won" and not deal.won_at:
        deal.won_at = now
    if stage == "lost":
        deal.lost_at = now
        if lost_reason:
            deal.lost_reason = lost_reason[:200]
    deal.updated_at = now
    db.flush()
    return deal


# --------------------------------------------------------------------------- #
# Quotes
# --------------------------------------------------------------------------- #
def next_quote_number(db: Session) -> str:
    last = db.query(Quote).order_by(Quote.id.desc()).first()
    n = (last.id + 1) if last else 1
    return f"QUO-{n:05d}"


def create_quote(db: Session, deal: Deal, *, title: str | None = None,
                 line_items=None, onboarding_fee: float = 0.0, tax_rate: float = 0.0,
                 notes: str | None = None, valid_days: int = 30,
                 user_id: int | None = None) -> Quote:
    q = Quote(deal_id=deal.id, title=(title or deal.title)[:200], status="draft",
              line_items=clean_line_items(line_items), onboarding_fee=_money(onboarding_fee),
              tax_rate=_money(tax_rate), notes=notes,
              valid_until=date.today() + timedelta(days=max(1, valid_days)),
              created_by_user_id=user_id)
    recompute(q)
    db.add(q)
    db.flush()
    q.number = next_quote_number_for(q.id)
    db.flush()
    return q


def next_quote_number_for(quote_id: int) -> str:
    return f"QUO-{quote_id:05d}"


def update_quote(db: Session, quote: Quote, *, title=None, line_items=None,
                 onboarding_fee=None, tax_rate=None, notes=None, valid_until=None) -> Quote:
    if quote.status in ("accepted", "declined"):
        raise ValueError("a finalised quote can no longer be edited")
    if title is not None:
        quote.title = str(title)[:200]
    if line_items is not None:
        quote.line_items = clean_line_items(line_items)
    if onboarding_fee is not None:
        quote.onboarding_fee = _money(onboarding_fee)
    if tax_rate is not None:
        quote.tax_rate = _money(tax_rate)
    if notes is not None:
        quote.notes = notes
    if valid_until is not None:
        quote.valid_until = valid_until
    recompute(quote)
    quote.updated_at = _utcnow()
    db.flush()
    return quote


def send_quote(db: Session, quote: Quote) -> Quote:
    """Mark a quote as sent and mint its public accept token. Idempotent on the
    token (keeps the same link if re-sent). Advances the deal to the 'quote' stage."""
    if not quote.public_token:
        quote.public_token = secrets.token_urlsafe(24)
    quote.status = "sent"
    quote.sent_at = _utcnow()
    quote.updated_at = quote.sent_at
    deal = db.get(Deal, quote.deal_id)
    if deal and deal.stage in ("new", "qualified"):
        move_stage(db, deal, "quote")
    db.flush()
    return quote


def _ensure_client_for_deal(db: Session, deal: Deal) -> Client:
    """Find or create the managed Client for a won deal, from its CRM contact."""
    if deal.client_id:
        c = db.get(Client, deal.client_id)
        if c:
            return c
    contact = db.get(CrmContact, deal.contact_id) if deal.contact_id else None
    if contact and contact.client_id:
        existing = db.get(Client, contact.client_id)
        if existing:
            deal.client_id = existing.id
            return existing
    name = ((contact.company if contact and contact.company else None)
            or (contact.name if contact else None) or deal.title or "New Client")
    client = Client(
        name=str(name)[:200],
        primary_contact=(contact.name if contact else None),
        email=(contact.email if contact else None),
        phone=(contact.phone if contact else None),
        site_address=(contact.address if contact else None),
        notes=f"Converted from deal #{deal.id} ({deal.title}).",
        is_active=True,
    )
    db.add(client)
    db.flush()
    deal.client_id = client.id
    if contact and not contact.client_id:
        contact.client_id = client.id
        contact.status = "won"
    return client


def _draft_onboarding_invoice(db: Session, deal: Deal, quote: Quote, client: Client) -> Invoice | None:
    """Draft (not sent) the one-time onboarding invoice: the editable onboarding
    fee plus any non-recurring line items. Left as DRAFT so the owner reviews/sends
    it (or exports to QuickBooks). Recurring MRR is NOT auto-invoiced here."""
    one_time = _one_time_items(quote)
    fee = _money(quote.onboarding_fee)
    if fee <= 0 and not one_time:
        return None
    now = _utcnow()
    inv = Invoice(client_id=client.id, status=InvoiceStatus.DRAFT, currency=quote.currency,
                  tax_rate=_money(quote.tax_rate), issued_at=now,
                  due_at=now + timedelta(days=15),
                  notes=f"Onboarding — accepted quote {quote.number or quote.id} "
                        f"(deal #{deal.id}: {deal.title}).")
    db.add(inv)
    db.flush()
    inv.number = f"INV-{inv.id:05d}"
    sub = 0.0
    if fee > 0:
        db.add(InvoiceLineItem(invoice_id=inv.id, description="One-time onboarding fee",
                               quantity=1, unit_price=fee, amount=fee, source="manual"))
        sub += fee
    for it in one_time:
        amt = _money(it.get("amount"))
        db.add(InvoiceLineItem(invoice_id=inv.id, description=it.get("description", "Item")[:300],
                               quantity=_money(it.get("quantity")) or 1,
                               unit_price=_money(it.get("unit_price")), amount=amt, source="manual"))
        sub += amt
    inv.subtotal = _money(sub)
    inv.tax_amount = _money(inv.subtotal * inv.tax_rate / 100.0)
    inv.total = _money(inv.subtotal + inv.tax_amount)
    db.flush()
    return inv


def accept_quote(db: Session, quote: Quote, *, name: str, title: str | None = None,
                 ip: str | None = None) -> dict:
    """Accept (e-sign) a quote. Idempotent: a second accept is a no-op that returns
    the existing result. Converts the deal to won, creates/links the Client, and
    drafts the onboarding invoice. Commits."""
    if quote.status == "accepted":
        return _accept_result(db, quote, already=True)
    if quote.status == "declined":
        raise ValueError("this quote was declined")
    now = _utcnow()
    quote.status = "accepted"
    quote.accepted_at = now
    quote.accepted_name = (name or "").strip()[:200] or "Signer"
    quote.accepted_title = (title or "").strip()[:160] or None
    quote.accepted_ip = (ip or "")[:64] or None
    quote.updated_at = now
    deal = db.get(Deal, quote.deal_id)
    client = None
    if deal:
        move_stage(db, deal, "won")
        if not deal.value:
            deal.value = mrr(quote) or quote.total
        client = _ensure_client_for_deal(db, deal)
        inv = _draft_onboarding_invoice(db, deal, quote, client)
        if inv:
            quote.onboarding_invoice_id = inv.id
    db.flush()
    db.commit()
    return _accept_result(db, quote, already=False)


def _accept_result(db: Session, quote: Quote, *, already: bool) -> dict:
    deal = db.get(Deal, quote.deal_id)
    return {
        "ok": True, "already_accepted": already,
        "quote_id": quote.id, "number": quote.number, "status": quote.status,
        "accepted_name": quote.accepted_name, "accepted_at": _iso(quote.accepted_at),
        "deal_id": quote.deal_id, "deal_stage": deal.stage if deal else None,
        "client_id": deal.client_id if deal else None,
        "onboarding_invoice_id": quote.onboarding_invoice_id,
        "mrr": mrr(quote),
    }


def decline_quote(db: Session, quote: Quote, *, reason: str | None = None) -> Quote:
    if quote.status == "accepted":
        raise ValueError("this quote was already accepted")
    now = _utcnow()
    quote.status = "declined"
    quote.declined_at = now
    quote.updated_at = now
    if reason:
        quote.notes = ((quote.notes or "") + f"\n[Declined] {reason[:280]}").strip()
    db.flush()
    return quote


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #
def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def deal_dict(db: Session, deal: Deal, *, with_quotes: bool = False) -> dict:
    contact = db.get(CrmContact, deal.contact_id) if deal.contact_id else None
    out = {
        "id": deal.id, "title": deal.title, "stage": deal.stage,
        "value": deal.value, "probability": deal.probability,
        "contact_id": deal.contact_id,
        "contact_name": (contact.name if contact else None),
        "contact_company": (contact.company if contact else None),
        "contact_email": (contact.email if contact else None),
        "client_id": deal.client_id, "source": deal.source,
        "lost_reason": deal.lost_reason, "notes": deal.notes,
        "expected_close": _iso(deal.expected_close),
        "created_at": _iso(deal.created_at), "updated_at": _iso(deal.updated_at),
        "won_at": _iso(deal.won_at),
    }
    if with_quotes:
        qs = db.query(Quote).filter(Quote.deal_id == deal.id).order_by(Quote.id.desc()).all()
        out["quotes"] = [quote_dict(q) for q in qs]
    return out


def quote_dict(quote: Quote) -> dict:
    return {
        "id": quote.id, "deal_id": quote.deal_id, "number": quote.number,
        "title": quote.title, "status": quote.status, "currency": quote.currency,
        "line_items": quote.line_items or [], "onboarding_fee": quote.onboarding_fee,
        "subtotal": quote.subtotal, "tax_rate": quote.tax_rate,
        "tax_amount": quote.tax_amount, "total": quote.total, "mrr": mrr(quote),
        "notes": quote.notes, "valid_until": _iso(quote.valid_until),
        "public_token": quote.public_token,
        "sent_at": _iso(quote.sent_at), "viewed_at": _iso(quote.viewed_at),
        "accepted_at": _iso(quote.accepted_at), "accepted_name": quote.accepted_name,
        "accepted_title": quote.accepted_title, "accepted_ip": quote.accepted_ip,
        "declined_at": _iso(quote.declined_at),
        "onboarding_invoice_id": quote.onboarding_invoice_id,
        "created_at": _iso(quote.created_at), "updated_at": _iso(quote.updated_at),
    }


def public_quote_dict(db: Session, quote: Quote) -> dict:
    """What the prospect sees on the public accept page — no internal deal data,
    owner notes, or IP/token leakage beyond their own."""
    deal = db.get(Deal, quote.deal_id)
    contact = db.get(CrmContact, deal.contact_id) if deal and deal.contact_id else None
    return {
        "number": quote.number, "title": quote.title, "status": quote.status,
        "currency": quote.currency, "line_items": quote.line_items or [],
        "onboarding_fee": quote.onboarding_fee, "subtotal": quote.subtotal,
        "tax_rate": quote.tax_rate, "tax_amount": quote.tax_amount,
        "total": quote.total, "mrr": mrr(quote), "notes": quote.notes,
        "valid_until": _iso(quote.valid_until),
        "to_name": (contact.name if contact else None),
        "to_company": (contact.company if contact else None),
        "accepted_at": _iso(quote.accepted_at), "accepted_name": quote.accepted_name,
    }


def pipeline_board(db: Session) -> dict:
    """Kanban board: deals grouped by stage with per-stage totals + weighted value."""
    deals = db.query(Deal).order_by(Deal.updated_at.desc()).all()
    cols = {s: {"stage": s, "deals": [], "count": 0, "value": 0.0} for s in DEAL_STAGES}
    weighted = 0.0
    open_value = 0.0
    for d in deals:
        col = cols.get(d.stage) or cols["new"]
        col["deals"].append(deal_dict(db, d))
        col["count"] += 1
        col["value"] = _money(col["value"] + d.value)
        if d.stage not in ("won", "lost"):
            weighted = _money(weighted + d.value * (d.probability / 100.0))
            open_value = _money(open_value + d.value)
    won = cols["won"]
    return {
        "stages": list(DEAL_STAGES),
        "columns": [cols[s] for s in DEAL_STAGES],
        "totals": {"open_value": open_value, "weighted_value": weighted,
                   "won_value": won["value"], "won_count": won["count"],
                   "total_deals": len(deals)},
    }
