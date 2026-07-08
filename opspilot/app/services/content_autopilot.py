"""v1.20 Content Autopilot — one switch, four channels, daily, never silent.

The marketing engine the operator asked for: every day Pulse writes and ships
CHANNEL-CUSTOMIZED content to all four surfaces —

  * bvtech.org        — full SEO article via WordPress (blog_autopilot)
  * jordanpolasek.com — founder/thought-leadership post committed to the site
                        repo via the GitLab API, with the Cloudflare build
                        VERIFIED and auto-reverted on failure (jp_site)
  * LinkedIn          — a short, punchy insight post (autopost queue: retries,
                        guards, requeue already built in)
  * Google Business   — a local-flavored update rotating the target metros
                        (Sugar Land / Houston / Austin / San Antonio)

Rules of the road: one post per channel per day (deduped per channel), a failed
channel NEVER blocks the others, every failure raises a notification and the
channel retries on the next heartbeat tick — success is the only thing that
marks a channel done for the day.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import Notification, SocialPost
from . import ai, secure_config

PROVIDER = "content_autopilot"
POST_HOUR_UTC = 14        # ~9am Central — content lands before the business day
CHANNELS = ("bvtech", "jp", "linkedin", "gbp")

_METROS = ("Sugar Land", "Houston", "Austin", "San Antonio")

_JP_SYSTEM = (
    "You are ghost-writing for Jordan Polasek — founder of BVTech, writing on his "
    "personal site jordanpolasek.com. Voice: direct, practical, first-person founder "
    "insight for Texas business owners; zero corporate fluff. NEVER mention El Campo. "
    "Return STRICT JSON: {\"title\": str, \"excerpt\": str (<=160 chars), "
    "\"html\": str (the article BODY as clean HTML: <p>, <h2>, <ul> — no <html>/<head>)}."
)
_LI_SYSTEM = (
    "You write LinkedIn posts for BVTech, a managed IT provider serving Sugar Land, "
    "Houston, Austin and San Antonio. 60-120 words, hook first line, concrete insight, "
    "one soft CTA, 2-3 hashtags. Never mention El Campo. Return the post text only."
)
_GBP_SYSTEM = (
    "You write Google Business Profile updates for BVTech (managed IT, cybersecurity). "
    "2-3 sentences, local flavor for the given metro, one clear CTA to bvtech.org. "
    "Never mention El Campo. Return the update text only."
)


def _today(now: datetime) -> str:
    return now.date().isoformat()


def get_config(db: Session) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    chans = cfg.get("channels") or {}
    return {
        "enabled": bool(cfg.get("enabled")),
        "hour_utc": int(cfg.get("hour_utc") or POST_HOUR_UTC),
        "channels": {c: bool(chans.get(c, True)) for c in CHANNELS},
        "last": cfg.get("last") or {},         # {channel: ISO date of last SUCCESS}
        "last_error": cfg.get("last_error") or {},
    }


def save_config(db: Session, *, enabled: bool | None = None, hour_utc: int | None = None,
                channels: dict | None = None) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    raw = dict((conn.config if conn else None) or {})
    if enabled is not None:
        raw["enabled"] = bool(enabled)
    if hour_utc is not None:
        raw["hour_utc"] = max(0, min(23, int(hour_utc)))
    if channels is not None:
        cur = raw.get("channels") or {}
        cur.update({c: bool(v) for c, v in channels.items() if c in CHANNELS})
        raw["channels"] = cur
    secure_config.upsert_platform(db, PROVIDER, "Content Autopilot", "Publishing", raw)
    return get_config(db)


def _mark(db: Session, channel: str, *, ok: bool, error: str | None = None,
          now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    conn = secure_config.get_platform(db, PROVIDER)
    raw = dict((conn.config if conn else None) or {})
    if ok:
        last = dict(raw.get("last") or {})
        last[channel] = _today(now)
        raw["last"] = last
        le = dict(raw.get("last_error") or {})
        le.pop(channel, None)
        raw["last_error"] = le
    else:
        le = dict(raw.get("last_error") or {})
        le[channel] = {"date": _today(now), "error": (error or "unknown")[:300]}
        raw["last_error"] = le
    secure_config.upsert_platform(db, PROVIDER, "Content Autopilot", "Publishing", raw)


def _notify_fail(db: Session, channel: str, error: str) -> None:
    try:
        db.add(Notification(client_id=None, target_user_id=None, kind="content",
                            severity="warning",
                            message=(f"📣 Content Autopilot: the {channel} post failed — "
                                     f"{error[:200]}. Will retry on the next tick.")[:1000]))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()


# --------------------------------------------------------------------------- #
# Per-channel runners — each returns (ok, detail)
# --------------------------------------------------------------------------- #
def _run_bvtech(db: Session, now: datetime) -> tuple[bool, str]:
    from . import blog_autopilot, wordpress
    if not wordpress.configured(db):
        return False, "WordPress not connected (Settings → Website)"
    article = blog_autopilot.generate_article(db, now)
    if not article:
        return False, "article generation returned nothing"
    row = blog_autopilot.publish_article(db, article, source="autopilot")
    if row.status != "posted":
        return False, row.error or "WordPress publish failed"
    return True, row.url or row.title


def _run_jp(db: Session, now: datetime) -> tuple[bool, str]:
    from . import jp_site
    if not jp_site.configured(db):
        return False, "jordanpolasek.com not connected (GitLab project + token)"
    metro = _METROS[now.toordinal() % len(_METROS)]
    raw = ai.complete(_JP_SYSTEM,
                      f"Write today's post. Angle it for business owners around {metro}. "
                      f"Pick ONE specific, practical topic (IT strategy, security, hiring, "
                      f"vendor costs, growth systems). Date: {now:%B %d, %Y}.",
                      smart=True, max_tokens=2500)
    import json as _json
    try:
        start, end = raw.find("{"), raw.rfind("}")
        post = _json.loads(raw[start:end + 1])
        assert post.get("title") and post.get("html")
    except Exception:  # noqa: BLE001
        return False, "Claude returned an unparseable JP article"
    out = jp_site.publish(db, post)
    if not out.get("ok"):
        return False, out.get("error") or "publish failed"
    return True, out.get("url") or post["title"]


def _enqueue_social(db: Session, body: str, channel: str, link: str = "") -> None:
    db.add(SocialPost(body=body[:2800], link=link or "https://bvtech.org",
                      channels=[channel], status="queued",
                      scheduled_for=datetime.now(timezone.utc)))
    db.commit()


def _run_linkedin(db: Session, now: datetime) -> tuple[bool, str]:
    conn = secure_config.get_platform(db, "pub_linkedin")
    cfg = (conn.config if conn else None) or {}
    from ..models import OAuthToken
    has_oauth = (db.query(OAuthToken).filter(OAuthToken.provider == "linkedin").count() > 0)
    if not (secure_config.get_secret(cfg, "access_token") or has_oauth):
        return False, "LinkedIn not connected (Settings → One-click Connect)"
    metro = _METROS[(now.toordinal() + 1) % len(_METROS)]
    text = ai.complete(_LI_SYSTEM,
                       f"Topic seed: one thing {metro}-area businesses get wrong about IT/"
                       f"security, and the fix. Date: {now:%B %d}.", max_tokens=400)
    _enqueue_social(db, text.strip(), "linkedin")
    return True, "queued to LinkedIn (autopost engine delivers + retries)"


def _run_gbp(db: Session, now: datetime) -> tuple[bool, str]:
    conn = secure_config.get_platform(db, "gbp")
    cfg = (conn.config if conn else None) or {}
    if not (cfg.get("account_name") and cfg.get("location_name")):
        return False, "Google Business Profile not connected (Settings → GBP)"
    metro = _METROS[(now.toordinal() + 2) % len(_METROS)]
    text = ai.complete(_GBP_SYSTEM,
                       f"Write today's update for the {metro} area. Date: {now:%B %d}.",
                       max_tokens=300)
    _enqueue_social(db, text.strip(), "google_business")
    return True, "queued to Google Business (autopost engine delivers + retries)"


_RUNNERS = {"bvtech": _run_bvtech, "jp": _run_jp,
            "linkedin": _run_linkedin, "gbp": _run_gbp}


# --------------------------------------------------------------------------- #
# The daily tick + on-demand runs
# --------------------------------------------------------------------------- #
def run_daily(db: Session, now: datetime | None = None, *, force: bool = False) -> dict:
    """Heartbeat entrypoint (and the 'Post to all now' button with force=True).
    One customized post per enabled channel per day; failures notify + retry."""
    now = now or datetime.now(timezone.utc)
    cfg = get_config(db)
    if not force:
        if not cfg["enabled"]:
            return {"ran": False, "reason": "disabled", "results": {}}
        if now.hour < cfg["hour_utc"]:
            return {"ran": False, "reason": "too_early", "results": {}}
    if not ai.enabled():
        return {"ran": False, "reason": "ai_off", "results": {}}
    results: dict[str, dict] = {}
    for ch in CHANNELS:
        if not cfg["channels"].get(ch, True):
            continue
        if not force and cfg["last"].get(ch) == _today(now):
            continue   # already succeeded today
        try:
            ok, detail = _RUNNERS[ch](db, now)
        except Exception as e:  # noqa: BLE001
            ok, detail = False, str(e)[:300]
            db.rollback()
        _mark(db, ch, ok=ok, error=None if ok else detail, now=now)
        if not ok:
            _notify_fail(db, ch, detail)
        results[ch] = {"ok": ok, "detail": detail}
    return {"ran": True, "results": results}


def status(db: Session) -> dict:
    """The one-click card's data: per channel — connected? enabled? last result."""
    cfg = get_config(db)
    from . import jp_site, wordpress
    from ..models import OAuthToken
    li_conn = secure_config.get_platform(db, "pub_linkedin")
    li_cfg = (li_conn.config if li_conn else None) or {}
    gbp_conn = secure_config.get_platform(db, "gbp")
    gbp_cfg = (gbp_conn.config if gbp_conn else None) or {}
    connected = {
        "bvtech": wordpress.configured(db),
        "jp": jp_site.configured(db),
        "linkedin": bool(secure_config.get_secret(li_cfg, "access_token")
                         or db.query(OAuthToken).filter(OAuthToken.provider == "linkedin").count()),
        "gbp": bool(gbp_cfg.get("account_name") and gbp_cfg.get("location_name")),
    }
    hints = {
        "bvtech": "Settings → Website: WordPress URL + username + Application Password",
        "jp": "Settings → Content Autopilot: GitLab project + token (api scope)",
        "linkedin": "Settings → One-click Connect → LinkedIn (Connect →)",
        "gbp": "Settings → Google Business Profile: connect + pick your location",
    }
    return {"enabled": cfg["enabled"], "hour_utc": cfg["hour_utc"],
            "ai_connected": ai.enabled(),
            "channels": [{"key": c,
                          "name": {"bvtech": "bvtech.org blog", "jp": "jordanpolasek.com",
                                   "linkedin": "LinkedIn", "gbp": "Google Business"}[c],
                          "enabled": cfg["channels"].get(c, True),
                          "connected": connected[c],
                          "last_success": cfg["last"].get(c),
                          "last_error": cfg["last_error"].get(c),
                          "setup_hint": hints[c]} for c in CHANNELS]}
