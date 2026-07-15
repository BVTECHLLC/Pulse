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

# v1.33 — a different editorial ANGLE each weekday so a 24/7 daily cadence
# never reads same-y. Both site writers get the day's angle woven into the
# prompt (topics/metros rotate independently, multiplying the variety).
WEEKDAY_ANGLES = (
    "a practical deep-dive guide the reader can act on this week",      # Mon
    "a short, punchy checklist or numbered action list",                # Tue
    "commentary on a current trend or recent industry development",     # Wed
    "myth-busting: a common belief that is wrong, and what to do instead",  # Thu
    "a story-driven lesson from the field (anonymized, concrete)",      # Fri
    "a 10-minute quick win: one small change with outsized payoff",     # Sat
    "big-picture strategy: how owners should think about this next quarter",  # Sun
)


def day_angle(now: datetime) -> str:
    return WEEKDAY_ANGLES[now.weekday()]


def bvtech_angle(now: datetime) -> str:
    """bvtech.org's editorial calendar: Monday is the WEEKLY CYBERSECURITY
    RECAP edition (the CVE/KEV-roundup style the site is known for); the other
    six days rotate the normal MSP-SEO weekday angles."""
    if now.weekday() == 0:
        return ("the WEEKLY CYBERSECURITY RECAP edition: a plain-English roundup of "
                "this week's most important vulnerability and threat news for Texas "
                "small businesses — what changed, who is affected, and exactly what to "
                "do about each item. Reference specific CVEs/CISA-KEV entries ONLY if "
                "you are certain they are real; otherwise cover the week's threat "
                "themes generically. Title it like a weekly security briefing.")
    return day_angle(now)

