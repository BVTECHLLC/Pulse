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
                     "unsubscribed", "bounced", "do_not_contact",
                     # v1.58: a lead who REPLIED leaves the sequence instantly —
                     # the conversation is human now, not automated.
                     "replied"}

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
# v1.85: SHORT + punchy. The opener earns the first line, then it's benefit-led
# and skimmable — "happy with your IT provider? want to save money? give us a
# try." One clear CTA. Short cold emails that respect the inbox get read + replied.
_SEQUENCE = [
    {
        "step": 0,
        "subject": "{company} — happy with your IT provider?",
        "body": (
            "Hi {first},\n\n"
            "{opener}"
            "Quick question — are you happy with your current IT provider? Fast "
            "support, real security, a fair bill?\n\n"
            "Most Texas businesses we take on were paying more for slower service "
            "than they realized. We're BVTech — managed IT & cybersecurity, local, "
            "since 2013.\n\n"
            "Want to save money and get better coverage? Grab a free 15-minute "
            "look at {company}: bvtech.org/book\n\n"
            "— Jordan Polasek, BVTech LLC"
        ),
    },
    {
        "step": 1,
        "subject": "re: {company}'s IT — quick idea",
        "body": (
            "Hi {first},\n\n"
            "{value_para}\n\n"
            "We fix that — flat monthly pricing, faster response, real backup and "
            "security. Often for less than you pay now.\n\n"
            "Free 15-minute review of {company}, no strings: bvtech.org/book\n\n"
            "— Jordan, BVTech LLC"
        ),
    },
    {
        "step": 2,
        "subject": "last note, {first}",
        "body": (
            "Hi {first},\n\n"
            "Last note — I won't crowd your inbox.\n\n"
            "If {company}'s IT is handled, glad to hear it. If it ever isn't — an "
            "outage, a scare, a provider who stopped answering — we're local, we "
            "pick up the phone, and we've done this since 2013.\n\n"
            "Grab any 15-minute slot whenever it helps: bvtech.org/book\n\n"
            "— Jordan Polasek, BVTech LLC"
        ),
    },
]

# Touch 2's default value paragraph — used whenever the personalized domain
# snapshot (v1.59) has nothing concrete to report for this lead.
_VALUE_DEFAULT = (
    "Following up with something useful either way: the single cheapest "
    "security win for a small business is turning on multi-factor "
    "authentication everywhere — email, banking, remote access. It stops "
    "the vast majority of account takeovers and takes an afternoon.")


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
        "prospected_on": raw.get("prospected_on") or "",  # last auto-scrape date (v1.57)
        "prospect_cycle": int(raw.get("prospect_cycle") or 0),  # market×industry rotation
        "replies_checked_at": raw.get("replies_checked_at") or "",  # inbox watermark (v1.58)
        "scorecard_on": raw.get("scorecard_on") or "",  # last Monday scorecard date (v1.59)
        # v1.83: the operator's REAL branded signature (the bvtech.org-hosted one
        # with the gif) — full HTML, stored in the vault so it survives every
        # rebuild. When set it replaces the built-in CSS-tile signature.
        "signature_html": raw.get("signature_html") or "",
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
           physical_address: str, *, opener: str = "",
           value_para: str | None = None) -> tuple[str, str]:
    """v1.59: touch 1 takes an optional personalized opening line; touch 2
    takes an optional personalized value paragraph (the domain snapshot) —
    both collapse cleanly to the evergreen defaults when absent."""
    step = _SEQUENCE[step_index]
    subject = campaigns.personalize(step["subject"], contact)
    body = step["body"]
    op = (opener or "").strip()
    body = body.replace("{opener}", op + "\n\n" if op else "")
    body = body.replace("{value_para}", (value_para or _VALUE_DEFAULT).strip())
    body = campaigns.personalize(body, contact) + \
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
        # v1.59 personalization — REAL sends only (dry-run previews must stay
        # instant: no LLM calls, no DNS lookups from the status card).
        opener, value = "", None
        if not dry_run:
            if step == 0:
                opener = _opener_for(contact)
            elif step == 1 and contact.website:
                try:
                    value = _domain_snapshot(contact.website)
                except Exception:  # noqa: BLE001
                    value = None
        subject, body = render(step, contact, cfg["sender"], cfg["physical_address"],
                               opener=opener, value_para=value)
        plan.append({"contact_id": contact.id, "email": contact.email,
                     "step": step, "subject": subject})
        if dry_run:
            continue
        # v1.87 DELIVERABILITY GUARD: never email a dead domain — it just bounces
        # and burns the mailbox's sender reputation. Verify MX right before the
        # send; a failure retires the lead permanently (do_not_contact) so it's
        # never retried. The bounce watcher catches any live-domain mailbox that
        # still doesn't exist.
        from . import deliverability
        ok_send, why = deliverability.is_sendable(contact.email)
        if not ok_send:
            contact.do_not_contact = True
            contact.status = "invalid"
            # Log as a NOTE, not an email — it was NOT sent, so it must not count
            # as a send in the scorecard/CRM timeline.
            crm.log_activity(db, contact, "note", subject="(not sent — undeliverable)",
                             body=f"skipped: {why}", direction="outbound",
                             meta={"campaign": CAMPAIGN, "kind": "suppressed", "why": why},
                             commit=False)
            _hubspot_flag(db, contact.email, f"Pulse: undeliverable ({why}) — suppressed.")
            failed += 1
            errors.append({"contact_id": contact.id, "error": f"undeliverable ({why})"})
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


