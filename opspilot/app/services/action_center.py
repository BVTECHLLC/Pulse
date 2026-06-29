"""v0.32 Action Center — the "what needs attention right now" brain.

This is the single pane of glass that turns every signal we collect (RMM health,
alerts, SLAs, security findings, warranties, contracts, revenue leak, overdue
work) into ONE ranked, explainable, deep-linkable list of actions. Each item
carries a 0-100 priority score and a plain-English reason, so a tech opening
Pulse sees exactly what to do next across the whole book of business — not a
dozen dashboards they have to triage by hand.

Pure read model: it computes from existing tables and never mutates anything.
Tenant-scoped: staff see every client (optionally filtered to one); a client
user only ever sees their own org.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import (
    Alert, AlertStatus, AlertSeverity, Asset, Client, Contract, Device,
    FindingSeverity, FindingStatus, Project, ProjectStatus, ProjectTask,
    SecurityFinding, SupportTicket, TicketStatus, TimeEntry, User,
)
from . import sla

# Severity → base score. Age and type nuance adjust within these bands.
_BASE = {"critical": 88, "high": 68, "medium": 44, "low": 20}
# ops_score penalty weight per open item severity.
_PENALTY = {"critical": 12.0, "high": 6.0, "medium": 2.0, "low": 0.6}

# Thresholds (kept here so the whole policy is readable in one place).
OFFLINE_MINUTES = 30          # a device silent longer than this is "offline"
LOW_HEALTH = 60               # health_score below this needs a look
PATCH_BEHIND = 5              # this many+ pending patches is actionable
WARRANTY_SOON_DAYS = 30       # warranty expiring within this window
CONTRACT_SOON_DAYS = 45       # contract ending within this window
UNBILLED_HOURS_FLAG = 8.0     # this many+ unbilled billable hours = revenue leak
SLA_AT_RISK_MIN = 60          # SLA due within this many minutes = "at risk"


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _age_days(dt, now) -> float:
    d = _aware(dt)
    if not d:
        return 0.0
    return max(0.0, (now - d).total_seconds() / 86400.0)


def _score(severity: str, age_days: float, nudge: int = 0) -> int:
    """Base by severity, +up to 10 for age (older = more urgent), +/- a nudge."""
    return max(1, min(100, round(_BASE[severity] + min(age_days, 10.0) + nudge)))


class _Collector:
    def __init__(self, now):
        self.now = now
        self.items: list[dict] = []
        self._seq = 0

    def add(self, *, kind, severity, title, detail, client_id, client_name,
            entity_type, entity_id, link, action, age_days=0.0, nudge=0):
        self._seq += 1
        self.items.append({
            "id": f"{kind}:{entity_type}:{entity_id}:{self._seq}",
            "kind": kind,
            "severity": severity,
            "score": _score(severity, age_days, nudge),
            "title": title,
            "detail": detail,
            "client_id": client_id,
            "client_name": client_name,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "link": link,            # dashboard deep-link (hash route)
            "action": action,        # recommended next step, plain English
            "age_days": round(age_days, 1),
        })


def build(db: Session, user: User, *, now: datetime | None = None,
          client_id: int | None = None, limit: int = 100,
          is_staff: bool = False) -> dict:
    """Compute the ranked action feed for the caller's scope.

    `is_staff` must be passed by the route (it already resolved it). A client
    user is always pinned to their own client_id regardless of the argument.
    """
    now = now or datetime.now(timezone.utc)
    col = _Collector(now)

    # ---- Resolve scope -----------------------------------------------------
    if not is_staff:
        scope_ids = [user.client_id] if user.client_id else []
    elif client_id is not None:
        scope_ids = [client_id]
    else:
        scope_ids = None  # all clients

    names = {c.id: c.name for c in db.query(Client).all()}

    def in_scope(q, model):
        if scope_ids is None:
            return q
        return q.filter(model.client_id.in_(scope_ids))

    cname = lambda cid: names.get(cid, f"Client {cid}")

    # ---- 1. Tickets: SLA breached / at risk -------------------------------
    open_tickets = in_scope(db.query(SupportTicket).filter(
        SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS])),
        SupportTicket).all()
    for t in open_tickets:
        s = sla.evaluate(t, now)
        link = f"#tickets/{t.id}"
        if s["breached"]:
            which = "resolution" if s["resolution_breached"] else "response"
            col.add(kind="sla_breach", severity="critical",
                    title=f"SLA breached — “{t.subject}”",
                    detail=f"{which.title()} SLA passed for a {t.priority} ticket.",
                    client_id=t.client_id, client_name=cname(t.client_id),
                    entity_type="ticket", entity_id=t.id, link=link,
                    action="Respond/resolve now and note the breach.",
                    age_days=_age_days(t.created_at, now),
                    nudge=8 if t.priority in ("urgent", "high") else 0)
        else:
            mins = [m for m in (s["response_minutes_left"], s["resolution_minutes_left"])
                    if m is not None]
            if mins and min(mins) <= SLA_AT_RISK_MIN:
                col.add(kind="sla_at_risk", severity="high",
                        title=f"SLA due soon — “{t.subject}”",
                        detail=f"SLA due in {max(0, min(mins))} min for a {t.priority} ticket.",
                        client_id=t.client_id, client_name=cname(t.client_id),
                        entity_type="ticket", entity_id=t.id, link=link,
                        action="Pick this up before the clock runs out.",
                        age_days=_age_days(t.created_at, now))

    # ---- 2. Alerts: active, unresolved ------------------------------------
    alerts = in_scope(db.query(Alert).filter(Alert.status != AlertStatus.RESOLVED),
                      Alert).all()
    for a in alerts:
        crit = a.severity == AlertSeverity.CRITICAL
        warn = a.severity == AlertSeverity.WARNING
        sev = "critical" if crit else ("high" if warn else "low")
        # An acknowledged alert is being handled — de-prioritize a band.
        if a.status == AlertStatus.ACKNOWLEDGED:
            sev = {"critical": "high", "high": "medium", "low": "low"}[sev]
        col.add(kind="alert", severity=sev,
                title=a.message[:120],
                detail=f"{a.severity.value.title()} alert ({a.kind}) is {a.status.value}.",
                client_id=a.client_id, client_name=cname(a.client_id),
                entity_type="alert", entity_id=a.id, link="#alerts",
                action="Investigate the device and acknowledge/resolve.",
                age_days=_age_days(a.first_seen, now))

    # ---- 3. Devices: offline / AV off / low health / patch behind ---------
    devices = in_scope(db.query(Device), Device).all()
    for d in devices:
        last = _aware(d.last_checkin)
        offline_min = None if last is None else (now - last).total_seconds() / 60
        if last is None or offline_min > OFFLINE_MINUTES:
            since = "never checked in" if last is None else f"silent {int(offline_min)} min"
            col.add(kind="device_offline", severity="high",
                    title=f"{d.hostname} is offline",
                    detail=f"Agent {since}.",
                    client_id=d.client_id, client_name=cname(d.client_id),
                    entity_type="device", entity_id=d.id, link=f"#devices/{d.id}",
                    action="Check power/network or the agent service.",
                    age_days=_age_days(d.last_checkin, now))
            continue  # if it's offline, its stale metrics aren't actionable
        if d.av_status and d.av_status.strip().lower() in ("off", "disabled", "none", "false"):
            col.add(kind="av_off", severity="high",
                    title=f"Antivirus off — {d.hostname}",
                    detail="Endpoint protection is reported disabled.",
                    client_id=d.client_id, client_name=cname(d.client_id),
                    entity_type="device", entity_id=d.id, link=f"#devices/{d.id}",
                    action="Re-enable AV / push a remediation runbook.")
        if d.health_score is not None and d.health_score < LOW_HEALTH:
            col.add(kind="low_health", severity="medium",
                    title=f"Low health ({d.health_score}) — {d.hostname}",
                    detail="Sustained resource pressure or repeated alerts.",
                    client_id=d.client_id, client_name=cname(d.client_id),
                    entity_type="device", entity_id=d.id, link=f"#devices/{d.id}",
                    action="Open the device, review CPU/RAM/disk trend.",
                    nudge=max(0, (LOW_HEALTH - d.health_score) // 10))
        if (d.patches_pending or 0) >= PATCH_BEHIND:
            col.add(kind="patch_behind", severity="medium",
                    title=f"{d.patches_pending} patches pending — {d.hostname}",
                    detail="Device is behind on updates.",
                    client_id=d.client_id, client_name=cname(d.client_id),
                    entity_type="device", entity_id=d.id, link=f"#patches",
                    action="Schedule a patch window / approve updates.")

    # ---- 4. Security findings: open high/critical -------------------------
    findings = in_scope(db.query(SecurityFinding).filter(
        SecurityFinding.status.in_([FindingStatus.OPEN, FindingStatus.REMEDIATING]),
        SecurityFinding.severity.in_([FindingSeverity.HIGH, FindingSeverity.CRITICAL])),
        SecurityFinding).all()
    for f in findings:
        sev = "critical" if f.severity == FindingSeverity.CRITICAL else "high"
        col.add(kind="security_finding", severity=sev,
                title=f"{f.severity.value.title()} finding — {f.title}",
                detail=(f.recommendation or f.description or "Open security finding.")[:160],
                client_id=f.client_id, client_name=cname(f.client_id),
                entity_type="finding", entity_id=f.id, link="#security",
                action="Remediate or formally risk-accept.",
                age_days=_age_days(f.discovered_at, now))

    # ---- 5. Assets: warranty expiring / expired ---------------------------
    soon = now + timedelta(days=WARRANTY_SOON_DAYS)
    assets = in_scope(db.query(Asset).filter(Asset.warranty_expires.isnot(None),
                                             Asset.status != "retired"), Asset).all()
    for a in assets:
        we = _aware(a.warranty_expires)
        if we and we <= soon:
            expired = we < now
            col.add(kind="warranty", severity="low" if not expired else "medium",
                    title=f"Warranty {'expired' if expired else 'expiring'} — {a.name}",
                    detail=f"Warranty {'lapsed' if expired else 'ends'} {we.date().isoformat()}.",
                    client_id=a.client_id, client_name=cname(a.client_id),
                    entity_type="asset", entity_id=a.id, link="#assets",
                    action="Renew coverage or plan a replacement.")

    # ---- 6. Contracts: ending soon ----------------------------------------
    csoon = now + timedelta(days=CONTRACT_SOON_DAYS)
    contracts = in_scope(db.query(Contract).filter(Contract.status == "active",
                                                   Contract.end_date.isnot(None)),
                         Contract).all()
    for c in contracts:
        ed = _aware(c.end_date)
        if ed and ed <= csoon:
            col.add(kind="contract_renewal",
                    severity="medium" if ed >= now else "high",
                    title=f"Contract {'overdue for renewal' if ed < now else 'renewing soon'} — {c.name}",
                    detail=f"Agreement ends {ed.date().isoformat()}.",
                    client_id=c.client_id, client_name=cname(c.client_id),
                    entity_type="contract", entity_id=c.id, link="#billing",
                    action="Start the renewal conversation / send the QBR.")

    # ---- 7. Revenue leak: unbilled billable time --------------------------
    unbilled = in_scope(db.query(TimeEntry).filter(TimeEntry.billable.is_(True),
                                                  TimeEntry.invoiced.is_(False)),
                        TimeEntry).all()
    per_client: dict[int, int] = {}
    for te in unbilled:
        per_client[te.client_id] = per_client.get(te.client_id, 0) + (te.minutes or 0)
    for cid, mins in per_client.items():
        hours = mins / 60.0
        if hours >= UNBILLED_HOURS_FLAG:
            col.add(kind="unbilled_time", severity="low",
                    title=f"{hours:.1f}h unbilled — {cname(cid)}",
                    detail="Billable work logged but not yet invoiced.",
                    client_id=cid, client_name=cname(cid),
                    entity_type="client", entity_id=cid, link="#billing",
                    action="Roll this into an invoice.",
                    nudge=min(8, int(hours // 8)))

    # ---- 8. Overdue project tasks -----------------------------------------
    tasks = in_scope(db.query(ProjectTask).filter(
        ProjectTask.due_date.isnot(None), ProjectTask.status != "done"),
        ProjectTask).all()
    for t in tasks:
        due = _aware(t.due_date)
        if due and due < now:
            col.add(kind="overdue_task", severity="medium",
                    title=f"Overdue task — {t.title}",
                    detail=f"Due {due.date().isoformat()}, still {t.status}.",
                    client_id=t.client_id, client_name=cname(t.client_id),
                    entity_type="task", entity_id=t.id, link=f"#projects/{t.project_id}",
                    action="Update status or re-schedule the work.",
                    age_days=_age_days(t.due_date, now),
                    nudge=4 if t.priority in ("urgent", "high") else 0)

    # ---- Rank, summarize, score -------------------------------------------
    items = sorted(col.items, key=lambda x: (-x["score"], x["client_name"]))
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    by_kind: dict[str, int] = {}
    penalty = 0.0
    for it in items:
        counts[it["severity"]] += 1
        by_kind[it["kind"]] = by_kind.get(it["kind"], 0) + 1
        penalty += _PENALTY[it["severity"]]
    ops_score = max(0, round(100 - min(100.0, penalty)))

    return {
        "generated_at": now.isoformat(),
        "ops_score": ops_score,
        "total": len(items),
        "counts": counts,
        "by_kind": by_kind,
        "items": items[:limit],
        "truncated": len(items) > limit,
    }
