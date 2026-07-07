"""v1.11 Pulse Copilot — an agentic AI that queries the fleet AND acts on it.

The operator types plain English ("which clients are behind on patches?",
"approve critical patches for Acme", "how's Sugar Land Dental doing?"). Claude
runs a tool-use loop server-side against a governed toolset and returns a
narrated answer plus a log of everything it did.

Safety model:
  * READ tools run freely and are ALWAYS tenant/role-scoped to the calling user.
  * WRITE tools (approve patches, create ticket) only EXECUTE when the request
    carries allow_actions=True. Otherwise they return a dry-run description, so
    the UI can show "I can do X — confirm?" and re-run with actions enabled.
  * The loop is bounded (max steps) and every tool call is recorded.

This is the differentiator: a real agent over the whole platform, not a chatbot.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from ..core.deps import is_staff
from ..models import Client, SupportTicket, TicketStatus, User
from . import ai

MAX_STEPS = 6

_SYSTEM = (
    "You are Pulse Copilot, the AI operations assistant inside BVTech OpsPilot — "
    "an MSP/RMM platform. You help the operator run their managed-IT business by "
    "answering questions about the fleet and, when asked, taking governed actions. "
    "Use the provided tools to get real data; never invent numbers. Be concise and "
    "concrete — lead with the answer, then the key details. When you take an action, "
    "state exactly what happened. If an action is proposed but not yet permitted "
    "(dry run), tell the operator you can do it and to confirm. Amounts and counts "
    "must come from tools, not guesses."
)


# --------------------------------------------------------------------------- #
# Tool schemas advertised to Claude
# --------------------------------------------------------------------------- #
def _tool_defs(staff: bool) -> list[dict]:
    tools = [
        {"name": "site_health",
         "description": "Per-client health rollup: devices, online count, average health, open alerts, pending patches. Use for 'how is X doing' / 'which clients are at risk'.",
         "input_schema": {"type": "object", "properties": {}}},
        {"name": "find_client",
         "description": "Resolve a client by (partial) name to its id. Use before actions that need a client.",
         "input_schema": {"type": "object", "properties": {
             "name": {"type": "string", "description": "full or partial client name"}},
             "required": ["name"]}},
        {"name": "open_tickets",
         "description": "Count and list recent open/in-progress tickets, optionally for one client_id.",
         "input_schema": {"type": "object", "properties": {
             "client_id": {"type": "integer"}}}},
        {"name": "device_summary",
         "description": "Totals: device count, how many are offline, and how many have pending patches.",
         "input_schema": {"type": "object", "properties": {}}},
    ]
    if staff:
        tools += [
            {"name": "fleet_patch_status",
             "description": "Every device with pending Windows Updates across the fleet, worst-first, with counts and critical counts.",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "approve_patches_for_client",
             "description": "Approve & install pending Windows Updates for EVERY device of a client at/above a severity. This is an ACTION — only run when the operator has confirmed.",
             "input_schema": {"type": "object", "properties": {
                 "client_id": {"type": "integer"},
                 "min_severity": {"type": "string", "enum": ["critical", "important", "all"]}},
                 "required": ["client_id"]}},
            {"name": "create_ticket",
             "description": "Open a support ticket for a client. This is an ACTION — only run when confirmed.",
             "input_schema": {"type": "object", "properties": {
                 "client_id": {"type": "integer"},
                 "subject": {"type": "string"},
                 "body": {"type": "string"},
                 "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]}},
                 "required": ["client_id", "subject"]}},
        ]
    return tools


_WRITE_TOOLS = {"approve_patches_for_client", "create_ticket"}


# --------------------------------------------------------------------------- #
# Tool implementations — all scoped to the calling user
# --------------------------------------------------------------------------- #
def _run_tool(db: Session, user: User, name: str, args: dict, allow_actions: bool) -> dict:
    staff = is_staff(user)
    if name in _WRITE_TOOLS and not staff:
        return {"error": "Not permitted."}

    if name == "site_health":
        from . import proactive
        return {"sites": proactive.site_health(db, user)}

    if name == "fleet_patch_status":
        if not staff:
            return {"error": "Staff only."}
        from . import patching
        return patching.fleet(db)

    if name == "find_client":
        q = (args.get("name") or "").strip().lower()
        cq = db.query(Client)
        if not staff:
            cq = cq.filter(Client.id == user.client_id)
        matches = [c for c in cq.all() if q in c.name.lower()] if q else []
        return {"matches": [{"id": c.id, "name": c.name} for c in matches[:8]]}

    if name == "open_tickets":
        q = db.query(SupportTicket).filter(
            SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS]))
        if not staff:
            q = q.filter(SupportTicket.client_id == user.client_id)
        elif args.get("client_id"):
            q = q.filter(SupportTicket.client_id == args["client_id"])
        rows = q.order_by(SupportTicket.created_at.desc()).limit(15).all()
        return {"count": q.count(),
                "tickets": [{"id": t.id, "subject": t.subject, "priority": t.priority,
                             "client_id": t.client_id} for t in rows]}

    if name == "device_summary":
        from datetime import datetime, timedelta, timezone
        from ..models import Device
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=30)
        dq = db.query(Device)
        if not staff:
            dq = dq.filter(Device.client_id == user.client_id)
        devs = dq.all()
        offline = sum(1 for d in devs if not d.last_checkin or
                      (d.last_checkin.replace(tzinfo=timezone.utc) if d.last_checkin.tzinfo is None
                       else d.last_checkin) < cutoff)
        patch = sum(1 for d in devs if (d.patches_pending or 0) > 0)
        return {"devices": len(devs), "offline": offline, "devices_with_pending_patches": patch}

    if name == "approve_patches_for_client":
        cid = args.get("client_id")
        sev = args.get("min_severity") or "critical"
        client = db.get(Client, cid) if cid else None
        if not client:
            return {"error": "Unknown client_id — use find_client first."}
        if not allow_actions:
            return {"dry_run": True,
                    "would": f"approve {sev}+ patches for all of {client.name}'s devices",
                    "note": "Not executed — confirm to run."}
        from . import patching
        from ..models import Device
        made = []
        for dev in db.query(Device).filter(Device.client_id == cid,
                                           Device.patches_pending.isnot(None),
                                           Device.patches_pending > 0).all():
            if patching._has_open_job(db, dev.id):
                continue
            from ..models import DevicePatch
            patches = db.query(DevicePatch).filter(DevicePatch.device_id == dev.id).all()
            th = patching._MIN_CHOICES.get(sev, patching._MIN_CHOICES["critical"])
            matching = [p for p in patches if patching._sev_rank(p.severity) >= th]
            if not matching:
                continue
            kbs = sorted({p.kb for p in matching if p.kb}) or None
            dep = patching.approve_patches(db, dev, user, kbs=kbs,
                                           reason=f"Copilot: {sev}+ for {client.name}")
            made.append({"device_id": dev.id, "job_id": dep.id})
        return {"approved_devices": len(made), "jobs": made, "client": client.name}

    if name == "create_ticket":
        cid = args.get("client_id")
        client = db.get(Client, cid) if cid else None
        if not client:
            return {"error": "Unknown client_id — use find_client first."}
        if not allow_actions:
            return {"dry_run": True,
                    "would": f"open a {args.get('priority') or 'normal'} ticket for "
                             f"{client.name}: {args.get('subject')}",
                    "note": "Not executed — confirm to run."}
        from datetime import datetime, timezone
        from ..models import PRIORITIES
        from . import sla
        pr = args.get("priority") if args.get("priority") in PRIORITIES else "normal"
        t = SupportTicket(client_id=cid, subject=(args.get("subject") or "")[:200],
                          body=args.get("body") or "Opened via Pulse Copilot.",
                          priority=pr, created_at=datetime.now(timezone.utc),
                          created_by_user_id=user.id)
        sla.stamp_due_dates(db, t)
        db.add(t)
        db.commit()
        return {"ticket_id": t.id, "client": client.name, "priority": pr}

    return {"error": f"Unknown tool '{name}'."}


# --------------------------------------------------------------------------- #
# The agentic loop
# --------------------------------------------------------------------------- #
def run(db: Session, user: User, message: str, *, allow_actions: bool = False) -> dict:
    """Run the Copilot on one operator message. Returns
    {answer, actions, proposed_actions, tools_used}."""
    tools = _tool_defs(is_staff(user))
    messages = [{"role": "user", "content": message}]
    actions: list[dict] = []          # write tools actually executed
    proposed: list[dict] = []         # write tools that were dry-run
    tools_used: list[str] = []

    for _ in range(MAX_STEPS):
        resp = ai.messages_call(_SYSTEM, messages, tools, smart=True)
        blocks = resp.get("content") or []
        stop = resp.get("stop_reason")
        # Record assistant turn verbatim so tool_result can reference tool_use ids.
        messages.append({"role": "assistant", "content": blocks})

        tool_uses = [b for b in blocks if b.get("type") == "tool_use"]
        if stop != "tool_use" or not tool_uses:
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
            return {"answer": text or "(no answer)", "actions": actions,
                    "proposed_actions": proposed, "tools_used": tools_used}

        results = []
        for tu in tool_uses:
            name = tu.get("name")
            args = tu.get("input") or {}
            tools_used.append(name)
            out = _run_tool(db, user, name, args, allow_actions)
            if name in _WRITE_TOOLS:
                (actions if not out.get("dry_run") else proposed).append(
                    {"tool": name, "args": args, "result": out})
            results.append({"type": "tool_result", "tool_use_id": tu.get("id"),
                            "content": json.dumps(out)[:6000]})
        messages.append({"role": "user", "content": results})

    return {"answer": "I gathered a lot but couldn't wrap up — try a narrower question.",
            "actions": actions, "proposed_actions": proposed, "tools_used": tools_used}