# --------------------------------------------------------------------------- #
# Branded HTML signature — v1.77. The old approach leaned on a server-side
# Exchange transport rule to staple a "photo/banner/socials" signature onto
# every message. That rule is invisible to this code, breaks silently, and the
# moment it stopped firing every email went out bare — the "lost banner". This
# bakes a self-contained, email-safe signature straight into the message so it
# ALWAYS renders: pure table + inline styles + a CSS-drawn logo tile (no
# external image to be blocked), so it looks identical in Outlook, Gmail, and
# Apple Mail whether or not the recipient loads remote images.
# --------------------------------------------------------------------------- #
def _signature_identity() -> dict:
    """Signature fields, overridable from the box .env but with defaults that
    always render so the banner can never go missing again."""
    import os
    return {
        "name":  os.environ.get("PULSE_SIG_NAME")  or "Jordan Polasek",
        "title": os.environ.get("PULSE_SIG_TITLE") or "Founder & Managing Partner",
        "company": os.environ.get("PULSE_SIG_COMPANY") or "BVTech LLC",
        "tagline": os.environ.get("PULSE_SIG_TAGLINE")
                   or "Managed IT & Cybersecurity for Texas businesses",
        "email": os.environ.get("PULSE_SIG_EMAIL") or "help@bvtech.org",
        "phone": os.environ.get("PULSE_SIG_PHONE") or "",
        "site":  os.environ.get("PULSE_SIG_SITE")  or "bvtech.org",
        "portal": os.environ.get("PULSE_SIG_PORTAL") or "portal.bvtech.org",
    }


def _html_signature() -> str:
    """A self-contained, images-off-safe HTML email signature. Brand navy/blue,
    a CSS-drawn BV logo tile, name/title/company, and tappable contact links."""
    s = _signature_identity()
    navy, blue, ink, mut = "#0b1f3a", "#2b7cff", "#1a2233", "#5b6472"
    rows = []
    rows.append(
        f'<a href="mailto:{s["email"]}" style="color:{blue};text-decoration:none">'
        f'{s["email"]}</a>')
    if s["phone"]:
        rows.append(f'<span style="color:{ink}">{s["phone"]}</span>')
    rows.append(
        f'<a href="https://{s["site"]}" style="color:{blue};text-decoration:none">'
        f'{s["site"]}</a>')
    rows.append(
        f'<a href="https://{s["portal"]}" style="color:{mut};text-decoration:none">'
        f'Client portal</a>')
    contact = ('&nbsp;&nbsp;·&nbsp;&nbsp;'.join(rows))
    return (
      '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
      'style="margin-top:22px;border-collapse:collapse;'
      "font-family:'Segoe UI',Calibri,Arial,sans-serif\">"
      '<tr>'
      # logo tile — drawn with CSS so it renders even with images blocked
      '<td valign="top" style="padding-right:16px">'
      f'<div style="width:52px;height:52px;border-radius:12px;background:{navy};'
      f'background:linear-gradient(135deg,{navy},{blue});text-align:center;'
      'line-height:52px;color:#ffffff;font-size:22px;font-weight:800;'
      "font-family:'Segoe UI',Arial,sans-serif;letter-spacing:.5px\">BV</div>"
      '</td>'
      # left brand rule + text block
      f'<td valign="top" style="border-left:3px solid {blue};padding-left:16px">'
      f'<div style="font-size:16px;font-weight:700;color:{ink};line-height:1.2">'
      f'{_H_ESC(s["name"])}</div>'
      f'<div style="font-size:13px;color:{mut};padding-top:2px">'
      f'{_H_ESC(s["title"])} · <span style="color:{ink};font-weight:600">'
      f'{_H_ESC(s["company"])}</span></div>'
      f'<div style="font-size:12px;color:{mut};font-style:italic;padding-top:4px">'
      f'{_H_ESC(s["tagline"])}</div>'
      f'<div style="font-size:12.5px;padding-top:8px;line-height:1.6">{contact}</div>'
      '</td></tr></table>')


