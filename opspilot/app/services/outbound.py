"""v1.52 Outbound — autonomous daily client-acquisition email engine for BVTech.

Turns the CRM's cold leads into booked calls on a hands-free daily cadence, the
same way content_autopilot runs the blog. Built ON TOP of campaigns.py's already
-compliant send primitives; adds what a real outbound program actually needs:

  * Warm-up ramp — deliverability is the whole game. A brand-new sending domain
    that blasts 100 emails on day one gets spam-foldered and blacklisted, which
    kills the program AND poisons the company's normal mail. ``warmup_cap`` ramps
    the daily ceiling from a gentle start to the aggressive target over ~2 weeks,
    then holds there. Same destination — domain reputation intact.
  * Multi-touch sequence — one email rarely lands a client. Each lead flows
    through a short, on-voice sequence (intro → proof → soft break-up), one touch
    every few days. Sequence position is DERIVED from prior logged campaign sends
    on the CRM timeline, so there is no new schema/migration to ship.
  * Suppression + compliance — never a customer, never ``do_not_contact``, never
    a lead already touched today or one that finished the sequence, and never
    without a physical mailing address + one-click opt-out in the footer
    (CAN-SPAM). Every send is logged to the contact's CRM timeline.
  * Autonomous, but safe by construction — OFF until it is explicitly enabled
    AND a physical mailing address + sender are configured AND a real transport
    is wired in. ``dry_run`` previews the entire day's plan with zero sends. The
    heartbeat calls :func:`run_daily` once per day; the daily cap makes a double
    tick harmless.

The transport (``send_fn(to, subject, body)``) is injected, exactly like
campaigns.py — so selection / ramp / sequencing / compliance / logging are all
unit-testable with no network and no real emails.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import CrmActivity, CrmContact
from . import campaigns, crm, secure_config

PROVIDER = "outbound_campaign"
CAMPAIGN = "bvtech_acq"          # tags every send's CRM activity meta
GAP_DAYS = 3                     # days between touches in a sequence
# Statuses that must never receive cold outreach.
SUPPRESSED_STATUS = {"customer", "client", "won", "closed", "disqualified",
                     "unsubscribed", "bounced", "do_not_contact"}

# Warm-up ramp defaults (days -> daily ceiling). Gentle start protects a cold
# domain; +15/day reaches an "aggressive" target inside ~2 weeks.
RAMP_START = 20
RAMP_STEP = 15


def warmup_cap(day_index: int, target: int, *, start: int = RAMP_START,
               step: int = RAMP_STEP) -> int:
    """Today's max sends. day 0 = start; climbs by `step`/day; capped at target.
    Pure + deterministic so the ramp is trivially testable."""
    if day_index < 0:
        day_index = 0
    return max(0, min(int(target), int(start) + int(step) * int(day_index)))


# --- The sequence. First-person, from Jordan; value-first; Texas-local; never
#     salesy-spammy. {first}/{company} are filled per contact. Keep each touch
#     short — cold email that reads like a human gets replies. -------------------
_SEQUENCE = [
    {
        "step": 0,
        "subject": "quick question about {company}'s IT",
        "body": (
            "Hi {first},\n\n"
            "I'm Jordan, founder of BVTech — a Texas MSP that's handled IT and "
            "cybersecurity for local small businesses since 2013.\n\n"
            "I work with a handful of teams around San Antonio, Houston, and "
            "Austin, and the pattern is almost always the same: things run fine "
            "until one outage, one phishing email, or one failed backup turns "
            "into a very expensive week.\n\n"
            "Would it be worth a 15-minute call to see whether {company} has any "
            "of those gaps? No pitch — I'll tell you straight if you're already "
            "in good shape.\n\n"
            "— Jordan Polasek, BVTech LLC"
        ),
    },
    {
        "step": 1,
        "subject": "re: {company}'s IT — one thing worth checking",
        "body": (
            "Hi {first},\n\n"
            "Following up with something useful either way: the single cheapest "
            "security win for a small business is turning on multi-factor "
            "authentication everywhere — email, banking, remote access. It stops "
            "the vast majority of account takeovers and takes an afternoon.\n\n"
            "If you'd like, I'll do a free 15-minute review of where {company} "
            "stands and hand you the list whether or not we ever work together.\n\n"
            "— Jordan, BVTech LLC"
        ),
    },
    {
        "step": 2,
        "subject": "closing the loop, {first}",
        "body": (
            "Hi {first},\n\n"
            "I don't want to crowd your inbox, so this is my last note. If IT and "
            "security for {company} are handled, genuinely glad to hear it.\n\n"
            "If they're ever not — an outage, a scare, a provider who stopped "
            "answering — keep BVTech in your back pocket. We're local, we pick up "
            "the phone, and we've been doing this for Texas businesses since 2013.\n\n"
            "Wishing you the best either way.\n\n"
            "— Jordan Polasek, BVTech LLC"
        ),
    },
]


def sequence_length() -> int:
    return len(_SEQUENCE)


# --------------------------------------------------------------------------- #
# Config (secure_config-backed, same pattern as content_autopilot).
# --------------------------------------------------------------------------- #
def get_config(db: Session) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    raw = dict((conn.config if conn else None) or {})
    return {
        "enabled": bool(raw.get("enabled", False)),   # OFF until explicitly armed
        "target": int(raw.get("target", 100)),        # aggressive ceiling (ramped to)
        "sender": raw.get("sender") or "",            # From: address
        "reply_to": raw.get("reply_to") or raw.get("sender") or "",
        "physical_address": raw.get("physical_address") or "",  # CAN-SPAM: required
        "started_on": raw.get("started_on") or "",    # ISO date the ramp began
        "last": raw.get("last") or {},                # {date: sent_count}
        "test_sent_on": raw.get("test_sent_on") or "",  # last self-test date (v1.56)
    }


def save_config(db: Session, **fields) -> dict:
    cur = get_config(db)
    cur.update({k: v for k, v in fields.items() if v is not None})
    secure_config.upsert_platform(db, PROVIDER, "Outbound Campaign", "Growth", cur)
    return cur


# --------------------------------------------------------------------------- #
# Sequence-position tracking — derived from the CRM timeline (no new schema).
# --------------------------------------------------------------------------- #
def _sends(db: Session, contact_id: int) -> list[CrmActivity]:
    rows = (db.query(CrmActivity)
            .filter(CrmActivity.contact_id == contact_id,
                    CrmActivity.type == "email",
                    CrmActivity.direction == "outbound")
            .order_by(CrmActivity.created_at.asc()).all())
    return [r for r in rows if (r.meta or {}).get("campaign") == CAMPAIGN]


def _position(db: Session, contact_id: int) -> int:
    """How many sequence touches this contact has already received (0..N)."""
    return len(_sends(db, contact_id))


def _last_send_at(db: Session, contact_id: int) -> datetime | None:
    s = _sends(db, contact_id)
    if not s:
        return None
    dt = s[-1].created_at
    return dt if (dt is None or dt.tzinfo) else dt.replace(tzinfo=timezone.utc)


def _due(contact: CrmContact, position: int, last_at: datetime | None,
         now: datetime, gap_days: int) -> bool:
    if not contact.email or contact.do_not_contact:
        return False
    if (contact.status or "").lower() in SUPPRESSED_STATUS:
        return False
    if position >= len(_SEQUENCE):
        return False
    if position == 0:
        return True
    if last_at is None:
        return True
    return (now - last_at) >= timedelta(days=gap_days)


def select_due(db: Session, now: datetime, *, gap_days: int = GAP_DAYS,
               limit: int | None = None) -> list[tuple[CrmContact, int]]:
    """Best-first list of (contact, next_step_index) eligible to send TODAY."""
    q = db.query(CrmContact).filter(CrmContact.email.isnot(None),
                                    CrmContact.do_not_contact.is_(False))
    # best leads first: highest MSP-readiness score, then oldest untouched
    q = q.order_by(CrmContact.score.desc().nullslast()
                   if hasattr(CrmContact.score, "desc") else CrmContact.id.asc(),
                   CrmContact.created_at.asc())
    out: list[tuple[CrmContact, int]] = []
    for c in q.all():
        pos = _position(db, c.id)
        if _due(c, pos, _last_send_at(db, c.id), now, gap_days):
            out.append((c, pos))
            if limit is not None and len(out) >= limit:
                break
    return out


# --------------------------------------------------------------------------- #
# Rendering + compliance
# --------------------------------------------------------------------------- #
def compliant_footer(sender: str, physical_address: str) -> str:
    """CAN-SPAM: a valid physical postal address + a clear opt-out. Non-optional
    — run_daily refuses to send if physical_address is blank."""
    return ("\n\n—\n"
            f"{sender}\n{physical_address}\n"
            "You received this because we believe managed IT may help your "
            "business. Reply STOP or simply say the word and we'll never contact "
            "you again.")


def render(step_index: int, contact: CrmContact, sender: str,
           physical_address: str) -> tuple[str, str]:
    step = _SEQUENCE[step_index]
    subject = campaigns.personalize(step["subject"], contact)
    body = campaigns.personalize(step["body"], contact) + \
        compliant_footer(sender, physical_address)
    return subject, body


# --------------------------------------------------------------------------- #
# The daily engine
# --------------------------------------------------------------------------- #
def _today(now: datetime) -> str:
    return now.date().isoformat()


def run_daily(db: Session, send_fn, now: datetime | None = None, *,
              force: bool = False, dry_run: bool = False) -> dict:
    """Send today's outbound batch (one sequence step per eligible lead), capped
    by the warm-up ramp. Idempotent by daily-count; safe to tick repeatedly.

    send_fn(to, subject, body) -> None. Pass dry_run=True to plan without sending.
    """
    now = now or datetime.now(timezone.utc)
    cfg = get_config(db)
    if not force and not cfg["enabled"]:
        return {"ran": False, "reason": "disabled", "sent": 0}
    # Compliance gate — refuse to send cold email without the legally-required
    # physical address and a From: identity. This is a hard stop, not a warning.
    if not cfg["sender"] or not cfg["physical_address"]:
        return {"ran": False, "reason": "not_configured",
                "detail": "set sender + physical_address (CAN-SPAM) before enabling",
                "sent": 0}

    # Warm-up ramp: how many are we allowed to send today, total?
    started = cfg["started_on"] or _today(now)
    try:
        d0 = datetime.fromisoformat(started).date()
    except ValueError:
        d0 = now.date()
    day_index = (now.date() - d0).days
    cap = warmup_cap(day_index, cfg["target"])
    already = int((cfg["last"] or {}).get(_today(now), 0))
    remaining = max(0, cap - already)

    due = select_due(db, now, limit=remaining)
    sent, failed, errors, plan = 0, 0, [], []
    for contact, step in due:
        subject, body = render(step, contact, cfg["sender"], cfg["physical_address"])
        plan.append({"contact_id": contact.id, "email": contact.email,
                     "step": step, "subject": subject})
        if dry_run:
            continue
        try:
            send_fn(contact.email, subject, body)
        except Exception as e:  # noqa: BLE001
            failed += 1
            errors.append({"contact_id": contact.id, "error": str(e)[:160]})
            continue
        sent += 1
        crm.log_activity(db, contact, "email", subject=subject, body=body[:1000],
                         direction="outbound",
                         meta={"campaign": CAMPAIGN, "step": step}, commit=False)
        if (contact.status or "new").lower() in ("new", "lead", "prospect"):
            contact.status = "contacted"

    if not dry_run and (sent or failed):
        last = dict(cfg["last"] or {})
        last[_today(now)] = already + sent
        # keep only the last ~30 days of counters
        for k in sorted(last)[:-30]:
            last.pop(k, None)
        if not force or cfg["enabled"]:
            save_config(db, started_on=started, last=last)
        db.commit()

    return {"ran": True, "dry_run": dry_run, "day_index": day_index,
            "cap": cap, "already_sent_today": already, "remaining": remaining,
            "eligible": len(due), "sent": sent, "failed": failed,
            "plan": plan[:50], "errors": errors[:10]}


# --------------------------------------------------------------------------- #
# v1.56 TRANSPORT + HEARTBEAT GLUE — the engine above was fully built (ramp,
# sequence, compliance) but nothing ever CALLED it and no mail transport was
# wired in, so not one email had actually gone out. This closes the loop:
#   * resolve_send_fn — M365 Graph via the m365_mailbox credentials the box
#     already loads from env (client_id/client_secret/tenant_id/mailbox),
#     falling back to SMTP; None when neither is configured.
#   * tick — the heartbeat entrypoint. Armed by the portal config OR the box
#     env: PULSE_OUTBOUND=test|live.  TEST emails the day's would-be batch and
#     a full rendered sample to the shop's own inbox — no lead is ever touched.
#     LIVE runs the real ramped daily batch inside business hours (9am-6pm CT).
# --------------------------------------------------------------------------- #
def _graph_factory(tenant: str, client_id: str, client_secret: str):
    from .m365 import GraphClient
    return GraphClient(tenant, client_id, client_secret)


_GRAPH_FACTORY = _graph_factory   # test seam


def resolve_send_fn(db: Session):
    """(send_fn, detail). Prefers the M365 Graph mailbox, then SMTP; (None,
    why) when no transport is configured. Never raises."""
    conn = secure_config.get_platform(db, "m365_mailbox")
    cfg = dict((conn.config if conn else None) or {})
    tenant = secure_config.get_secret(cfg, "tenant_id") or cfg.get("tenant_id") or ""
    client_id = secure_config.get_secret(cfg, "client_id") or cfg.get("client_id") or ""
    client_secret = secure_config.get_secret(cfg, "client_secret") or ""
    mailbox = (cfg.get("mailbox") or "").strip()
    if tenant and client_id and client_secret and mailbox:
        graph = _GRAPH_FACTORY(str(tenant), str(client_id), str(client_secret))

        def _send_graph(to: str, subject: str, body: str) -> None:
            graph.send_mail(mailbox, [to], subject, body)

        return _send_graph, f"M365 Graph as {mailbox}"
    from ..core.config import get_settings
    if get_settings().email_enabled:
        from . import email as email_svc

        def _send_smtp(to: str, subject: str, body: str) -> None:
            if not email_svc.send(to, subject, body):
                raise RuntimeError("SMTP send failed")

        return _send_smtp, "SMTP"
    return None, ("no email transport — connect the M365 mailbox (Settings → "
                  "Mailbox) or set SMTP_HOST")


def _env_mode() -> str:
    import os
    return (os.environ.get("PULSE_OUTBOUND") or "off").strip().lower()


def _apply_env_defaults(db: Session, cfg: dict) -> dict:
    """Box .env can fully configure the program — sender defaults to the
    connected M365 mailbox, address/target from PULSE_OUTBOUND_* vars."""
    import os
    updates: dict = {}
    if not cfg["sender"]:
        conn = secure_config.get_platform(db, "m365_mailbox")
        mcfg = dict((conn.config if conn else None) or {})
        sender = (os.environ.get("PULSE_OUTBOUND_SENDER")
                  or mcfg.get("mailbox") or "").strip()
        if sender:
            updates["sender"] = sender
    if not cfg["physical_address"] and os.environ.get("PULSE_OUTBOUND_ADDRESS"):
        updates["physical_address"] = os.environ["PULSE_OUTBOUND_ADDRESS"].strip()
    if os.environ.get("PULSE_OUTBOUND_TARGET"):
        try:
            updates["target"] = int(os.environ["PULSE_OUTBOUND_TARGET"])
        except ValueError:
            pass
    return save_config(db, **updates) if updates else cfg


def _notify(db: Session, severity: str, message: str) -> None:
    try:
        from ..models import Notification
        db.add(Notification(client_id=None, target_user_id=None, kind="content",
                            severity=severity, message=message[:1000]))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()


def _self_test(db: Session, send_fn, transport: str, cfg: dict,
               now: datetime) -> dict:
    """TEST mode: email the day's would-be batch + a fully rendered sample to
    the shop's own inbox, once per day. No lead is ever emailed."""
    from ..core.config import get_settings
    today = _today(now)
    if cfg.get("test_sent_on") == today:
        return {"ran": False, "mode": "test", "reason": "test_already_sent_today"}
    if not cfg["sender"] or not cfg["physical_address"]:
        _notify(db, "warning",
                "📧 Outbound is in TEST mode but not configured yet — set the "
                "sender and the CAN-SPAM physical mailing address "
                "(PULSE_OUTBOUND_ADDRESS in the box .env, or Campaigns → "
                "Outbound config). No emails sent.")
        return {"ran": False, "mode": "test", "reason": "not_configured"}
    plan = run_daily(db, send_fn, now, force=True, dry_run=True)
    lines = [f"  {i+1}. {p['email']}  (step {p['step'] + 1}/3)  —  {p['subject']}"
             for i, p in enumerate(plan.get("plan") or [])][:15]
    sample_subject, sample_body = render(
        0, type("C", (), {"name": "Alex Carter", "company": "Carter & Co"})(),
        cfg["sender"], cfg["physical_address"])
    inbox = get_settings().SUPPORT_EMAIL
    body = (
        "PULSE OUTBOUND — TEST MODE (no leads were emailed)\n"
        "==================================================\n\n"
        f"Transport: {transport}\n"
        f"Eligible leads today: {plan.get('eligible', 0)} "
        f"(day-{plan.get('day_index', 0)} warm-up cap: {plan.get('cap', 0)})\n\n"
        "Today's would-be batch:\n" + ("\n".join(lines) or "  (none eligible yet — "
        "scrape leads in Growth → Prospecting)") + "\n\n"
        "----- SAMPLE EMAIL (touch 1 of 3, exactly as a lead would get it) -----\n\n"
        f"Subject: {sample_subject}\n\n{sample_body}\n\n"
        "-----------------------------------------------------------------------\n"
        "Happy with it? Set PULSE_OUTBOUND=live in the box .env (or enable in "
        "the portal) and the ramp starts at 20/day."
    )
    # v1.56.1 NEVER-SILENT: a failed Graph/SMTP send used to bubble up into the
    # heartbeat's blanket except and vanish — "no email, no error, retries
    # forever". Catch it HERE, tell the operator exactly what broke (a 403 is
    # almost always the Entra app missing the Mail.Send APPLICATION permission),
    # and do NOT stamp test_sent_on so the next tick retries automatically.
    try:
        send_fn(inbox, f"[Pulse test] Outbound preview — {plan.get('eligible', 0)} "
                       "leads ready, nothing sent", body)
    except Exception as e:  # noqa: BLE001
        m = str(e)
        hint = ""
        if any(t in m for t in ("403", "Forbidden", "Authorization_RequestDenied",
                                "ErrorAccessDenied")):
            hint = (" — this is almost always the Entra app missing the Mail.Send "
                    "APPLICATION permission (Microsoft Graph) with admin consent. "
                    "Entra admin center → App registrations → the mailbox app → "
                    "API permissions → add Microsoft Graph → Application → "
                    "Mail.Send → Grant admin consent.")
        _notify(db, "warning",
                f"📧 Outbound TEST email FAILED via {transport}: {m[:280]}{hint} "
                "Will retry automatically next tick.")
        return {"ran": False, "mode": "test", "reason": "send_failed",
                "error": m[:300], "transport": transport}
    save_config(db, test_sent_on=today)
    _notify(db, "info",
            f"📧 Outbound TEST email sent to {inbox}: {plan.get('eligible', 0)} "
            "leads eligible, full sample included. Flip PULSE_OUTBOUND=live to "
            "start the warm-up ramp (20/day, business hours).")
    return {"ran": True, "mode": "test", "test_sent_to": inbox,
            "eligible": plan.get("eligible", 0), "transport": transport}


