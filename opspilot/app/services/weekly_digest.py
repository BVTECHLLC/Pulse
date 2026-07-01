"""v0.85 Weekly "State of the Practice" digest.

Every Monday morning the owner gets one email that opens with the practice's
overall grade (A–F) and the week's headline numbers, then the full
what-needs-attention briefing. It runs on the existing run-checks tick — no
cron config, no dashboard babysitting — and is idempotent: it sends at most
once per ISO week, tracked on the ``weekly_digest`` vault row so a scheduler
that fires every few minutes can't double-send.

Config (public-safe, on the vault): enabled, weekday (0=Mon), send-after hour
(local-naive UTC hour), and recipients (defaults to every OWNER's email).
Sending is no-op-safe when SMTP is off (logged), so it's on by default.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import briefing, email as email_svc, practice_health, secure_config

PROVIDER = "weekly_digest"

_DEF_WEEKDAY = 0     # Monday
_DEF_HOUR = 7        # send once the tick after 07:00 UTC on the chosen weekday


def _defaults() -> dict:
    return {"enabled": True, "weekday": _DEF_WEEKDAY, "hour": _DEF_HOUR, "recipients": []}


def get_config(db: Session) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    out = _defaults()
    if "enabled" in cfg:
        out["enabled"] = bool(cfg["enabled"])
    try:
        out["weekday"] = max(0, min(6, int(cfg.get("weekday", _DEF_WEEKDAY))))
    except (TypeError, ValueError):
        pass
    try:
        out["hour"] = max(0, min(23, int(cfg.get("hour", _DEF_HOUR))))
    except (TypeError, ValueError):
        pass
    rec = cfg.get("recipients")
    if isinstance(rec, list):
        out["recipients"] = [str(r).strip() for r in rec if str(r).strip()]
    # last_sent_week is internal bookkeeping, surfaced read-only for the UI.
    out["last_sent_week"] = cfg.get("last_sent_week")
    return out


def _owner_emails(db: Session) -> list[str]:
    from ..models import Role, User
    rows = (db.query(User)
            .filter(User.role == Role.OWNER, User.is_active.is_(True)).all())
    return [u.email for u in rows if u.email]


def save_config(db: Session, fields: dict) -> dict:
    cur = get_config(db)
    payload = {"enabled": cur["enabled"], "weekday": cur["weekday"],
               "hour": cur["hour"], "recipients": cur["recipients"],
               "last_sent_week": cur.get("last_sent_week")}
    if "enabled" in (fields or {}):
        payload["enabled"] = bool(fields["enabled"])
    if fields.get("weekday") is not None:
        payload["weekday"] = max(0, min(6, int(fields["weekday"])))
    if fields.get("hour") is not None:
        payload["hour"] = max(0, min(23, int(fields["hour"])))
    if fields.get("recipients") is not None:
        rec = fields["recipients"]
        if isinstance(rec, str):
            rec = [p.strip() for p in rec.replace("\n", ",").split(",")]
        payload["recipients"] = [str(r).strip() for r in (rec or []) if str(r).strip()]
    secure_config.upsert_platform(db, PROVIDER, "Weekly Digest", "State of the practice", payload)
    return get_config(db)


def _week_key(now: datetime) -> str:
    iso = now.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _recipients(db: Session, cfg: dict) -> list[str]:
    return cfg.get("recipients") or _owner_emails(db)


def render(db: Session, now: datetime | None = None) -> tuple[str, str]:
    """Build the (subject, body) for the weekly digest. Leads with the practice
    grade + headline numbers, then the full attention briefing."""
    now = now or datetime.now(timezone.utc)
    try:
        ph = practice_health.practice_health(db, now)
    except Exception:
        ph = {"grade": "N/A", "score": None, "domains": {}}
    brief = briefing.build(db)

    grade = ph.get("grade", "N/A")
    score = ph.get("score")
    subject = f"State of the Practice — grade {grade} · {brief['attention_total']} to action ({now:%b %d})"

    lines = ["State of the Practice",
             f"Week of {now:%B %d, %Y}", ""]
    lines.append(f"Overall practice grade: {grade}" + (f" ({score}/100)" if score is not None else ""))
    doms = ph.get("domains") or {}
    if doms:
        pretty = ", ".join(f"{k} {v.get('grade','?')}" for k, v in doms.items())
        lines.append(f"By area: {pretty}")
    for rec in (ph.get("recommendations") or [])[:3]:
        lines.append(f"  → {rec}")
    lines += ["", f"{brief['attention_total']} items need attention this week:", ""]
    for s in brief["sections"]:
        lines.append(f"{s['title']}: {s['count']}")
        for ln in s.get("lines", [])[:5]:
            lines.append(f"   • {ln}")
    lines += ["", "Open the dashboard for the live picture.", "— Pulse"]
    return subject, "\n".join(lines)


def maybe_send(db: Session, now: datetime | None = None, *, sender=None) -> dict:
    """Run on the scheduler tick. Sends the weekly digest at most once per ISO
    week, only on/after the configured weekday+hour. Returns a small status dict
    (never raises)."""
    now = now or datetime.now(timezone.utc)
    cfg = get_config(db)
    if not cfg.get("enabled"):
        return {"sent": False, "reason": "disabled"}
    if now.weekday() != cfg["weekday"] or now.hour < cfg["hour"]:
        return {"sent": False, "reason": "not_due"}
    wk = _week_key(now)
    if cfg.get("last_sent_week") == wk:
        return {"sent": False, "reason": "already_sent", "week": wk}

    recipients = _recipients(db, cfg)
    subject, body = render(db, now)
    send = sender or email_svc.send
    delivered = 0
    for to in recipients:
        try:
            if send(to, subject, body):
                delivered += 1
        except Exception:
            pass

    # Mark the week done even if there were zero recipients / SMTP is off, so we
    # don't retry every tick for the rest of the day. (A real send failure with
    # SMTP configured is rare; the next week's send is unaffected.) Non-secret
    # keys not passed here are preserved by the vault's partial-update merge.
    secure_config.upsert_platform(
        db, PROVIDER, "Weekly Digest", "State of the practice", {"last_sent_week": wk})
    return {"sent": True, "week": wk, "recipients": len(recipients), "delivered": delivered}