def _H_ESC(v: str) -> str:
    import html as _h
    return _h.escape(v or "")


# v1.83: the operator's REAL signature wins. Sources, in order:
#   1. vault  — outbound config `signature_html` (survives every rebuild; set once
#               from the bvtech.org-hosted signature file with the gif)
#   2. env    — PULSE_SIG_HTML_URL: fetch the hosted signature (cached ~12h) so
#               editing the file on bvtech.org updates emails automatically
#   3. built-in CSS tile — the guaranteed floor so no email ever goes out bare.
_SIG_CACHE: dict = {"url": "", "html": "", "at": 0.0}


def _sig_from_env() -> str:
    import os
    import time
    import urllib.request
    url = (os.environ.get("PULSE_SIG_HTML_URL") or "").strip()
    if not url:
        return ""
    if _SIG_CACHE["url"] == url and _SIG_CACHE["html"] and \
            time.time() - _SIG_CACHE["at"] < 12 * 3600:
        return _SIG_CACHE["html"]
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "BVTech-Pulse/1.0 (+https://bvtech.org)"})
        with urllib.request.urlopen(req, timeout=10) as r:
            html_sig = r.read(200_000).decode("utf-8", errors="replace").strip()
        if "<" in html_sig:      # sanity: looks like markup, not an error page
            _SIG_CACHE.update({"url": url, "html": html_sig, "at": time.time()})
            return html_sig
    except Exception:  # noqa: BLE001 — unreachable host -> fall through
        pass
    return _SIG_CACHE["html"] if _SIG_CACHE["url"] == url else ""


# Sentinels that mean "append NOTHING — let the org's M365/Exchange signature
# rule staple the real branded signature on outbound mail." This is the right
# mode when the operator already has a working Exchange/Outlook signature (photo,
# banner, socials) — Pulse must not double it up with its own.
_SIG_OFF = {"off", "none", "disabled", "exchange", "m365", "outlook"}


def _text_to_html(text: str, custom_sig: str | None = None) -> str:
    """Render the message as HTML. The body keeps its exact line structure
    (pre-wrap, escaped byte-for-byte). The signature is: the operator's own HTML
    when set; NOTHING when set to an OFF sentinel (so the M365/Exchange rule
    appends the real one); the hosted env signature; else the built-in tile —
    so an email is never bare AND never double-signed."""
    raw = (custom_sig or "").strip()
    if raw.lower() in _SIG_OFF:
        sig = ""                                  # let Exchange append the real one
    else:
        sig = raw or _sig_from_env() or _html_signature()
    return ('<div style="font-family:\'Segoe UI\',Calibri,Arial,sans-serif;'
            'font-size:15px;color:#222222;line-height:1.5;white-space:pre-wrap">'
            + _H_ESC(text) + "</div>" + sig)


def _graph_and_mailbox(db: Session):
    """(GraphClient, mailbox) from the m365_mailbox creds, or None."""
    conn = secure_config.get_platform(db, "m365_mailbox")
    cfg = dict((conn.config if conn else None) or {})
    tenant = secure_config.get_secret(cfg, "tenant_id") or cfg.get("tenant_id") or ""
    client_id = secure_config.get_secret(cfg, "client_id") or cfg.get("client_id") or ""
    client_secret = secure_config.get_secret(cfg, "client_secret") or ""
    mailbox = (cfg.get("mailbox") or "").strip()
    if tenant and client_id and client_secret and mailbox:
        return _GRAPH_FACTORY(str(tenant), str(client_id), str(client_secret)), mailbox
    return None


def resolve_send_fn(db: Session):
    """(send_fn, detail). Prefers the M365 Graph mailbox, then SMTP; (None,
    why) when no transport is configured. Never raises."""
    gm = _graph_and_mailbox(db)
    if gm:
        graph, mailbox = gm
        # v1.83: resolve the operator's real signature once per send-fn build.
        custom_sig = (get_config(db).get("signature_html") or "").strip()

        def _send_graph(to: str, subject: str, body: str) -> None:
            graph.send_mail(mailbox, [to], subject,
                            _text_to_html(body, custom_sig), html=True)

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


def _hubspot_flag(db: Session, email: str, note: str) -> None:
    """v1.88 write-back: when Pulse suppresses (dead domain) or retires (bounced)
    a lead, flag the same HubSpot contact UNQUALIFIED so the source list
    self-cleans. Best-effort and fully optional — a no-op when HubSpot isn't
    connected, and it never raises into the send/reply path."""
    try:
        conn = secure_config.get_platform(db, "hubspot")
        cfg = dict((conn.config if conn else None) or {})
        token = secure_config.get_secret(cfg, "token") or cfg.get("token")
        if not token:
            return
        _HUBSPOT_CLIENT(str(token)).flag_unqualified(email, note)
    except Exception:  # noqa: BLE001
        pass


