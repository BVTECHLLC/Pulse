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
        {"name": "device_history",
         "description": "Recent health for one device: latest metrics + its open alerts. Use find_client/fleet first to get a device_id.",
         "input_schema": {"type": "object", "properties": {
             "device_id": {"type": "integer"}}, "required": ["device_id"]}},
        {"name": "security_posture",
         "description": "Security grade + open findings per client (worst-first). Optionally one client_id.",
         "input_schema": {"type": "object", "properties": {
             "client_id": {"type": "integer"}}}},
        {"name": "client_report",
         "description": "The full QBR-style summary for one client: devices, patch %, security grade, tickets/SLA, service hours, MRR. Use for 'how is X doing overall' / renewal prep.",
         "input_schema": {"type": "object", "properties": {
             "client_id": {"type": "integer"}}, "required": ["client_id"]}},
        {"name": "predicted_issues",
         "description": "PREDICTED problems from trend + anomaly analysis of device telemetry (disk full soon, health declining, resource spikes) — before they become hard alerts.",
         "input_schema": {"type": "object", "properties": {}}},
    ]
    if staff:
        tools += [
            {"name": "fleet_patch_status",
             "description": "Every device with pending Windows Updates across the fleet, worst-first, with counts and critical counts.",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "financials",
             "description": "Money view: total MRR/ARR and accounts-receivable (outstanding + overdue).",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "sla_radar",
             "description": "PREDICTED SLA breaches: open tickets that are breached or about to breach within N hours, ranked most-urgent first. Use for 'which tickets are about to breach?' / 'what needs attention right now?'.",
             "input_schema": {"type": "object", "properties": {
                 "horizon_hours": {"type": "integer", "description": "look-ahead window (default 8)"}}}},
            {"name": "contract_margin",
             "description": "Per-contract economics: contracted MRR vs the cost of service actually delivered, margin %, effective realized hourly rate, and renewal window. Flags money-losing (underwater) contracts and upcoming renewals. Use for 'which contracts are underwater?' / 'what's up for renewal?' / renewal pricing.",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "revenue_leakage",
             "description": "Money earned but not billed: unbilled billable time, contracts overdue to be invoiced, and resolved tickets with no time captured. Use for 'what am I not billing?' / 'find revenue leakage'.",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "draft_client_email",
             "description": "Write a professional client email draft (returns text; does NOT send). Good for 'draft an email to X about Y'.",
             "input_schema": {"type": "object", "properties": {
                 "client_id": {"type": "integer"}, "about": {"type": "string"},
                 "tone": {"type": "string"}}, "required": ["about"]}},
            {"name": "create_maintenance_window",
             "description": "Schedule a maintenance window (suppresses alerts + lets auto-patch run). ACTION — only run when confirmed.",
             "input_schema": {"type": "object", "properties": {
                 "client_id": {"type": "integer"}, "device_id": {"type": "integer"},
                 "starts_in_hours": {"type": "number"}, "duration_hours": {"type": "number"},
                 "reason": {"type": "string"}}, "required": ["client_id"]}},
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


_WRITE_TOOLS = {"approve_patches_for_client", "create_ticket", "create_maintenance_window"}


# --------------------------------------------------------------------------- #
# Tool implementations — all scoped to the calling user
# --------------------------------------------------------------------------- #
def _run_tool(db: Session, user: User, name: str, args: dict, allow_actions: bool,
              client_scope: int | None = None) -> dict:
    staff = is_staff(user)
    if name in _WRITE_TOOLS and not staff:
        return {"error": "Not permitted."}

    def _cid(explicit):
        """Resolve the client filter for a tool. When this agent is pinned to a
        single client (a fleet-sweep sub-agent), that scope wins over everything;
        otherwise non-staff are pinned to their own client, staff use the arg."""
        if client_scope is not None:
            return client_scope
        if not staff:
            return user.client_id
        return explicit

    if name == "site_health":
        from . import proactive
        sites = proactive.site_health(db, user)
        if client_scope is not None:
            sites = [s for s in sites if s.get("client_id") == client_scope]
        return {"sites": sites}

    if name == "fleet_patch_status":
        if not staff:
            return {"error": "Staff only."}
        from . import patching
        fl = patching.fleet(db)
        if client_scope is not None:
            devs = [d for d in fl.get("devices", []) if d.get("client_id") == client_scope]
            crit = sum(d.get("critical", 0) for d in devs)
            fl = {"devices": devs,
                  "totals": {"devices": len(devs),
                             "pending": sum(d.get("pending", 0) for d in devs),
                             "critical": crit}}
        return fl

    if name == "find_client":
        q = (args.get("name") or "").strip().lower()
        cq = db.query(Client)
        if client_scope is not None:
            cq = cq.filter(Client.id == client_scope)
        elif not staff:
            cq = cq.filter(Client.id == user.client_id)
        pool = cq.all()
        matches = [c for c in pool if q in c.name.lower()] if q else pool[:8]
        return {"matches": [{"id": c.id, "name": c.name} for c in matches[:8]]}

    if name == "open_tickets":
        q = db.query(SupportTicket).filter(
            SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS]))
        cid = _cid(args.get("client_id"))
        if cid:
            q = q.filter(SupportTicket.client_id == cid)
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
        cid = _cid(None)
        if cid:
            dq = dq.filter(Device.client_id == cid)
        devs = dq.all()
        offline = sum(1 for d in devs if not d.last_checkin or
                      (d.last_checkin.replace(tzinfo=timezone.utc) if d.last_checkin.tzinfo is None
                       else d.last_checkin) < cutoff)
        patch = sum(1 for d in devs if (d.patches_pending or 0) > 0)
        return {"devices": len(devs), "offline": offline, "devices_with_pending_patches": patch}

    if name == "predicted_issues":
        from . import foresight
        if client_scope is not None:
            cids = [client_scope]
        else:
            cids = None if staff else [user.client_id]
        risks = foresight.fleet_risks(db, cids)
        risks.sort(key=lambda r: {"critical":3,"high":2,"medium":1}.get(r.get("severity"),0), reverse=True)
        return {"predicted": [{"hostname": r["hostname"], "severity": r["severity"],
                               "kind": r["kind"], "detail": r["detail"]} for r in risks[:15]],
                "count": len(risks)}

    if name == "device_history":
        from datetime import datetime, timezone
        from ..models import Alert, AlertStatus, Device, DeviceCheckin
        dev = db.get(Device, args.get("device_id"))
        if client_scope is not None:
            ok = dev and dev.client_id == client_scope
        else:
            ok = dev and (staff or dev.client_id == user.client_id)
        if not ok:
            return {"error": "Device not found or not permitted."}
        recent = (db.query(DeviceCheckin).filter(DeviceCheckin.device_id == dev.id)
                  .order_by(DeviceCheckin.ts.desc()).limit(10).all())
        alerts = (db.query(Alert).filter(Alert.device_id == dev.id,
                                         Alert.status != AlertStatus.RESOLVED).all())
        return {"hostname": dev.hostname, "health_score": dev.health_score,
                "cpu_pct": dev.cpu_pct, "ram_pct": dev.ram_pct, "disk_pct": dev.disk_pct,
                "patches_pending": dev.patches_pending or 0, "av_status": dev.av_status,
                "open_alerts": [{"kind": a.kind, "severity": a.severity.value,
                                 "message": a.message} for a in alerts],
                "recent_health": [c.health_score for c in reversed(recent)]}

    if name in ("sla_radar", "contract_margin", "revenue_leakage"):
        if not staff:
            return {"error": "Staff only."}
        from . import psa_intel
        cids = [client_scope] if client_scope is not None else None
        if name == "sla_radar":
            hz = int(args.get("horizon_hours") or 8)
            r = psa_intel.sla_radar(db, horizon_hours=max(1, min(72, hz)), client_ids=cids)
            return {"counts": r["counts"], "at_risk": r["at_risk"][:20]}
        if name == "contract_margin":
            r = psa_intel.contract_intel(db, client_ids=cids)
            return {"totals": r["totals"],
                    "contracts": [c for c in r["contracts"] if c["flags"]][:20] or r["contracts"][:20]}
        r = psa_intel.revenue_leakage(db, client_ids=cids)
        return {"total_recoverable": r["total_recoverable"],
                "unbilled_time": r["unbilled_time"], "due_contracts": r["due_contracts"],
                "untracked_tickets": {"count": r["untracked_tickets"]["count"]}}

    if name == "security_posture":
        from . import posture
        port = posture.portfolio(db)
        cid = _cid(args.get("client_id"))
        if cid:
            port = [p for p in port if p.get("client_id") == cid]
        return {"clients": [{"client": p.get("client_name"), "grade": p.get("grade"),
                             "score": p.get("score"), "open_findings": p.get("open_findings")}
                            for p in port]}

    if name == "client_report":
        cid = _cid(args.get("client_id"))
        if not staff and cid != user.client_id:
            return {"error": "Not permitted."}
        client = db.get(Client, cid)
        if not client:
            return {"error": "Unknown client_id."}
        from datetime import datetime, timezone
        from ..api.routes.reports import _build_summary
        sm = _build_summary(db, client, datetime.now(timezone.utc))
        return {"client": client.name, "devices": sm["devices"], "patch": sm["patch"],
                "security_grade": sm.get("posture", {}).get("grade"),
                "tickets": sm["tickets"], "service_hours_90d": sm["service"]["hours_90d"],
                "mrr": sm["revenue"]["mrr"], "training": sm.get("training", {})}

    if name == "financials":
        if not staff:
            return {"error": "Staff only."}
        out = {}
        try:
            from ..api.routes.billing import _summary as _bill  # may not exist
        except Exception:  # noqa: BLE001
            _bill = None
        try:
            from . import ar_aging
            from datetime import datetime, timezone
            ag = ar_aging.aging_report(db, datetime.now(timezone.utc))
            out["ar_outstanding"] = ag.get("total")
            out["ar_overdue"] = ag.get("overdue_total")
        except Exception:  # noqa: BLE001
            pass
        try:
            from ..models import Contract, License
            from ..api.routes.contracts import monthly_value
            mrr = sum(monthly_value(c) for c in db.query(Contract).filter(Contract.status == "active").all())
            mrr += sum((l.monthly_cost or 0.0) for l in db.query(License).all())
            out["mrr"] = round(mrr, 2)
            out["arr"] = round(mrr * 12, 2)
        except Exception:  # noqa: BLE001
            pass
        return out

    if name == "draft_client_email":
        if not staff:
            return {"error": "Staff only."}
        _dc = _cid(args.get("client_id"))
        client = db.get(Client, _dc) if _dc else None
        who = client.name if client else "the client"
        prompt = (f"Write a short, professional email from BVTech (a managed IT provider) "
                  f"to {who} about: {args.get('about')}. Tone: {args.get('tone') or 'friendly, clear'}. "
                  f"No placeholders; ready to send.")
        try:
            draft = ai.complete("You write concise, professional MSP client emails.", prompt, max_tokens=500)
        except ai.AIError as e:
            return {"error": str(e)}
        return {"draft": draft, "client": who, "note": "Draft only — review and send yourself."}

    if name == "create_maintenance_window":
        cid = _cid(args.get("client_id"))
        client = db.get(Client, cid) if cid else None
        if not client:
            return {"error": "Unknown client_id — use find_client first."}
        from datetime import datetime, timedelta, timezone
        start = datetime.now(timezone.utc) + timedelta(hours=float(args.get("starts_in_hours") or 0))
        end = start + timedelta(hours=float(args.get("duration_hours") or 2))
        if not allow_actions:
            return {"dry_run": True,
                    "would": f"open a maintenance window for {client.name} "
                             f"from {start:%b %d %H:%M} for "
                             f"{args.get('duration_hours') or 2}h",
                    "note": "Not executed — confirm to run."}
        from ..models import MaintenanceWindow
        did = args.get("device_id")
        if did:
            from ..models import Device as _Dev
            d = db.get(_Dev, did)
            if not d or d.client_id != cid:
                return {"error": "device not in this client"}
        w = MaintenanceWindow(client_id=cid, device_id=did, starts_at=start, ends_at=end,
                              reason=(args.get("reason") or "Scheduled via Pulse Copilot"),
                              created_by_user_id=user.id)
        db.add(w)
        db.commit()
        return {"window_id": w.id, "client": client.name,
                "starts_at": start.isoformat(), "ends_at": end.isoformat()}

    if name == "approve_patches_for_client":
        cid = _cid(args.get("client_id"))
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
        cid = _cid(args.get("client_id"))
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
def run(db: Session, user: User, message: str, *, allow_actions: bool = False,
        client_scope: int | None = None) -> dict:
    """Run the Copilot on one operator message. Returns
    {answer, actions, proposed_actions, tools_used}.

    When `client_scope` is set, every tool is pinned to that single client — this
    is how a fleet-sweep sub-agent (copilot_fleet) analyses one client in isolation
    even though the operator is staff with fleet-wide reach."""
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
            out = _run_tool(db, user, name, args, allow_actions, client_scope)
            if name in _WRITE_TOOLS:
                (actions if not out.get("dry_run") else proposed).append(
                    {"tool": name, "args": args, "result": out})
            results.append({"type": "tool_result", "tool_use_id": tu.get("id"),
                            "content": json.dumps(out)[:6000]})
        messages.append({"role": "user", "content": results})

    return {"answer": "I gathered a lot but couldn't wrap up — try a narrower question.",
            "actions": actions, "proposed_actions": proposed, "tools_used": tools_used}
