"""BVTech Inbox Guardian (v1.122) — an in-house AI email filter.

Reads a Microsoft 365 mailbox (e.g. help@bvtech.org) via Graph, has our free LLM
read each new message and decide whether it should reach the owner's inbox or be
set aside as an unwanted solicitation/spam, and (when enabled) moves the filtered
ones into a dedicated "BVTech Filtered" folder — so Outlook stays clean.

Design goals from the owner:
  * Be WISE and ERR TOWARD KEEPING real people — clients (AT&T, law firms, the
    2A/firearms businesses, partners, vendors we use) and genuine inquiries all
    get through easily. Anyone we already correspond with is whitelisted.
  * Filter cold solicitations aggressively — "rank your site", marketing/SEO/
    web-design pitches, bought lead lists, crypto/forex, fake invoices, bulk
    outreach. If it looks like soliciting, we're not interested.
  * Safe by default: DRY-RUN classifies and records but moves nothing until the
    owner flips it on from the portal. Reversible (everything moves to a folder,
    never deleted).
  * Reusable: all state is per-provider config, so the same engine can be offered
    to BVTech clients as a managed service later.

Deterministic fallbacks: a known sender is kept without spending a token; if the
LLM is unreachable a message is marked REVIEW (never auto-junked), so nothing
real is ever lost.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import secure_config

PROVIDER = "email_filter"
FILTERED_FOLDER = "BVTech Filtered"
MAX_RECENT = 120          # verdicts kept for the portal review list


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def get_config(db: Session) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    raw = dict((conn.config if conn else None) or {})
    return {
        "enabled": bool(raw.get("enabled", False)),        # master on/off (scanning)
        "apply": bool(raw.get("apply", False)),            # actually MOVE mail (vs dry-run)
        "mailbox": raw.get("mailbox") or "help@bvtech.org",
        "tenant": raw.get("tenant") or "bvtech.org",
        "aggressiveness": raw.get("aggressiveness") or "balanced",  # lenient|balanced|strict
        "allow": [a.lower() for a in (raw.get("allow") or [])],     # emails/domains always kept
        "block": [b.lower() for b in (raw.get("block") or [])],     # emails/domains always filtered
        "recent": list(raw.get("recent") or []),            # [{id,subject,from,verdict,category,reason,at,moved}]
        "stats": dict(raw.get("stats") or {}),
        "last_scan": raw.get("last_scan"),
        "last_error": raw.get("last_error"),
        "_raw": raw,
    }


def save_config(db: Session, **fields) -> dict:
    cur = get_config(db)["_raw"]
    cur.update(fields)
    secure_config.upsert_platform(db, PROVIDER, "Inbox Guardian (AI email filter)",
                                  "Productivity", cur)
    return cur


def set_setting(db: Session, **kw) -> dict:
    """Update simple settings (enabled/apply/aggressiveness/mailbox/tenant)."""
    allowed = {"enabled", "apply", "aggressiveness", "mailbox", "tenant"}
    fields = {k: v for k, v in kw.items() if k in allowed and v is not None}
    return save_config(db, **fields)


def add_sender(db: Session, email: str, where: str) -> dict:
    """where = 'allow' or 'block'. Accepts a full email or a bare domain."""
    cfg = get_config(db)
    e = (email or "").strip().lower()
    if not e or where not in ("allow", "block"):
        return cfg
    lst = set(cfg[where])
    lst.add(e)
    other = "block" if where == "allow" else "allow"
    oth = [x for x in cfg[other] if x != e]       # moving to one list removes it from the other
    return save_config(db, **{where: sorted(lst), other: oth})


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
_SYSTEM = (
    "You are the inbox triage assistant for BVTech LLC, a Texas managed-IT and "
    "cybersecurity company. Decide whether an incoming email should reach the "
    "owner's Outlook inbox (KEEP) or be set aside as an unwanted solicitation or "
    "spam (JUNK), or REVIEW when unsure.\n"
    "ERR STRONGLY TOWARD KEEP for anything that could be a real person: existing "
    "or prospective clients, a business asking for IT/cybersecurity help, law "
    "firms, telecom/AT&T, firearms/2A businesses, partners, vendors we use, "
    "recruiters for a real role, and personal mail. A human who wants to BUY our "
    "services or get support is KEEP — that is not soliciting.\n"
    "JUNK is for clear cold SOLICITATIONS and spam only: agencies pitching SEO, "
    "marketing, web design, app/software dev, 'rank your website', 'we found "
    "issues with your site', lead-generation or bought lead lists, SMM/backlinks, "
    "crypto/forex/investment, loans/debt, fake invoices or gift cards, and "
    "obvious automated bulk outreach. When genuinely unsure, choose REVIEW, "
    "never JUNK.\n"
    'Reply with ONE line of JSON only: {"verdict":"keep|review|junk",'
    '"category":"client|prospect|partner|vendor|personal|recruiter|newsletter|solicitor|spam",'
    '"reason":"<=8 words","confidence":0-100}'
)


def _domain(addr: str) -> str:
    return (addr or "").split("@")[-1].strip().lower().rstrip(".")


def _listed(addr: str, items: list[str]) -> bool:
    a = (addr or "").strip().lower()
    d = _domain(a)
    return bool(a) and (a in items or d in items)


def classify(msg: dict, cfg: dict, known_senders: set[str]) -> dict:
    """Return a verdict dict for one message summary. Deterministic for known/
    allow/block senders; AI for the rest; REVIEW if the AI is down."""
    frm = ((msg.get("from") or {}).get("address") or "").lower()
    dom = _domain(frm)
    if _listed(frm, cfg["block"]):
        return {"verdict": "junk", "category": "solicitor", "reason": "blocklisted sender",
                "confidence": 100, "by": "rule"}
    if _listed(frm, cfg["allow"]) or frm in known_senders or dom in known_senders:
        return {"verdict": "keep", "category": "client", "reason": "known / allowlisted",
                "confidence": 100, "by": "rule"}
    # AI triage
    from . import ai
    user = (f"From: {(msg.get('from') or {}).get('name','')} <{frm}>\n"
            f"Subject: {msg.get('subject','')}\n"
            f"Preview: {(msg.get('preview') or '')[:600]}")
    if cfg.get("aggressiveness") == "strict":
        user += "\n(Owner setting: STRICT — filter borderline marketing too.)"
    elif cfg.get("aggressiveness") == "lenient":
        user += "\n(Owner setting: LENIENT — only filter obvious spam.)"
    try:
        raw = ai.complete(_SYSTEM, user, max_tokens=120)
    except Exception:  # noqa: BLE001 — never auto-junk without the model
        return {"verdict": "review", "category": "prospect", "reason": "AI unavailable",
                "confidence": 0, "by": "fallback"}
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {"verdict": "review", "category": "prospect", "reason": "unparsed",
                "confidence": 0, "by": "fallback"}
    try:
        d = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return {"verdict": "review", "category": "prospect", "reason": "unparsed",
                "confidence": 0, "by": "fallback"}
    v = str(d.get("verdict", "review")).lower()
    if v not in ("keep", "review", "junk"):
        v = "review"
    return {"verdict": v, "category": str(d.get("category", "prospect"))[:20],
            "reason": str(d.get("reason", ""))[:60],
            "confidence": int(d.get("confidence") or 0), "by": "ai"}


# --------------------------------------------------------------------------- #
# Known senders (whitelist from the CRM — people we already talk to)
# --------------------------------------------------------------------------- #
def known_senders(db: Session) -> set[str]:
    out: set[str] = set()
    try:
        from ..models import CrmContact
        for (email,) in db.query(CrmContact.email).filter(CrmContact.email.isnot(None)):
            e = (email or "").strip().lower()
            if "@" in e:
                out.add(e)
                # also trust the whole domain of a real client (not free webmail)
                from . import email_guard
                d = _domain(e)
                if d and d not in email_guard.ALLOW:
                    out.add(d)
    except Exception:  # noqa: BLE001
        pass
    return out


# --------------------------------------------------------------------------- #
# Scan
# --------------------------------------------------------------------------- #
def _graph(cfg: dict):
    from .m365 import GraphClient
    return GraphClient(cfg["tenant"])


def status(db: Session) -> dict:
    """Light health check for the portal (does the mailbox connect?)."""
    cfg = get_config(db)
    out = {k: cfg[k] for k in ("enabled", "apply", "mailbox", "tenant",
                               "aggressiveness", "allow", "block", "stats", "last_scan",
                               "last_error")}
    out["recent"] = cfg["recent"][:MAX_RECENT]
    try:
        _graph(cfg).ping()
        out["connected"] = True
    except Exception as e:  # noqa: BLE001
        out["connected"] = False
        out["connect_error"] = str(e)[:200]
    return out


def scan(db: Session, *, limit: int = 25) -> dict:
    """Fetch recent inbox messages, classify the ones we haven't seen, record the
    verdicts, and (when apply=True) move JUNK into the filtered folder. Safe to
    call repeatedly; dedupes by message id."""
    cfg = get_config(db)
    if not cfg["enabled"]:
        return {"ok": False, "reason": "disabled"}
    try:
        g = _graph(cfg)
        msgs = g.list_messages(cfg["mailbox"], folder="inbox", top=min(50, max(5, limit)))
    except Exception as e:  # noqa: BLE001
        save_config(db, last_error=str(e)[:200], last_scan=_now_iso())
        return {"ok": False, "error": str(e)[:200]}

    seen = {r["id"] for r in cfg["recent"]}
    known = known_senders(db)
    folder_id = None
    counts = {"keep": 0, "review": 0, "junk": 0, "moved": 0, "new": 0}
    new_rows: list[dict] = []
    for m in msgs:
        mid = m.get("id")
        if not mid or mid in seen:
            continue
        counts["new"] += 1
        v = classify(m, cfg, known)
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
        moved = False
        if v["verdict"] == "junk" and cfg["apply"]:
            try:
                if folder_id is None:
                    folder_id = g.ensure_folder(cfg["mailbox"], FILTERED_FOLDER)
                if folder_id:
                    g.move_message(cfg["mailbox"], mid, folder_id)
                    moved = True
                    counts["moved"] += 1
            except Exception:  # noqa: BLE001 — a move failure never loses the mail
                moved = False
        new_rows.append({
            "id": mid, "subject": (m.get("subject") or "")[:140],
            "from": (m.get("from") or {}).get("address", ""),
            "from_name": (m.get("from") or {}).get("name", "")[:80],
            "verdict": v["verdict"], "category": v["category"], "reason": v["reason"],
            "confidence": v["confidence"], "by": v["by"], "moved": moved,
            "received": m.get("received"), "at": _now_iso(),
        })

    recent = (new_rows + cfg["recent"])[:MAX_RECENT]
    stats = dict(cfg["stats"])
    for k in ("keep", "review", "junk", "moved"):
        stats[k] = int(stats.get(k, 0)) + counts.get(k, 0)
    save_config(db, recent=recent, stats=stats, last_scan=_now_iso(), last_error=None)
    return {"ok": True, "mode": "apply" if cfg["apply"] else "dry-run", **counts}


def maybe_run(db: Session, now: datetime | None = None, *, every_min: int = 10) -> dict:
    """Heartbeat hook: scan at most once every `every_min` minutes when enabled."""
    cfg = get_config(db)
    if not cfg["enabled"]:
        return {"ran": False, "reason": "disabled"}
    last = cfg.get("last_scan")
    if last:
        try:
            dt = datetime.fromisoformat(last)
            if (datetime.now(timezone.utc) - dt).total_seconds() < every_min * 60:
                return {"ran": False, "reason": "recent"}
        except Exception:  # noqa: BLE001
            pass
    return {"ran": True, **scan(db)}