def _hs_client(token: str):
    from .hubspot import HubSpotClient
    return HubSpotClient(token)


_HUBSPOT_CLIENT = _hs_client       # test seam


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
    # v1.57 AUTO-PROSPECTING: whenever the program is armed (test OR live),
    # keep the lead tank full — once a day, scrape the next market×industry
    # rotation and enrich lead emails from their own websites. Runs before the
    # branches so even the test-mode preview fills with real leads.
    try:
        _ensure_leads(db, cfg, now)
    except Exception:  # noqa: BLE001
        db.rollback()
    # v1.58 REPLY WATCHER: listen to the mailbox — hot leads flagged, STOP
    # honored instantly, bounces retired. Every ~15 min, cheap watermark.
    try:
        _watch_replies(db, cfg, now)
    except Exception:  # noqa: BLE001
        db.rollback()
    # v1.59 SCORECARD: Monday-morning numbers to the shop inbox, once.
    try:
        _weekly_scorecard(db, send_fn, cfg, now)
    except Exception:  # noqa: BLE001
        db.rollback()
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


# --------------------------------------------------------------------------- #
# v1.57 AUTO-PROSPECTING — keep the lead tank full, hands-free.
#
# The gap this closes: Google Places returns phone/website/address but NEVER an
# email, so scraped leads could not be emailed and "eligible today" sat at 0
# forever unless someone hand-entered addresses. Two pieces:
#   * _ensure_leads — once a day while the program is armed: if the untouched
#     emailable pool is below ~3× today's cap, scrape the next market×industry
#     combo in a 52-step rotation (4 Texas metros × 13 MSP-ready verticals),
#     then run enrichment. PULSE_PROSPECT=off disables.
#   * enrich_emails — visit each scraped lead's own website (homepage, then
#     /contact) and extract their PUBLIC business contact email — mailto links
#     first, domain-matching addresses preferred, junk filtered. B2B contact
#     discovery from the business's own published pages.
# Both are seam-injected (places client / page fetcher) for offline testing.
# --------------------------------------------------------------------------- #
POOL_LOW_FACTOR = 3          # top up when untouched pool < 3× today's cap
PROSPECT_BATCH = 25          # max new leads per daily scrape
ENRICH_BATCH = 25            # max websites visited per daily enrichment pass

_EMAIL_RX = None             # compiled lazily (module import stays cheap)
_JUNK_EMAIL = ("example.", "sentry", "wixpress", "@2x", "noreply", "no-reply",
               "donotreply", "yourdomain", "domain.com", "email.com", ".png",
               ".jpg", ".jpeg", ".gif", ".webp", ".svg")


def _places_factory(key: str):
    from .prospecting import PlacesClient
    return PlacesClient(key)


_PLACES_FACTORY = _places_factory     # test seam


def _overpass_factory():
    """FREE, no-key lead source (OpenStreetMap). Used when Google Places isn't
    configured so the tank fills — and cold email actually sends — at $0 cost."""
    from .prospecting import OverpassClient
    return OverpassClient()


_OVERPASS_FACTORY = _overpass_factory  # test seam


def _fetch_page(url: str) -> str:
    """Fetch one public web page (the lead's own site). Small, tolerant, capped."""
    import urllib.request
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; BVTech-Pulse/1.0; +https://bvtech.org)"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return r.read(400_000).decode("utf-8", errors="replace")


_FETCH_PAGE = _fetch_page             # test seam


def _extract_email(html_text: str, site_host: str) -> str | None:
    """Best public contact email on a page: mailto first, own-domain preferred,
    then the classic info@/contact@/office@ shapes; junk filtered."""
    import re as _re
    global _EMAIL_RX
    if _EMAIL_RX is None:
        _EMAIL_RX = _re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
    mailtos = _re.findall(r'mailto:([^"\'\s?>]+)', html_text, _re.I)
    everywhere = _EMAIL_RX.findall(html_text)
    seen, ordered = set(), []
    for e in [m.strip().lower() for m in mailtos + everywhere]:
        if e and e not in seen and _EMAIL_RX.fullmatch(e):
            seen.add(e)
            ordered.append(e)
    ordered = [e for e in ordered if not any(j in e for j in _JUNK_EMAIL)]
    if not ordered:
        return None
    host = (site_host or "").lower().removeprefix("www.")
    if host:
        same = [e for e in ordered if e.rsplit("@", 1)[-1].removeprefix("www.")
                in (host, "www." + host)]
        if same:
            return same[0]
    for pref in ("info@", "contact@", "office@", "hello@", "admin@", "sales@"):
        for e in ordered:
            if e.startswith(pref):
                return e
    return ordered[0]