def tick(db: Session, now: datetime | None = None) -> dict:
    """Heartbeat entrypoint. Modes (PULSE_OUTBOUND env, or portal `enabled`):
    off → nothing; test → daily self-test email only; live → real ramped sends
    inside business hours. Extra ticks are harmless (daily counters + stamps)."""
    now = now or datetime.now(timezone.utc)
    mode = _env_mode()
    cfg = get_config(db)
    if mode not in ("test", "live") and not cfg["enabled"]:
        return {"ran": False, "reason": "off"}
    cfg = _apply_env_defaults(db, cfg)
    send_fn, transport = resolve_send_fn(db)
    if send_fn is None:
        return {"ran": False, "reason": "no_transport", "detail": transport}
    if mode == "test" and not cfg["enabled"]:
        return _self_test(db, send_fn, transport, cfg, now)
    # LIVE — arm the portal flag once so counters/status all agree.
    if not cfg["enabled"]:
        cfg = save_config(db, enabled=True)
    # Cold email lands (and reads) best in business hours: 9am-6pm Central.
    if not (14 <= now.hour < 23):
        return {"ran": False, "reason": "outside_send_window",
                "detail": "sends run 9am-6pm Central"}
    # cheap early-out so the 2-minute heartbeat isn't rescanning the CRM all day
    already = int((cfg["last"] or {}).get(_today(now), 0))
    started = cfg["started_on"] or _today(now)
    try:
        day_index = (now.date() - datetime.fromisoformat(started).date()).days
    except ValueError:
        day_index = 0
    if already >= warmup_cap(day_index, cfg["target"]):
        return {"ran": False, "reason": "daily_cap_reached", "sent_today": already}
    out = run_daily(db, send_fn, now)
    out["transport"] = transport
    if out.get("sent") or out.get("failed"):
        _notify(db, "info" if not out.get("failed") else "warning",
                f"📬 Outbound: {out.get('sent', 0)} cold touch(es) sent today "
                f"(cap {out.get('cap')}, ramp day {out.get('day_index')}, "
                f"{out.get('failed', 0)} failed) via {transport}.")
    return out
