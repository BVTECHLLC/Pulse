"""v1.17 The Autonomy Engine — Pulse earns (and loses) the right to act alone.

Every RMM has automation rules. None of them check their own work. This engine
closes that loop in three layers:

  1. **Outcome grading** — every autonomous action (patch install, remediation,
     auto-ticket) is recorded and later graded by OBSERVABLE STATE, not vibes:
     did the patch job succeed? did the alert clear? did the auto-ticket resolve
     without breaching SLA? Deterministic; no AI in the verdict.
  2. **Trust ledger + earned-autonomy gate** — per (action_type, client), a
     rolling success rate. Machine-touching automations consult `allowed()`
     before firing: a combo whose measured success drops below the threshold is
     SUSPENDED automatically (and the operator is told). Operators can also pin
     a per-client ceiling ("supervised") — autonomy as a contract term.
  3. **Playbook memory + the Self-Driving Report** — the graded history becomes
     institutional memory the Copilot can consult ("last 4 times this fired
     here, the fix worked"), and a receipts-backed report: what Pulse handled
     alone, its success rate, and the tech-hours it saved.

Design: `record()` never breaks the calling action path (best-effort, no commit
— the caller's transaction owns it). `grade_due()` runs on the heartbeat and
commits its own verdicts. Suspension is default-permissive: with no failure
history the gate allows (those paths were explicitly enabled by policy); it
develops teeth from evidence.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import (ActionOutcome, Alert, AlertStatus, Client, DeploymentStatus,
                      Notification, ScriptDeployment, SupportTicket, TicketStatus)
from . import secure_config

PROVIDER = "autonomy"            # settings: thresholds + per-client ceilings
WATCH_PROVIDER = "autonomy_watch"  # dedup ledger for suspension notifications

# Conservative per-action estimates of technician minutes saved when the action
# succeeds autonomously (shown as estimates in the Self-Driving Report).
MINUTES_SAVED = {"patch_install": 25, "remediation": 20, "auto_ticket": 8}

# Grading windows / stall limits.
_STALL_HOURS = {"patch_install": 24}     # job never picked up/finished
_TICKET_MAX_DAYS = 7                     # open auto-ticket ages out to indeterminate

DEFAULTS = {"min_samples": 5, "min_success": 0.8}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Settings (vault-backed)
# --------------------------------------------------------------------------- #
def get_settings(db: Session) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    ceilings = cfg.get("ceilings") or {}   # {client_id(str): "auto"|"supervised"}
    try:
        min_samples = max(2, int(cfg.get("min_samples", DEFAULTS["min_samples"])))
    except (TypeError, ValueError):
        min_samples = DEFAULTS["min_samples"]
    try:
        min_success = min(1.0, max(0.1, float(cfg.get("min_success", DEFAULTS["min_success"]))))
    except (TypeError, ValueError):
        min_success = DEFAULTS["min_success"]
    return {"min_samples": min_samples, "min_success": min_success,
            "ceilings": {str(k): v for k, v in ceilings.items() if v in ("auto", "supervised")}}


def save_settings(db: Session, *, min_samples: int | None = None,
                  min_success: float | None = None,
                  ceilings: dict | None = None) -> dict:
    cur = get_settings(db)
    if min_samples is not None:
        cur["min_samples"] = max(2, int(min_samples))
    if min_success is not None:
        cur["min_success"] = min(1.0, max(0.1, float(min_success)))
    if ceilings is not None:
        cur["ceilings"] = {str(k): v for k, v in ceilings.items()
                           if v in ("auto", "supervised")}
    secure_config.upsert_platform(db, PROVIDER, "Autonomy Engine", "Automation", cur)
    return cur


# --------------------------------------------------------------------------- #
# 1) Recording — instrument the action paths
# --------------------------------------------------------------------------- #
def record(db: Session, *, action_type: str, playbook: str, client_id: int | None,
           ref_kind: str, ref_id: int, device_id: int | None = None,
           autonomous: bool = True, grade_after_minutes: int = 30,
           now: datetime | None = None) -> ActionOutcome | None:
    """Log one taken action for later grading. Idempotent per (type, ref).
    Adds to the caller's session WITHOUT committing; never raises."""
    try:
        now = now or _utcnow()
        dup = (db.query(ActionOutcome)
               .filter(ActionOutcome.action_type == action_type,
                       ActionOutcome.ref_kind == ref_kind,
                       ActionOutcome.ref_id == ref_id).first())
        if dup:
            return dup
        row = ActionOutcome(action_type=action_type, playbook=playbook[:160],
                            client_id=client_id, device_id=device_id,
                            ref_kind=ref_kind, ref_id=ref_id, autonomous=autonomous,
                            taken_at=now,
                            grade_after=now + timedelta(minutes=grade_after_minutes))
        db.add(row)
        db.flush()
        return row
    except Exception:  # noqa: BLE001 — telemetry must never break the action
        return None