def enrich_emails(db: Session, limit: int = ENRICH_BATCH, fetcher=None) -> dict:
    """Fill in missing emails for scraped leads from their own websites.
    fetcher(url)->html is injectable; failures skip quietly (site down ≠ error)."""
    from urllib.parse import urlparse
    fetch = fetcher or _FETCH_PAGE
    rows = (db.query(CrmContact)
            .filter(CrmContact.email.is_(None), CrmContact.website.isnot(None),
                    CrmContact.do_not_contact.is_(False))
            .order_by(CrmContact.score.desc().nullslast()
                      if hasattr(CrmContact.score, "desc") else CrmContact.id.asc())
            .limit(max(1, limit)).all())
    found, checked = 0, 0
    for c in rows:
        checked += 1
        site = (c.website or "").strip()
        if not site.startswith(("http://", "https://")):
            site = "https://" + site
        host = urlparse(site).netloc
        email = None
        for candidate in (site, site.rstrip("/") + "/contact"):
            try:
                email = _extract_email(fetch(candidate), host)
            except Exception:  # noqa: BLE001 — dead site/timeouts are normal
                email = None
            if email:
                break
        if email:
            c.email = email
            found += 1
    if found:
        db.commit()
    return {"checked": checked, "emails_found": found}


def _untouched_pool(db: Session) -> int:
    """Emailable leads that haven't been touched yet (status still 'new')."""
    return (db.query(CrmContact)
            .filter(CrmContact.email.isnot(None),
                    CrmContact.do_not_contact.is_(False),
                    CrmContact.status == "new").count())


def _ensure_leads(db: Session, cfg: dict, now: datetime) -> dict:
    """Once a day while armed: scrape the next rotation combo when the pool is
    low, then enrich emails. Never raises (tick wraps it anyway)."""
    import os
    if (os.environ.get("PULSE_PROSPECT") or "").strip().lower() in ("off", "0", "false"):
        return {"ran": False, "reason": "disabled"}
    today = _today(now)
    if cfg.get("prospected_on") == today:
        return {"ran": False, "reason": "already_today"}
    # Prefer Google Places when a key is configured (richer ratings/reviews);
    # otherwise use the FREE, no-key OpenStreetMap source so the tank still fills
    # and cold email actually goes out at $0 API cost. Both feed the same
    # scrape→score→enrich→email pipeline.
    conn = secure_config.get_platform(db, "google_places")
    pcfg = dict((conn.config if conn else None) or {})
    key = secure_config.get_secret(pcfg, "api_key") or ""
    source = "places" if key else "free"
    # today's cap decides how full the tank should be
    started = cfg.get("started_on") or today
    try:
        day_index = (now.date() - datetime.fromisoformat(started).date()).days
    except ValueError:
        day_index = 0
    cap = warmup_cap(day_index, int(cfg.get("target") or 100))
    pool = _untouched_pool(db)
    scraped = {"created": 0, "market": "", "industry": ""}
    if pool < cap * POOL_LOW_FACTOR:
        from . import prospecting
        combos = [(m, i["query"]) for m in prospecting.MARKETS
                  for i in prospecting.INDUSTRIES]
        cycle = int(cfg.get("prospect_cycle") or 0)
        market, industry = combos[cycle % len(combos)]
        try:
            client = _PLACES_FACTORY(key) if key else _OVERPASS_FACTORY()
            scraped = prospecting.run(db, client, market, industry,
                                      max_results=PROSPECT_BATCH)
        except Exception as e:  # noqa: BLE001
            _notify(db, "warning",
                    f"🎯 Auto-prospecting hit a problem ({market}/{industry}, "
                    f"{source} source): {str(e)[:200]} — will try the next combo "
                    "tomorrow.")
        save_config(db, prospect_cycle=cycle + 1)
    enriched = {"checked": 0, "emails_found": 0}
    try:
        enriched = enrich_emails(db)
    except Exception:  # noqa: BLE001
        db.rollback()
    save_config(db, prospected_on=today)
    if scraped.get("created") or enriched.get("emails_found"):
        src_label = "Google Places" if source == "places" else "free OpenStreetMap"
        _notify(db, "info",
                f"🎯 Lead tank ({src_label}): +{scraped.get('created', 0)} new "
                f"{scraped.get('market', '')} {scraped.get('industry', '')} lead(s) "
                f"scraped, {enriched.get('emails_found', 0)} email(s) found on their "
                f"websites — emailable untouched pool now {_untouched_pool(db)}.")
    return {"ran": True, "source": source, "scraped": scraped.get("created", 0),
            "enriched": enriched.get("emails_found", 0),
            "pool": _untouched_pool(db)}


