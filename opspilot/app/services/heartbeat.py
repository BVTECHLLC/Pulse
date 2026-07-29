"""v1.1 heartbeat — the master maintenance tick, callable from anywhere.

This is the body of what used to live only inside POST /api/automation/run-checks.
Extracting it lets THREE callers share one implementation:
  * the Autopilot background scheduler (scheduler.py) — no external cron needed
  * the /api/automation/run-checks endpoint — staff "run now"
  * tests — deterministic, offline

Every sub-task is best-effort: one failing integration never blocks the rest
(a dead SMTP config shouldn't stop SLA breach detection).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import SupportTicket, TicketStatus
from . import monitoring, sla


def run_all(db: Session, now: datetime | None = None) -> dict:
    """Run every recurring check/automation once. Idempotent by design — each
    sub-service dedupes its own sends (weekly digest per ISO week, SLA breach
    via sla_breach_alerted, reports via their own schedule bookkeeping...), so
    calling this as often as every couple of minutes is safe."""
    from . import automation as automation_svc  # local import: avoid cycles
    now = now or datetime.now(timezone.utc)

    # 1) Offline sweep.
    sweep, new_offline = monitoring.sweep_offline(db)

    # 1.1) Incident Intelligence (v1.19) FIRST: correlate alert STORMS into one
    #      incident + ONE ticket. Member alerts are consumed BEFORE any per-alert
    #      handling (automation rules, auto-remediation, auto-tickets) — twenty
    #      offline alerts from one dead switch must not fire twenty rule actions.
    #      Also auto-resolve incidents whose member alerts have all cleared.
    from . import incidents as incidents_svc
    incident_summary = {"incidents": [], "consumed": set()}
    incidents_resolved = []
    try:
        incident_summary = incidents_svc.correlate(db, new_offline, now)
    except Exception:  # noqa: BLE001
        db.rollback()
    try:
        incidents_resolved = incidents_svc.sweep_resolutions(db, now)
    except Exception:  # noqa: BLE001
        db.rollback()
    consumed = incident_summary.get("consumed", set())
    remaining = [a for a in new_offline if a.id not in consumed]

    # 1.2) Per-alert handling — alert.opened automations + auto-remediation —
    #      for NON-storm alerts only (a site outage isn't fixable per-device).
    from . import auto_remediation
    from ..models import Device
    for alert in remaining:
        dev = db.get(Device, alert.device_id)
        automation_svc.dispatch(db, "alert.opened",
                                automation_svc.build_alert_context(alert, dev))
        try:
            auto_remediation.on_alert(db, alert, dev)   # detect → fix
        except Exception:  # noqa: BLE001
            pass

    # 1.3) Proactive Ops (v1.7): auto-open tickets for newly-offline critical
    #      alerts (storm members already have their single incident ticket).
    if remaining:
        from . import proactive
        try:
            if proactive.on_new_alerts(db, remaining):
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()

    # 2) SLA breach detection + built-in escalation (deduped per ticket).
    from . import sla_escalation
    open_tickets = (db.query(SupportTicket)
                    .filter(SupportTicket.status.in_([TicketStatus.OPEN,
                                                      TicketStatus.IN_PROGRESS]))
                    .all())
    sla_fired = 0
    escalated = 0
    for t in open_tickets:
        s = sla.evaluate(t, now)
        if s["breached"] and not t.sla_breach_alerted:
            t.sla_breach_alerted = True
            esc = sla_escalation.escalate(db, t, now)
            if esc["priority_bumped"]:
                escalated += 1
            db.commit()   # persist flag + escalation before custom rules dispatch
            ctx = automation_svc.build_ticket_context(t)
            ctx["breach"] = True
            automation_svc.dispatch(db, "ticket.sla_breached", ctx)
            sla_fired += 1

    # 3) Due time-based automation rules (v0.53).
    scheduled = automation_svc.run_scheduled(db, now)

    # 4) Recurring billing (v0.58).
    from . import recurring_billing
    recurring = []
    try:
        recurring = recurring_billing.generate_due(db, now)
    except Exception:  # noqa: BLE001
        pass

    # 5) A/R payment reminders (v0.62).
    from . import ar_aging
    reminders = []
    try:
        reminders = ar_aging.send_due_reminders(db, now)
    except Exception:  # noqa: BLE001
        pass

    # 6) Posture snapshots + grade-slip alerts (v0.67).
    from . import posture_history
    snapshots = []
    try:
        snapshots = posture_history.snapshot_all(db, now)
    except Exception:  # noqa: BLE001
        pass

    # 7) Auto-posting (v0.70).
    from . import autopost
    posts = []
    try:
        posts = autopost.publish_due(db, now)
    except Exception:  # noqa: BLE001
        pass

    # 8) Weekly "State of the Practice" digest (v0.85).
    from . import weekly_digest
    digest = {"sent": False}
    try:
        digest = weekly_digest.maybe_send(db, now)
    except Exception:  # noqa: BLE001
        pass

    # 9) Due scheduled client reports (v0.20).
    from . import scheduled_reports
    reports = {"reports_sent": 0}
    try:
        reports = scheduled_reports.send_due(db, now)
    except Exception:  # noqa: BLE001
        pass

    # 10) Connector health watchdog (v0.52.2) — at most hourly.
    from . import integration_health
    health = None
    try:
        health = integration_health.maybe_sweep(db, min_interval_minutes=60)
    except Exception:  # noqa: BLE001
        pass

    # 11) AI ticket triage (v1.1) — Claude reads new tickets, suggests priority/
    #     summary/next step. No-op when AI is off or every ticket is triaged.
    from . import ai_triage
    triaged = []
    try:
        triaged = ai_triage.sweep(db, now)
    except Exception:  # noqa: BLE001
        pass

    # 12) Academy streak-saver emails (v1.3) — afternoon nudge for streaks that
    #     die at midnight; once per user per day.
    from . import academy
    streaks_saved = []
    try:
        streaks_saved = academy.streak_reminders(db, now)
    except Exception:  # noqa: BLE001
        pass

    # 13.25) Foresight watch (v1.13) — raise PREDICTED risks (disk full soon,
    #        health decline, resource spikes) before they hard-alert. Deduped
    #        per device+kind per day.
    from . import foresight
    predicted = []
    try:
        predicted = foresight.watch(db, now)
    except Exception:  # noqa: BLE001
        db.rollback()

    # 13.27) Autonomy Engine (v1.17) — grade every due autonomous action by its
    #        observed outcome; the trust ledger + earned-autonomy gate feed off
    #        these verdicts.
    from . import autonomy
    outcomes = []
    try:
        outcomes = autonomy.grade_due(db, now)
    except Exception:  # noqa: BLE001
        db.rollback()

    # 13.28) PSA SLA foresight (v1.15) — warn on tickets about to breach SLA
    #        (critical window) BEFORE the breach, deduped per ticket per day.
    from . import psa_intel
    sla_watch = []
    try:
        sla_watch = psa_intel.sla_watch(db, now)
    except Exception:  # noqa: BLE001
        db.rollback()

    # 13.3) Proactive Copilot briefing (v1.12) — once per morning, drop an
    #       action-oriented "here's what needs doing" note into notifications.
    from . import copilot_briefing
    briefing = {"posted": False}
    try:
        briefing = copilot_briefing.maybe_post(db, now)
    except Exception:  # noqa: BLE001
        db.rollback()

    # 13.4) Patch auto-approval (v1.9) — hands-off: approve pending patches per
    #       policy (severity + optional maintenance-window gate); the agent then
    #       installs them on its next check-in. Off by default.
    from . import patching
    patches_auto = []
    try:
        patches_auto = patching.auto_approve_sweep(db, now)
        if patches_auto:
            db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()

    # 13.5) Website auto-blogger (v1.4) — Claude writes + publishes a bvtech.org
    #        article on its cadence; off by default, guarded, never silent.
    from . import blog_autopilot
    blog = {"published": False}
    try:
        blog = blog_autopilot.maybe_publish(db, now)
    except Exception:  # noqa: BLE001
        pass

    # 13.55) Content Autopilot (v1.20) — one customized post per channel per day
    #        (bvtech.org, jordanpolasek.com, LinkedIn, Google Business). Failures
    #        notify + retry next tick; success is the only thing that marks a
    #        channel done. Off by default.
    from . import content_autopilot
    content = {"ran": False}
    try:
        content = content_autopilot.run_daily(db, now)
    except Exception:  # noqa: BLE001
        db.rollback()

    # 13.56) jordanpolasek.com build verification (v1.20) — watch the deploy
    #        pipeline for commits Pulse pushed; auto-revert + notify on failure.
    from . import jp_site
    jp_verified = []
    try:
        jp_verified = jp_site.verify_pending(db, now)
    except Exception:  # noqa: BLE001
        db.rollback()

    # 13.560) v1.61 SELF-UPDATE announcement — the box deploys CI-green main on
    #         its own (scripts/box_autoupdate.sh); the first heartbeat on a new
    #         version tells the operator it happened. Never-silent, zero-SSH.
    try:
        from ..core.config import get_settings as _gs61
        from . import secure_config as _sc61
        _ver61 = _gs61().APP_VERSION
        _conn61 = _sc61.get_platform(db, "pulse_meta")
        _raw61 = dict((_conn61.config if _conn61 else None) or {})
        if _raw61.get("last_version") != _ver61:
            if _raw61.get("last_version"):
                from ..models import Notification as _N61
                db.add(_N61(client_id=None, target_user_id=None, kind="system",
                            severity="info",
                            message=(f"🚀 Pulse auto-updated to v{_ver61} "
                                     f"(from v{_raw61.get('last_version')}) — deployed "
                                     "automatically from CI-green main.")[:1000]))
                db.commit()
            _sc61.upsert_platform(db, "pulse_meta", "Pulse Meta", "System",
                                  {**_raw61, "last_version": _ver61})
    except Exception:  # noqa: BLE001
        db.rollback()

    # 13.565) v1.56 OUTBOUND acquisition engine — ramped cold-email touches to
    #         scraped CRM leads over the M365 mailbox. Armed via the portal or
    #         PULSE_OUTBOUND=test|live on the box; TEST emails the day's plan to
    #         the shop's own inbox and never touches a lead. Daily counters and
    #         stamps make the 2-minute tick harmless.
    from . import outbound as outbound_eng
    outb = {"ran": False}
    try:
        outb = outbound_eng.tick(db, now)
    except Exception:  # noqa: BLE001
        db.rollback()

    # 13.57) v1.40 FLOOD GUARD self-heal — collapse duplicate queued social
    #        drafts and sweep same-day duplicate posts off the live sites
    #        (hourly per site). Only while the autopilot is enabled, so the
    #        guard follows the same master switch as the engine it protects.
    try:
        if content_autopilot.get_config(db)["enabled"]:
            content_autopilot.collapse_queue(db)
            jp_site.sweep_duplicates(db, now)
            # v1.45: the LIVE CISA-KEV homepage ticker refreshes on the
            # heartbeat (self-stamped once per day) instead of waiting for the
            # 9am-CT posting window — a fresh deploy updates it within minutes.
            import os as _os_hb
            if not _os_hb.environ.get("PULSE_DISABLE_KEV_TICKER"):
                jp_site.update_kev_ticker(db, now)
    except Exception:  # noqa: BLE001
        db.rollback()

    # 13) Academy AI question refresh (v1.3) — monthly, only when Claude is
    #     connected; cheap month-key check otherwise.
    academy_ai = {"refreshed": False}
    try:
        academy_ai = academy.ai_refresh(db, now)
    except Exception:  # noqa: BLE001
        pass

    return {"offline": sweep, "sla_breaches_fired": sla_fired, "escalated": escalated,
            "reports": reports, "health_checked": (health or {}).get("checked", 0),
            "scheduled_fired": len(scheduled), "recurring_invoices": len(recurring),
            "reminders_sent": len(reminders), "posture_snapshots": len(snapshots),
            "posts_published": len([p for p in posts if p.get("ok")]),
            "weekly_digest": digest, "ai_triaged": len(triaged),
            "streak_reminders": len(streaks_saved), "academy_ai": academy_ai,
            "blog": blog, "patches_auto_approved": len(patches_auto),
            "briefing_posted": briefing.get("posted", False),
            "predicted_risks": len(predicted), "sla_watch": len(sla_watch),
            "outcomes_graded": len(outcomes),
            "incidents": len(incident_summary.get("incidents", [])),
            "incidents_resolved": len(incidents_resolved),
            "content_autopilot": {k: v.get("ok") for k, v in
                                  (content.get("results") or {}).items()},
            "outbound": {k: outb.get(k) for k in
                         ("ran", "mode", "reason", "sent", "eligible") if k in outb},
            "jp_builds_checked": len(jp_verified)}