# --------------------------------------------------------------------------- #
# 2) Grading — observable state transitions, no AI
# --------------------------------------------------------------------------- #
def _grade_patch_install(db: Session, o: ActionOutcome, now: datetime):
    dep = db.get(ScriptDeployment, o.ref_id)
    if dep is None:
        return "indeterminate", "deployment row vanished"
    if dep.status == DeploymentStatus.SUCCEEDED:
        return "success", f"job #{dep.id} succeeded (exit {dep.exit_code})"
    if dep.status in (DeploymentStatus.FAILED, DeploymentStatus.REJECTED,
                      DeploymentStatus.CANCELED):
        return "failure", f"job #{dep.id} {dep.status.value} (exit {dep.exit_code})"
    # Still pending/approved/running — stall out after the limit, else re-check later.
    if (now - _aware(o.taken_at)) > timedelta(hours=_STALL_HOURS["patch_install"]):
        return "indeterminate", f"job #{dep.id} never finished ({dep.status.value})"
    return None, None


def _grade_remediation(db: Session, o: ActionOutcome, now: datetime):
    alert = db.get(Alert, o.ref_id)
    if alert is None:
        return "indeterminate", "alert row vanished"
    if alert.status == AlertStatus.RESOLVED:
        return "success", f"alert '{alert.kind}' cleared"
    # Past the grading window and the condition is still live -> the fix didn't fix.
    return "failure", f"alert '{alert.kind}' still {alert.status.value} after remediation"


def _grade_auto_ticket(db: Session, o: ActionOutcome, now: datetime):
    t = db.get(SupportTicket, o.ref_id)
    if t is None:
        return "indeterminate", "ticket row vanished"
    if t.status in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
        if t.sla_breach_alerted:
            return "failure", f"ticket #{t.id} resolved but breached SLA first"
        return "success", f"ticket #{t.id} resolved within SLA"
    if (now - _aware(o.taken_at)) > timedelta(days=_TICKET_MAX_DAYS):
        return "indeterminate", f"ticket #{t.id} still open after {_TICKET_MAX_DAYS}d"
    if t.sla_breach_alerted:
        return "failure", f"ticket #{t.id} breached SLA while open"
    return None, None   # still inside its window — grade on a later tick


_GRADERS = {"patch_install": _grade_patch_install,
            "remediation": _grade_remediation,
            "auto_ticket": _grade_auto_ticket}


def grade_due(db: Session, now: datetime | None = None) -> list[dict]:
    """Heartbeat entrypoint: grade every due, ungraded outcome. Commits."""
    now = now or _utcnow()
    due = (db.query(ActionOutcome)
           .filter(ActionOutcome.graded_at.is_(None),
                   ActionOutcome.grade_after <= now.replace(tzinfo=None))
           .limit(200).all())
    graded = []
    for o in due:
        fn = _GRADERS.get(o.action_type)
        if fn is None:
            continue
        try:
            verdict, evidence = fn(db, o, now)
        except Exception:  # noqa: BLE001
            continue
        if verdict is None:
            continue   # not decidable yet — next tick
        o.graded_at = now
        o.verdict = verdict
        o.evidence = (evidence or "")[:300]
        graded.append({"id": o.id, "action_type": o.action_type,
                       "playbook": o.playbook, "client_id": o.client_id,
                       "verdict": verdict})
    if graded:
        db.commit()
    return graded