# --------------------------------------------------------------------------- #
# v1.58 REPLY WATCHER — the machine can talk; now it listens.
#
# Scans the sending mailbox's inbox (Mail.Read is granted on the mailbox app):
#   * a campaign-touched lead REPLIES  -> status "replied", sequence stops
#     instantly (SUPPRESSED_STATUS), 🔥 notification — a human takes over.
#   * reply says STOP/unsubscribe      -> do_not_contact + "unsubscribed",
#     honored automatically (CAN-SPAM requires it; we do it in minutes).
#   * bounce (mailer-daemon) naming a lead -> "bounced", never emailed again —
#     protects the domain's sender reputation.
# Every inbound is logged to the lead's CRM timeline. Watermarked so each
# message is processed once; runs at most every REPLY_SCAN_MINUTES.
# --------------------------------------------------------------------------- #
REPLY_SCAN_MINUTES = 15

_STOP_RX = None


def _is_stop(subject: str, preview: str) -> bool:
    """Opt-out detection with a guard against eating hot leads: explicit forms
    (unsubscribe / opt out / remove me / do not email...) match anywhere, but a
    bare 'stop' only counts when the REPLY BODY leads with it — real opt-outs
    are terse ('STOP', 'stop emailing me'); 'can't stop praising you' is not
    an unsubscribe."""
    import re as _re
    global _STOP_RX
    if _STOP_RX is None:
        _STOP_RX = _re.compile(
            r"\b(unsubscribe|opt[ -]?out|remove me|take me off"
            r"|stop (?:email|send|contact)\w*"
            r"|do not (?:email|contact)|don'?t (?:email|contact))\b", _re.I)
    if _STOP_RX.search(f"{subject or ''} {preview or ''}"):
        return True
    return bool(_re.match(r"\s*stop\b", preview or "", _re.I))


_NDR_SUBJECT_RX = None


def _re_ndr_subject(subject: str) -> bool:
    """Classic delivery-failure subjects (Microsoft/Google/generic NDRs)."""
    import re as _re
    global _NDR_SUBJECT_RX
    if _NDR_SUBJECT_RX is None:
        _NDR_SUBJECT_RX = _re.compile(
            r"\b(undeliverable|delivery has failed|delivery status notification"
            r"|delivery failure|returned mail|mail delivery failed|failure notice"
            r"|message not delivered|address not found|could not be delivered)\b",
            _re.I)
    return bool(_NDR_SUBJECT_RX.search(subject or ""))


