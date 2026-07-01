"""v0.74 AI copilot — "Ask Pulse" + AI drafting, powered by Claude.

Staff-only. "Ask" answers natural-language questions using a compact, safe
snapshot of the business (aggregate counts — no secrets). Draft endpoints turn a
ticket / prompt into a polished reply, email, or advisory the operator can edit
and send. Everything degrades gracefully when Claude isn't connected.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import (
    Alert, Device, Role, SupportTicket, TicketComment, TicketStatus, User,
)
from ...services import ai

router = APIRouter(prefix="/api/ai", tags=["ai"])

_BRAND = ("You are Pulse Copilot, the built-in AI assistant for BVTech OpsPilot, "
          "an MSP/RMM platform. Be concise, practical, and friendly. Never invent "
          "client data — use only what's provided. Format with short paragraphs or "
          "bullets.")


@router.get("/status")
def ai_status(user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return {"enabled": ai.enabled()}


def _snapshot(db: Session) -> str:
    now = datetime.now(timezone.utc)
    lines = []
    try:
        from ...services import ar_aging
        aging = ar_aging.aging_report(db, now)
        lines.append(f"Accounts receivable: ${aging['total']:,.0f} outstanding, "
                     f"${aging['overdue_total']:,.0f} overdue across {aging['count']} invoices.")
    except Exception:
        pass
    try:
        opent = (db.query(SupportTicket)
                 .filter(SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS]))
                 .count())
        lines.append(f"Open tickets: {opent}.")
    except Exception:
        pass
    try:
        cutoff = now - timedelta(minutes=30)
        total = db.query(Device).count()
        offline = db.query(Device).filter((Device.last_checkin.is_(None)) |
                                          (Device.last_checkin < cutoff)).count()
        lines.append(f"Devices: {total} total, {offline} offline.")
    except Exception:
        pass
    try:
        from ...services import posture
        port = posture.portfolio(db)
        worst = [p for p in port if p.get("score") is not None][:3]
        if worst:
            lines.append("Security grades (riskiest): " +
                         ", ".join(f"{p['client_name']} {p['grade']}" for p in worst) + ".")
    except Exception:
        pass
    return "\n".join(lines) or "No business data available yet."


class AskIn(BaseModel):
    question: str


@router.post("/ask")
def ask(body: AskIn, db: Session = Depends(get_db),
        user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not ai.enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Claude isn't connected yet — add your Anthropic API key on the server.")
    q = (body.question or "").strip()
    if not q:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ask a question.")
    prompt = (f"Here is a live snapshot of the MSP's operations:\n\n{_snapshot(db)}\n\n"
              f"Operator question: {q}\n\n"
              "Answer using the snapshot where relevant. If the snapshot lacks the data, "
              "say what to check in the portal.")
    try:
        answer = ai.complete(_BRAND, prompt, max_tokens=800)
    except ai.AIError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    return {"answer": answer}


class DraftIn(BaseModel):
    kind: str = "email"          # email | reply | advisory | social
    prompt: str
    tone: str | None = None      # friendly | formal | urgent


@router.post("/draft")
def draft(body: DraftIn, db: Session = Depends(get_db),
          user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not ai.enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Claude isn't connected yet — add your Anthropic API key on the server.")
    if not (body.prompt or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give the assistant something to work with.")
    tone = f" Tone: {body.tone}." if body.tone else ""
    kinds = {
        "email": "Write a professional client email.",
        "reply": "Write a helpful support-ticket reply.",
        "advisory": "Write a short, plain-English security advisory for a small-business client.",
        "social": "Write a punchy, SEO-friendly social post (<= 1200 chars) for an MSP.",
    }
    instr = kinds.get(body.kind, kinds["email"])
    try:
        text = ai.complete(_BRAND, f"{instr}{tone}\n\nDetails:\n{body.prompt}", max_tokens=900)
    except ai.AIError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    return {"draft": text}


@router.post("/alerts/{alert_id}/explain")
def explain_alert(alert_id: int, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Plain-English cause + fix steps for an alert — senior-tech guidance on tap,
    so junior techs (and busy owners) resolve faster."""
    if not ai.enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Claude isn't connected yet — add your Anthropic API key on the server.")
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    dev = db.get(Device, a.device_id) if a.device_id else None
    ctx = (f"Alert type: {a.kind}\nSeverity: {a.severity.value if hasattr(a.severity,'value') else a.severity}\n"
           f"Message: {a.message}\nReading: {a.metric_value}\n")
    if dev:
        ctx += (f"Device: {dev.hostname} ({dev.os or 'unknown OS'}), "
                f"CPU {dev.cpu_pct}%, RAM {dev.ram_pct}%, disk {dev.disk_pct}%, "
                f"health {dev.health_score}, AV {dev.av_status}, patches pending {dev.patches_pending}.\n")
    prompt = ("Explain this RMM alert to a junior technician: what it most likely means, "
              "the top 2-3 likely causes, and clear step-by-step fix actions (Windows-first). "
              "Be specific and concise.\n\n" + ctx)
    try:
        text = ai.complete(_BRAND, prompt, max_tokens=700)
    except ai.AIError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    return {"alert_id": a.id, "kind": a.kind, "explanation": text}


@router.post("/tickets/{ticket_id}/reply-draft")
def ticket_reply_draft(ticket_id: int, db: Session = Depends(get_db),
                       user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Draft a suggested reply to a specific ticket from its thread."""
    if not ai.enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Claude isn't connected yet — add your Anthropic API key on the server.")
    t = db.get(SupportTicket, ticket_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    comments = (db.query(TicketComment)
                .filter(TicketComment.ticket_id == t.id, TicketComment.internal.is_(False))
                .order_by(TicketComment.created_at.asc()).all())
    thread = f"Subject: {t.subject}\nPriority: {t.priority.value if hasattr(t.priority,'value') else t.priority}\n\n"
    thread += f"Description: {t.body or '(none)'}\n\n"
    for c in comments[-10:]:
        thread += f"- {c.author_email}: {c.body}\n"
    prompt = ("Draft a friendly, professional reply to the customer for this support "
              "ticket. Acknowledge the issue, give clear next steps, and keep it short.\n\n"
              f"{thread}")
    try:
        text = ai.complete(_BRAND, prompt, max_tokens=700)
    except ai.AIError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    return {"draft": text}