# --------------------------------------------------------------------------- #
# 3) Trust ledger + the earned-autonomy gate
# --------------------------------------------------------------------------- #
def _stats(db: Session, action_type: str, client_id: int | None) -> dict:
    q = (db.query(ActionOutcome)
         .filter(ActionOutcome.action_type == action_type,
                 ActionOutcome.graded_at.isnot(None),
                 ActionOutcome.verdict.in_(["success", "failure"])))
    if client_id is not None:
        q = q.filter(ActionOutcome.client_id == client_id)
    rows = q.all()
    n = len(rows)
    ok = sum(1 for r in rows if r.verdict == "success")
    return {"samples": n, "successes": ok, "failures": n - ok,
            "success_rate": (ok / n) if n else None}


def allowed(db: Session, action_type: str, client_id: int | None) -> tuple[bool, str]:
    """The gate every machine-touching automation consults before firing."""
    cfg = get_settings(db)
    if client_id is not None and cfg["ceilings"].get(str(client_id)) == "supervised":
        return False, "operator ceiling: supervised (propose-only) for this client"
    st = _stats(db, action_type, client_id)
    if st["samples"] >= cfg["min_samples"] and st["success_rate"] is not None \
            and st["success_rate"] < cfg["min_success"]:
        return False, (f"suspended: {int(st['success_rate'] * 100)}% success over "
                       f"{st['samples']} graded runs (needs {int(cfg['min_success'] * 100)}%)")
    if st["samples"] >= cfg["min_samples"]:
        return True, (f"earned: {int(st['success_rate'] * 100)}% success over "
                      f"{st['samples']} runs")
    return True, f"building history ({st['samples']}/{cfg['min_samples']} graded runs)"


def notify_suspended(db: Session, action_type: str, client_id: int | None,
                     reason: str, now: datetime | None = None) -> bool:
    """Tell the operator an automation got benched — once per combo per day."""
    now = now or _utcnow()
    today = now.date().isoformat()
    key = f"{action_type}:{client_id}"
    conn = secure_config.get_platform(db, WATCH_PROVIDER)
    cfg = (conn.config if conn else None) or {}
    seen = set(cfg.get("seen", [])) if cfg.get("date") == today else set()
    if key in seen:
        return False
    seen.add(key)
    cname = None
    if client_id:
        cli = db.get(Client, client_id)
        cname = cli.name if cli else f"client {client_id}"
    try:
        db.add(Notification(client_id=client_id, target_user_id=None,
                            kind="autonomy", severity="warning",
                            message=(f"🛑 Autonomy suspended: {action_type}"
                                     f"{' at ' + cname if cname else ''} — {reason}. "
                                     f"Pulse will propose instead of act until its record recovers.")[:1000]))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    secure_config.upsert_platform(db, WATCH_PROVIDER, "Autonomy Watch", "Automation",
                                  {"date": today, "seen": sorted(seen)})
    return True


def ledger(db: Session, client_ids: list[int] | None = None) -> dict:
    """The trust ledger: per (action_type, client) samples/success/level."""
    cfg = get_settings(db)
    q = db.query(ActionOutcome).filter(ActionOutcome.graded_at.isnot(None),
                                       ActionOutcome.verdict.in_(["success", "failure"]))
    if client_ids is not None:
        q = q.filter(ActionOutcome.client_id.in_(client_ids))
    combos: dict[tuple, dict] = {}
    for r in q.all():
        k = (r.action_type, r.client_id)
        c = combos.setdefault(k, {"samples": 0, "successes": 0, "playbooks": set(),
                                  "last_verdict": None, "last_at": None})
        c["samples"] += 1
        c["successes"] += (r.verdict == "success")
        c["playbooks"].add(r.playbook)
        ga = _aware(r.graded_at)
        if c["last_at"] is None or (ga and ga > c["last_at"]):
            c["last_at"] = ga
            c["last_verdict"] = r.verdict
    names = {cl.id: cl.name for cl in db.query(Client).all()}
    rows = []
    for (atype, cid), c in combos.items():
        rate = c["successes"] / c["samples"]
        if str(cid) in cfg["ceilings"] and cfg["ceilings"][str(cid)] == "supervised":
            level = "supervised"
        elif c["samples"] >= cfg["min_samples"]:
            level = "earned" if rate >= cfg["min_success"] else "suspended"
        else:
            level = "watching"
        rows.append({"action_type": atype, "client_id": cid,
                     "client": names.get(cid), "samples": c["samples"],
                     "successes": c["successes"], "failures": c["samples"] - c["successes"],
                     "success_rate": round(rate, 3), "level": level,
                     "playbooks": sorted(c["playbooks"])[:6],
                     "last_verdict": c["last_verdict"]})
    order = {"suspended": 0, "watching": 1, "earned": 2, "supervised": 3}
    rows.sort(key=lambda r: (order.get(r["level"], 9), -r["samples"]))
    return {"settings": cfg, "combos": rows,
            "suspended": sum(1 for r in rows if r["level"] == "suspended"),
            "earned": sum(1 for r in rows if r["level"] == "earned")}