def _parse_iso(ts: str):
    try:
        return datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def _watch_replies(db: Session, cfg: dict, now: datetime) -> dict:
    last = cfg.get("replies_checked_at") or ""
    last_dt = _parse_iso(last)
    if last_dt and (now - last_dt).total_seconds() < REPLY_SCAN_MINUTES * 60:
        return {"ran": False, "reason": "recently_checked"}
    gm = _graph_and_mailbox(db)
    if not gm:
        return {"ran": False, "reason": "no_graph"}
    graph, mailbox = gm
    try:
        msgs = graph.list_messages(mailbox, "inbox", top=25)
    except Exception as e:  # noqa: BLE001
        return {"ran": False, "reason": "scan_failed", "error": str(e)[:200]}
    save_config(db, replies_checked_at=now.isoformat())
    hot, stops, bounced = [], [], []
    for m in msgs:
        rec_dt = _parse_iso(m.get("received") or "")
        if last_dt and rec_dt and rec_dt <= last_dt:
            continue                     # already processed in an earlier scan
        sender = ((m.get("from") or {}).get("address") or "").strip().lower()
        text = f"{m.get('subject') or ''} {m.get('preview') or ''}"
        if not sender:
            continue
        # v1.87: broaden NDR detection. Microsoft/Exchange bounces don't always
        # come from a "postmaster@" address — the display name is often "Microsoft
        # Outlook" — so also treat a message as an NDR when the SUBJECT is a classic
        # delivery-failure notice, regardless of sender.
        _is_ndr = (sender.startswith(("mailer-daemon", "postmaster"))
                   or "mailer-daemon" in sender or "microsoftexchange" in sender
                   or _re_ndr_subject(m.get("subject") or ""))
        if _is_ndr:
            # NDR: find which campaign lead bounced by their address in the text
            tl = text.lower()
            for c in (db.query(CrmContact)
                      .filter(CrmContact.email.isnot(None)).all()):
                if c.email and c.email.lower() in tl and _position(db, c.id) > 0:
                    c.status = "bounced"
                    c.do_not_contact = True   # v1.87: retire permanently, never retry
                    _hubspot_flag(db, c.email, "Pulse: email bounced — retired.")
                    bounced.append(c.company or c.name)
                    crm.log_activity(db, c, "email", subject="(bounce)",
                                     body=text[:500], direction="inbound",
                                     meta={"campaign": CAMPAIGN, "kind": "bounce"},
                                     commit=False)
            continue
        c = (db.query(CrmContact)
             .filter(CrmContact.email.ilike(sender)).first())
        if not c or _position(db, c.id) == 0:
            continue                     # not a campaign-touched lead
        if _is_stop(m.get("subject") or "", m.get("preview") or ""):
            c.do_not_contact = True
            c.status = "unsubscribed"
            stops.append(c.company or c.name)
            kind = "stop"
        else:
            c.status = "replied"
            hot.append((c.name, c.company))
            kind = "reply"
        crm.log_activity(db, c, "email", subject=m.get("subject") or "(reply)",
                         body=(m.get("preview") or "")[:500], direction="inbound",
                         meta={"campaign": CAMPAIGN, "kind": kind}, commit=False)
    if hot or stops or bounced:
        db.commit()
    for name, company in hot:
        _notify(db, "info",
                f"🔥 HOT LEAD: {name} ({company}) replied to the outreach — "
                f"the sequence stopped itself; go close them in {mailbox}.")
    if stops:
        _notify(db, "info",
                f"✋ Opt-out honored automatically for: {', '.join(stops[:5])}"
                f"{' …' if len(stops) > 5 else ''} — marked do-not-contact.")
    if bounced:
        _notify(db, "info",
                f"↩️ {len(bounced)} bounce(s) retired from the sequence: "
                f"{', '.join(bounced[:5])}.")
    return {"ran": True, "hot": len(hot), "stops": len(stops),
            "bounced": len(bounced), "scanned": len(msgs)}


# --------------------------------------------------------------------------- #
# v1.59 CONVERSION LAYER — from "cold email that sends" to "cold email that
# gets replies":
#   * _opener_for      — one specific, warm first line written by the FREE LLM
#     from the facts captured at scrape time (rating, reviews, vertical, metro).
#     Hard-validated; collapses to the evergreen intro on any doubt.
#   * _domain_snapshot — a REAL outside-only finding about the lead's own
#     domain (public DNS: DMARC/SPF) for touch 2. Proof of competence instead
#     of a claim of it. No finding -> the evergreen MFA tip.
#   * _weekly_scorecard — Monday morning: sends / replies / opt-outs / bounces
#     by vertical for the last 7 days, emailed to the shop inbox, so the
#     rotation can be aimed at what actually bites.
# --------------------------------------------------------------------------- #
_OPENER_SYSTEM = (
    "You write exactly ONE short opening sentence for a polite cold email from "
    "Jordan, founder of BVTech (a Texas IT/MSP company), to a local business. "
    "Use the facts given — be specific, warm, and professional. No flattery "
    "overload, no exclamation marks, no links, no emoji, 25 words max, plain "
    "text only, no surrounding quotes. Never mention El Campo.")


def _opener_for(contact: CrmContact) -> str:
    """LLM-personalized first line; '' (evergreen intro) on any doubt."""
    try:
        from . import ai
        vertical = (contact.tags or ["local business"])[0]
        facts = (f"Business: {contact.company or contact.name}; type: {vertical}; "
                 f"metro: {contact.market or 'Texas'}; {contact.notes or 'no other facts'}")
        line = (ai.complete(_OPENER_SYSTEM, facts, smart=False, max_tokens=70)
                or "").strip().strip('"').strip()
        if (15 <= len(line) <= 170 and "\n" not in line
                and "http" not in line.lower() and "el campo" not in line.lower()
                and not line.endswith(":")):
            return line
    except Exception:  # noqa: BLE001
        pass
    return ""