_JP_SYSTEM = (
    "You are ghost-writing for Jordan Polasek — founder of BVTech, writing on his "
    "personal site jordanpolasek.com. Voice: direct, practical, first-person founder "
    "insight for Texas business owners; zero corporate fluff. NEVER mention El Campo.\n"
    "Reply in EXACTLY this delimited format (NOT JSON, no code fences):\n"
    "TITLE: <the headline>\n"
    "EXCERPT: <one-sentence summary, max 160 chars>\n"
    "HTML:\n"
    "<the article BODY as clean HTML: <p>, <h2>, <ul> — no <html>/<head>>"
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


def _pub_note(out: dict) -> str:
    """Human note for a site-publish result: did the post make it into the blog
    LISTING, and was the Cloudflare cache purged? These two are exactly what
    made successful publishes look like 'nothing happened'."""
    bits = []
    if out.get("listing_generated"):
        bits.append(f"published as {out.get('content_path', 'markdown')} - the site build "
                    "adds it to the blog index automatically")
    elif out.get("listings_updated"):
        bits.append("listed in " + ", ".join(out["listings_updated"]))
    elif out.get("listings_skipped"):
        bits.append("WARNING: not added to the blog index - run the Doctor")
    if out.get("cache_purged"):
        bits.append("cache purged - visible now")
    elif out.get("cache_detail"):
        bits.append(f"cache: {out['cache_detail']}")
    return " | ".join(bits)


def get_config(db: Session) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    chans = cfg.get("channels") or {}
    return {
        # HANDS-FREE BY DEFAULT (v1.33): daily posting is ON unless explicitly
        # turned off. Channels that aren't connected just report that and skip —
        # nothing breaks — so the safe default is "publish every day".
        "enabled": bool(cfg.get("enabled", True)),
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
    """bvtech.org is a static site in GitLab (deployed by Cloudflare) — publish
    there natively; WordPress only as a legacy fallback if someone connected it."""
    from . import blog_autopilot, jp_site, wordpress
    article = blog_autopilot.generate_article(db, now, angle=bvtech_angle(now))
    if not article:
        return False, "article generation returned nothing"
    if jp_site.configured(db, "bvtech"):
        out = jp_site.publish(db, article, site="bvtech")
        if not out.get("ok"):
            return False, out.get("error") or "GitLab publish failed"
        # Record the post so (a) it shows in blog history and (b) the topic/metro
        # rotation in generate_article ADVANCES — without this row the counter
        # never moved for GitLab publishes, so every run regenerated the same
        # topic (and often the same slug -> duplicate-file 400s).
        from ..models import BlogPost
        db.add(BlogPost(title=article.get("title") or "(untitled)",
                        excerpt=article.get("excerpt"), html=article.get("html"),
                        status="posted", url=out.get("url"), source="autopilot"))
        db.commit()
        note = _pub_note(out)
        news_note = _publish_news_edition(db, now)
        return True, ((out.get("url") or article.get("title", ""))
                      + (f" | {note}" if note else "") + news_note)
    if wordpress.configured(db):
        row = blog_autopilot.publish_article(db, article, source="autopilot")
        if row.status != "posted":
            return False, row.error or "WordPress publish failed"
        return True, row.url or row.title
    return False, "bvtech.org not connected (GitLab token — one paste connects both sites)"


_NEWS_SYSTEM = (
    "You are Jordan Polasek, Founder of BVTech LLC, writing your DAILY 'BVTech News - "
    "Cybersecurity Intelligence' briefing at bvtech.org/news/ - first-person, expert, "
    "plain-English KEV/CVE analysis with real remediation steps for Texas small "
    "businesses. Use ONLY the real CVE facts provided; never invent CVEs. NEVER "
    "mention El Campo.\n"
    "Reply EXACTLY:\nTITLE: <briefing headline; the date written naturally after an em dash, e.g. '... — July 15, 2026', NEVER in parentheses>\n"
    "EXCERPT: <120-155 chars>\nHTML:\n<body html: <p>,<h2>,<ul> only>")


def _publish_news_edition(db: Session, now: datetime) -> str:
    """Daily KEV briefing to bvtech.org/news/ (its own page + index), cloned
    from the newest existing edition's markup. 1/day rides the bvtech cap."""
    import os as _os
    if _os.environ.get("PULSE_DISABLE_KEV_TICKER"):
        return ""
    from . import jp_site
    try:
        kev = jp_site._KEV_FETCH(6)
        items = "; ".join(f"{k['cve']} ({k['vendor']} {k['product']}: {k['name']}, "
                          f"added {k['added']}, federal due {k['due']})" for k in kev)
        raw = ai.complete(_NEWS_SYSTEM,
                          f"Today: {now:%B %d, %Y}. Real CISA KEV entries to cover "
                          f"(exact facts): {items}", smart=True, max_tokens=4000)
        npost = ai.parse_article(raw)
        if not npost:
            return " | news: article unparseable"
        nout = jp_site.publish(db, npost, site="bvtech_news")
        return (f" | news: {nout.get('url')}" if nout.get("ok")
                else f" | news FAILED: {nout.get('error', '?')[:80]}")
    except Exception as e:  # noqa: BLE001
        return f" | news FAILED: {str(e)[:80]}"


def _run_jp(db: Session, now: datetime) -> tuple[bool, str]:
    from . import jp_site
    if not jp_site.configured(db):
        return False, "jordanpolasek.com not connected (GitLab project + token)"
    metro = _METROS[now.toordinal() % len(_METROS)]
    prompt = (f"Write today's post. Angle it for business owners around {metro}. "
              f"Pick ONE specific, practical topic (IT strategy, security, hiring, "
              f"vendor costs, growth systems). Today's editorial style: {day_angle(now)}. "
              f"Date: {now:%B %d, %Y}.")
    # Quote-proof delimited format (JSON kept breaking on unescaped quotes in
    # the HTML) + JSON fallback + ONE corrective retry. On total failure the
    # error carries a snippet of what Claude actually said, so it's diagnosable.
    raw = ai.complete(_JP_SYSTEM, prompt, smart=True, max_tokens=4000)
    post = ai.parse_article(raw)
    if not post:
        raw = ai.complete(_JP_SYSTEM, prompt + "\nIMPORTANT: use EXACTLY the "
                          "TITLE:/EXCERPT:/HTML: format - nothing before TITLE:, "
                          "no JSON, no code fences.",
                          smart=True, max_tokens=4000)
        post = ai.parse_article(raw)
    if not post:
        head = " ".join(str(raw or "")[:120].split())
        return False, f"JP article unparseable after retry; Claude said: '{head}...'"
    out = jp_site.publish(db, post)
    if not out.get("ok"):
        return False, out.get("error") or "publish failed"
    note = _pub_note(out)
    return True, (out.get("url") or post["title"]) + (f" | {note}" if note else "")


def _enqueue_social(db: Session, body: str, channel: str, link: str = "") -> SocialPost:
    # v1.40 FLOOD GUARD: ONE queued draft per channel — a newer draft REPLACES
    # the queued one instead of stacking. Smashing 'Post to all now' while a
    # channel is paused can never build a backlog that floods it on reconnect.
    queued = [r for r in db.query(SocialPost).filter(SocialPost.status == "queued").all()
              if channel in (r.channels or [])]
    keep = queued[0] if queued else None
    for r in queued[1:]:
        r.status = "skipped"
        r.result = "superseded by a newer draft (1-post-per-day flood guard)"
    if keep is not None:
        keep.body = body[:2800]
        keep.link = link or "https://bvtech.org"
        keep.scheduled_for = datetime.now(timezone.utc)
        keep.result = "draft refreshed (flood guard keeps one queued post per channel)"
        db.commit()
        return keep
    post = SocialPost(body=body[:2800], link=link or "https://bvtech.org",
                      channels=[channel], status="queued",
                      scheduled_for=datetime.now(timezone.utc))
    db.add(post)
    db.commit()
    return post


def collapse_queue(db: Session) -> int:
    """Backlog self-heal (runs every heartbeat tick): keep only the NEWEST
    queued post per channel, mark older duplicates skipped. Returns how many
    were collapsed. This drains any flood that accumulated before v1.40."""
    rows = (db.query(SocialPost).filter(SocialPost.status == "queued")
            .order_by(SocialPost.created_at.desc()).all())
    seen: set[str] = set()
    collapsed = 0
    for r in rows:                                   # newest first
        chans = tuple(r.channels or ["linkedin"])
        if all(c in seen for c in chans):
            r.status = "skipped"
            r.result = "superseded by a newer draft (1-post-per-day flood guard)"
            collapsed += 1
        seen.update(chans)
    if collapsed:
        db.commit()
    return collapsed


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
# v1.27 Publish a SPECIFIC, hand-written post — the "I wrote this exact thing,
# ship it" path. The daily autopilot generates content; this pushes content you
# supply through the very same publishers (GitLab commit + Cloudflare verify for
# the sites, the autopost queue for LinkedIn/GBP) so nothing bypasses the guards.
# --------------------------------------------------------------------------- #
def publish_custom(db: Session, channel: str, *, title: str | None = None,
                   html: str | None = None, body: str | None = None,
                   excerpt: str | None = None, slug: str | None = None,
                   keywords: str | None = None, kind: str | None = None,
                   link: str = "", override: bool = False) -> dict:
    """Publish one operator-authored post to one channel. Returns
    {ok, channel, detail, url?/queued_id?}. Never raises for a 'not connected'
    channel — it reports it, exactly like the daily runner."""
    if channel not in ("bvtech", "jp", "linkedin", "gbp"):
        return {"ok": False, "channel": channel, "detail": f"unknown channel '{channel}'"}

    # v1.40 FLOOD GUARD: custom posts respect the 1-post-per-day cap too —
    # repeated Publish clicks can't stack same-day posts and tank SEO. An
    # explicit override exists for the rare deliberate second post.
    now = datetime.now(timezone.utc)
    cfg = get_config(db)
    if not override and cfg["last"].get(channel) == _today(now):
        return {"ok": False, "channel": channel, "capped": True,
                "detail": "already posted to this channel today - the 1-post-per-day "
                          "guard protects your SEO. It resets at midnight UTC (7pm "
                          "Central); tick 'post anyway' only if you truly want a second "
                          "same-day post."}

    if channel in ("bvtech", "jp"):
        from . import jp_site
        if not (html or body):
            return {"ok": False, "channel": channel, "detail": "no content (html or body required)"}
        if not title:
            return {"ok": False, "channel": channel, "detail": "a title is required for a site post"}
        if not jp_site.configured(db, channel):
            site = "bvtech.org" if channel == "bvtech" else "jordanpolasek.com"
            return {"ok": False, "channel": channel,
                    "detail": f"{site} not connected (paste a GitLab token — one connects both sites)"}
        post = {"title": title, "html": html or "", "body": body or "",
                "description": excerpt or "", "slug": slug or "",
                "keywords": keywords or "", "kind": kind or "blog"}
        post = {k: v for k, v in post.items() if v}
        out = jp_site.publish(db, post, site=channel)
        if not out.get("ok"):
            return {"ok": False, "channel": channel, "detail": out.get("error") or "publish failed"}
        _mark(db, channel, ok=True, now=now)   # counts toward the 1/day cap
        note = _pub_note(out)
        return {"ok": True, "channel": channel,
                "detail": "committed" + (f" | {note}" if note else ""),
                "url": out.get("url"), "slug": out.get("slug")}

    # LinkedIn / Google Business — queue through the autopost engine (retries,
    # guards, dedupe, requeue all already built in). The heartbeat/next tick
    # delivers it; the brand guard rejects off-brand content at publish time.
    text = (body or html or "").strip()
    if not text:
        return {"ok": False, "channel": channel, "detail": "no post text"}
    social_channel = "linkedin" if channel == "linkedin" else "google_business"
    row = _enqueue_social(db, text, social_channel, link=link)   # flood-guarded queue
    _mark(db, channel, ok=True, now=now)                   # counts toward the 1/day cap
    return {"ok": True, "channel": channel, "queued_id": row.id,
            "detail": f"queued to {social_channel} (autopost engine delivers + retries; "
                      "one queued draft per channel - a newer draft replaces it)"}


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
        # v1.47: LinkedIn + Google Business are WEEKLY - Mondays only (a
        # deliberate force-run can still post any day, capped 1/day).
        if ch in ("linkedin", "gbp") and not force and now.weekday() != 0:
            continue
        if cfg["last"].get(ch) == _today(now):
            # v1.40 FLOOD GUARD: one post per channel per day, ALWAYS — even on
            # 'Post to all now'. Smashing the button can never stack extra posts
            # (19-a-day floods murder SEO). Force still runs channels that
            # haven't shipped today (e.g. retrying a failed one right now).
            if force:
                results[ch] = {"ok": True, "skipped_daily_cap": True,
                               "detail": "already posted today - the 1-post-per-day guard "
                                         "protects your SEO; the next post ships tomorrow"}
            continue
        try:
            ok, detail = _RUNNERS[ch](db, now)
        except Exception as e:  # noqa: BLE001
            ok, detail = False, str(e)[:300]
            db.rollback()
        _mark(db, ch, ok=ok, error=None if ok else detail, now=now)
        if not ok:
            _notify_fail(db, ch, detail)
        results[ch] = {"ok": ok, "detail": detail}
    # v1.44: refresh bvtech.org's LIVE CISA-KEV homepage ticker with today's
    # real exploited-vulnerability entries — once per day (stamped inside).
    # Kept OUT of `results` (its own key) so channel semantics stay untouched.
    import os as _os
    kev = None
    if cfg["channels"].get("bvtech", True) and not _os.environ.get("PULSE_DISABLE_KEV_TICKER"):
        try:
            from . import jp_site
            kev = jp_site.update_kev_ticker(db, now)
        except Exception:  # noqa: BLE001
            db.rollback()
    # v1.33 daily receipt: on the scheduled (non-force) run, drop ONE summary
    # notification with the day's shipped URLs — hands-free means the operator
    # never has to check; the proof comes to them. Failures already notify
    # individually; this is the "it worked" side of never-silent.
    if not force and any(r["ok"] for r in results.values()):
        try:
            lines = "; ".join(f"{ch} OK - {r['detail'][:120]}" if r["ok"] else f"{ch} FAILED"
                              for ch, r in results.items())
            db.add(Notification(client_id=None, target_user_id=None, kind="content",
                                severity="info",
                                message=f"📣 Today's content shipped: {lines}"[:1000]))
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
    return {"ran": True, "results": results, "kev_ticker": kev}


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
        "bvtech": jp_site.configured(db, "bvtech") or wordpress.configured(db),
        "jp": jp_site.configured(db, "jp"),
        "linkedin": bool(secure_config.get_secret(li_cfg, "access_token")
                         or db.query(OAuthToken).filter(OAuthToken.provider == "linkedin").count()),
        "gbp": bool(gbp_cfg.get("account_name") and gbp_cfg.get("location_name")),
    }
    hints = {
        "bvtech": "Marketing → Content Autopilot: one GitLab token connects both sites",
        "jp": "Marketing → Content Autopilot: one GitLab token connects both sites",
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