# --------------------------------------------------------------------------- #
# 4) Playbook memory + the Self-Driving Report
# --------------------------------------------------------------------------- #
def playbook_memory(db: Session, *, client_id: int | None = None,
                    action_type: str | None = None, playbook: str | None = None,
                    limit: int = 12) -> dict:
    """What happened the last N times Pulse acted here — the Copilot's memory."""
    q = db.query(ActionOutcome).filter(ActionOutcome.graded_at.isnot(None))
    if client_id is not None:
        q = q.filter(ActionOutcome.client_id == client_id)
    if action_type:
        q = q.filter(ActionOutcome.action_type == action_type)
    if playbook:
        q = q.filter(ActionOutcome.playbook.ilike(f"%{playbook}%"))
    rows = q.order_by(ActionOutcome.graded_at.desc()).limit(max(1, min(50, limit))).all()
    graded = [r for r in rows if r.verdict in ("success", "failure")]
    ok = sum(1 for r in graded if r.verdict == "success")
    return {"count": len(rows),
            "success_rate": round(ok / len(graded), 3) if graded else None,
            "history": [{"when": _aware(r.taken_at).isoformat() if r.taken_at else None,
                         "action_type": r.action_type, "playbook": r.playbook,
                         "client_id": r.client_id, "autonomous": r.autonomous,
                         "verdict": r.verdict, "evidence": r.evidence} for r in rows]}


def report(db: Session, days: int = 7, now: datetime | None = None) -> dict:
    """The Self-Driving Report — receipts for what Pulse handled by itself."""
    now = now or _utcnow()
    days = max(1, min(90, days))
    cutoff = now - timedelta(days=days)
    rows = (db.query(ActionOutcome)
            .filter(ActionOutcome.taken_at >= cutoff.replace(tzinfo=None))
            .all())
    auto = [r for r in rows if r.autonomous]
    graded = [r for r in auto if r.verdict in ("success", "failure")]
    ok = [r for r in graded if r.verdict == "success"]
    minutes = sum(MINUTES_SAVED.get(r.action_type, 10) for r in ok)
    by_type: dict[str, dict] = {}
    for r in auto:
        t = by_type.setdefault(r.action_type, {"taken": 0, "success": 0, "failure": 0,
                                               "pending": 0, "indeterminate": 0})
        t["taken"] += 1
        if r.verdict in ("success", "failure", "indeterminate"):
            t[r.verdict] += 1
        elif r.graded_at is None:
            t["pending"] += 1
    led = ledger(db)
    return {"generated_at": now.isoformat(), "window_days": days,
            "autonomous_actions": len(auto),
            "confirmed_actions": len(rows) - len(auto),
            "graded": len(graded), "successes": len(ok),
            "success_rate": round(len(ok) / len(graded), 3) if graded else None,
            "est_minutes_saved": minutes,
            "est_hours_saved": round(minutes / 60.0, 1),
            "by_type": by_type,
            "suspended_combos": [r for r in led["combos"] if r["level"] == "suspended"],
            "earned_combos": led["earned"]}