def _doh_txt(name: str) -> list[str]:
    """Public DNS-over-HTTPS TXT lookup (Cloudflare resolver)."""
    import json as _json
    import urllib.request
    req = urllib.request.Request(
        f"https://cloudflare-dns.com/dns-query?name={name}&type=TXT",
        headers={"accept": "application/dns-json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        d = _json.loads(r.read().decode())
    return [(a.get("data") or "").strip('"') for a in (d.get("Answer") or [])]


_DOH_TXT = _doh_txt                    # test seam


def _domain_snapshot(website: str) -> str | None:
    """One concrete, verifiable email-security finding about the lead's own
    domain — passive public-DNS checks only. None when their setup looks fine."""
    from urllib.parse import urlparse
    site = website if website.startswith(("http://", "https://")) else "https://" + website
    host = urlparse(site).netloc.removeprefix("www.")
    if not host or "." not in host:
        return None
    dmarc = [t for t in _DOH_TXT(f"_dmarc.{host}") if "v=dmarc1" in t.lower()]
    spf = [t for t in _DOH_TXT(host) if "v=spf1" in t.lower()]
    if not dmarc:
        finding = (f"{host} has no DMARC record — which means scammers can send "
                   "email that looks exactly like it comes from your team, to "
                   "your own clients and vendors, and nothing stops it")
    elif "p=none" in dmarc[0].lower().replace(" ", ""):
        finding = (f"{host}'s DMARC policy is set to 'none', so email that FAILS "
                   "authentication still gets delivered as if it were yours")
    elif not spf:
        finding = (f"{host} has no SPF record, so receiving mail servers can't "
                   "verify that your legitimate email is really from you")
    else:
        return None
    return ("Following up with something I actually checked rather than a canned "
            f"tip: I ran an outside-only look at your domain and found that "
            f"{finding}. It's usually fixable in an afternoon — I'll show you "
            "how at no charge, whether or not we ever work together.")


def _weekly_scorecard(db: Session, send_fn, cfg: dict, now: datetime) -> dict:
    """Monday: last-7-days outbound numbers by vertical, to the shop inbox."""
    if now.weekday() != 0:
        return {"ran": False, "reason": "not_monday"}
    today = _today(now)
    if cfg.get("scorecard_on") == today:
        return {"ran": False, "reason": "already_sent"}
    since = now - timedelta(days=7)
    acts = (db.query(CrmActivity)
            .filter(CrmActivity.type == "email", CrmActivity.created_at >= since).all())
    camp = [a for a in acts if (a.meta or {}).get("campaign") == CAMPAIGN]
    sends = [a for a in camp if a.direction == "outbound"]
    inbound = [a for a in camp if a.direction == "inbound"]
    replies = [a for a in inbound if (a.meta or {}).get("kind") == "reply"]
    stops = [a for a in inbound if (a.meta or {}).get("kind") == "stop"]
    bounces = [a for a in inbound if (a.meta or {}).get("kind") == "bounce"]
    ids = {a.contact_id for a in camp}
    verts: dict = {}
    if ids:
        for c in db.query(CrmContact).filter(CrmContact.id.in_(ids)).all():
            verts[c.id] = (c.tags or ["(untagged)"])[0]
    by_vert: dict = {}
    for a in sends:
        v = verts.get(a.contact_id, "(untagged)")
        by_vert.setdefault(v, [0, 0])[0] += 1
    for a in replies:
        v = verts.get(a.contact_id, "(untagged)")
        by_vert.setdefault(v, [0, 0])[1] += 1
    rate = (100 * len(replies) / len(sends)) if sends else 0.0
    lines = [f"  {v}:  {s} sent, {r} replies" for v, (s, r) in
             sorted(by_vert.items(), key=lambda kv: -kv[1][1])]
    body = (
        "PULSE OUTBOUND — WEEKLY SCORECARD (last 7 days)\n"
        "===============================================\n\n"
        f"Touches sent:   {len(sends)}\n"
        f"Replies:        {len(replies)}  ({rate:.1f}% reply rate)\n"
        f"Opt-outs:       {len(stops)} (honored automatically)\n"
        f"Bounces:        {len(bounces)} (retired automatically)\n\n"
        "By vertical:\n" + ("\n".join(lines) or "  (no sends this week)") + "\n\n"
        "Replies win deals — every 🔥 notification is a warm conversation "
        "waiting in the inbox. Verticals with replies above are where the "
        "rotation is biting; tell Pulse if you want to focus them."
    )
    from ..core.config import get_settings
    inbox = get_settings().SUPPORT_EMAIL
    try:
        send_fn(inbox, f"[Pulse] Weekly outbound scorecard — {len(sends)} sent, "
                       f"{len(replies)} replies", body)
    except Exception as e:  # noqa: BLE001
        return {"ran": False, "reason": "send_failed", "error": str(e)[:200]}
    save_config(db, scorecard_on=today)
    _notify(db, "info", f"📊 Weekly outbound scorecard sent to {inbox}: "
                        f"{len(sends)} touches, {len(replies)} replies "
                        f"({rate:.1f}%), {len(stops)} opt-outs, {len(bounces)} bounces.")
    return {"ran": True, "sends": len(sends), "replies": len(replies),
            "stops": len(stops), "bounces": len(bounces)}
