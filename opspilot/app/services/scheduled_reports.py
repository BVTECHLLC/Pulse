"""v0.20 scheduled client reports. The run-checks tick calls send_due() which
emails a brief branded snapshot to each enabled schedule whose cadence is due.
Email delivery is a safe no-op (logged) until SMTP is configured."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import Client, ReportSchedule
from . import email as email_svc

_PERIOD = {"weekly": timedelta(days=7), "monthly": timedelta(days=30),
           "quarterly": timedelta(days=90)}


def _is_due(sched: ReportSchedule, now: datetime) -> bool:
    if not sched.enabled:
        return False
    if sched.last_sent_at is None:
        return True
    period = _PERIOD.get(sched.cadence, _PERIOD["monthly"])
    last = sched.last_sent_at
    if last.tzinfo is None:                 # normalize naive (SQLite) timestamps
        last = last.replace(tzinfo=timezone.utc)
    return (now - last) >= period


def _report_body(summary: dict, client: Client) -> str:
    """A rich, readable QBR text body built from the full report summary."""
    s = get_settings()
    d, pa, al = summary["devices"], summary["patch"], summary["alerts"]
    tk, pj, asset_ = summary["tickets"], summary["projects"], summary["assets"]
    sv, rev, sec = summary["service"], summary["revenue"], summary["security"]

    def line(label, val):
        return f"  {label:<26}{val}"

    return "\n".join([
        f"{s.APP_NAME} — Service Review for {client.name}",
        f"Generated {summary['generated_at'][:16].replace('T', ' ')} UTC",
        "=" * 52,
        "INFRASTRUCTURE",
        line("Devices monitored", d["total"]),
        line("Average health", d["avg_health"] if d["avg_health"] is not None else "n/a"),
        line("Patch compliance", f"{pa['compliance_pct']}%" if pa["compliance_pct"] is not None else "n/a"),
        line("Pending patches", pa["pending_total"]),
        line("Assets tracked", asset_["total"]),
        line("Warranties expiring (60d)", asset_["warranty_expiring"]),
        "",
        "SECURITY & ALERTS",
        line("Security score", sec.get("score", "n/a")),
        line("Active alerts", f"{al['total']} ({al['critical']} critical)"),
        "",
        "SERVICE DESK",
        line("Open tickets", tk["open"]),
        line("Resolved tickets", tk["resolved"]),
        line("SLA breaches", tk["sla_breached"]),
        line("Hours delivered (90d)", f"{sv['hours_90d']} ({sv['billable_hours_90d']} billable)"),
        "",
        "PROJECTS",
        line("Active projects", pj["active"]),
        line("Tasks completed", f"{pj['tasks_done']}/{pj['tasks_total']}"),
        "",
        "INVESTMENT",
        line("Monthly recurring", f"${rev['mrr']:,.2f}"),
        line("Annual run-rate", f"${rev['arr']:,.2f}"),
        "=" * 52,
        f"Full interactive report: {s.PUBLIC_BASE_URL}/report/{client.id}",
        "A CSV of these metrics is attached.",
    ])


def send_due(db: Session, now: datetime | None = None) -> dict:
    """Email every due schedule with the full QBR body + a CSV attachment.
    Returns counts. Safe to call every tick."""
    # Lazy import avoids any import cycle (reports route pulls in services).
    from ..api.routes.reports import _build_summary, summary_csv
    now = now or datetime.now(timezone.utc)
    schedules = db.query(ReportSchedule).filter(ReportSchedule.enabled.is_(True)).all()
    sent = 0
    for sched in schedules:
        if not _is_due(sched, now):
            continue
        client = db.get(Client, sched.client_id)
        if not client:
            continue
        summary = _build_summary(db, client, now)
        body = _report_body(summary, client)
        csv_name = f"report-{client.name.replace(' ', '_')}.csv"
        ok = False
        try:
            ok = email_svc.send(sched.recipient_email,
                                f"{get_settings().APP_NAME} report — {client.name}",
                                body, attachments=[(csv_name, summary_csv(summary), "text/csv")])
        except Exception as e:  # noqa: BLE001
            print(f"[reports] send to {sched.recipient_email} raised: {e}")
        # With SMTP unconfigured send() is a logged no-op returning False — still
        # advance the schedule (nothing will ever deliver until SMTP is set up).
        # With SMTP CONFIGURED, a failed send must NOT advance: the next tick
        # retries, and staff get a notification instead of silence.
        if ok or not get_settings().email_enabled:
            sched.last_sent_at = now
            sent += 1
        else:
            print(f"[reports] delivery failed for schedule {sched.id} "
                  f"({sched.recipient_email}) — will retry next tick")
            try:
                from ..models import Notification
                db.add(Notification(client_id=sched.client_id, target_user_id=None,
                                    kind="report", severity="warning",
                                    message=(f"Scheduled report for {client.name} failed to send "
                                             f"to {sched.recipient_email} — check SMTP settings. "
                                             f"It will retry automatically.")[:1000]))
            except Exception:  # noqa: BLE001
                pass
    if schedules:
        db.commit()
    return {"schedules": len(schedules), "reports_sent": sent}
