"""v1.4 Auto-blogger — Claude writes bvtech.org articles; Pulse publishes them.

Rides the Autopilot heartbeat: every `every_days` days (default 3) it writes one
SEO-conscious article in the brand voice, rotating across the target metros
(reusing the auto-poster's brand profile: voice, metros, keywords, CTA), and
publishes it to the connected WordPress site. Optionally cross-posts a teaser
to LinkedIn by dropping it into the existing social queue (which has its own
retry + brand guards).

Safety rails:
  * Off by default — nothing publishes until the owner flips it on.
  * `wp_status` can be "draft" to keep a human in the loop.
  * Brand guard: articles mentioning excluded areas (El Campo) are rejected
    before any network call and recorded as failed (visible, not silent).
  * At most one attempt per hour after a failure — no hammering WP or Claude.

Every attempt is a BlogPost row: posted rows carry the live URL, failed rows
carry the reason.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import BlogPost, Notification
from . import ai, secure_config, wordpress

PROVIDER = "blog_autopilot"
_TRUTHY = {"1", "true", "yes", "on"}

_BANNED_PHRASES = ("el campo",)

_SYSTEM = (
    "You write blog articles for BVTech (bvtech.org), a managed IT services & "
    "cybersecurity company serving {metros}. Audience: small-business owners and "
    "office managers — smart people who are not IT experts. Voice: {voice}\n"
    "Write ONE complete article and reply in EXACTLY this delimited format "
    "(NOT JSON, no markdown fences):\n"
    "TITLE: compelling, specific, max 70 chars, naturally includes the focus "
    "metro or topic (SEO headline, not clickbait)\n"
    "EXCERPT: meta-description quality summary, 120-155 chars\n"
    "HTML:\n"
    "the article body as clean HTML (600-900 words): <p>, <h2>, <h3>, "
    "<ul>/<ol>/<li>, <strong> only — no <html>/<head>/<h1>/inline styles/scripts. "
    "Structure: a hook paragraph, 3-5 sections with h2 headings, a practical "
    "checklist or takeaways list, and a closing paragraph that invites the reader "
    "to reach out to BVTech ({cta}). Concrete and useful over promotional; one "
    "natural mention of the focus metro; never invent statistics or client names."
)


def get_config(db: Session) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    return {
        "enabled": str(cfg.get("enabled", "false")).lower() in _TRUTHY,
        "every_days": max(1, int(cfg.get("every_days") or 3)),
        "wp_status": cfg.get("wp_status") if cfg.get("wp_status") in ("publish", "draft") else "publish",
        "cross_post_linkedin": str(cfg.get("cross_post_linkedin", "true")).lower() in _TRUTHY,
        "topics": cfg.get("topics") or "",
        "wp_configured": wordpress.configured(db),
        "ai_connected": ai.enabled(),
    }


def save_config(db: Session, **fields) -> dict:
    payload: dict[str, str] = {}
    for k in ("enabled", "cross_post_linkedin"):
        if fields.get(k) is not None:
            payload[k] = "true" if fields[k] else "false"
    if fields.get("every_days") is not None:
        payload["every_days"] = str(max(1, int(fields["every_days"])))
    if fields.get("wp_status") in ("publish", "draft"):
        payload["wp_status"] = fields["wp_status"]
    if fields.get("topics") is not None:
        payload["topics"] = str(fields["topics"])[:500]
    if payload:
        secure_config.upsert_platform(db, PROVIDER, "Auto-Blogger", "Marketing", payload)
    return get_config(db)


def _brand(db: Session) -> dict:
    """Reuse the auto-poster's brand profile (voice, metros, keywords, CTA)."""
    from . import autopost
    cfg = autopost.get_config(db)
    metros = cfg["cities"] or ["Sugar Land", "Houston", "Austin", "San Antonio"]
    metros = [m for m in metros if len(m.strip()) > 2]
    return {"metros": metros, "voice": cfg["voice"] or
            "plain-spoken, confident, technically credible, zero fluff",
            "keywords": cfg["keywords"], "cta": cfg["cta_url"] or "https://bvtech.org/contact"}


def _guard(title: str, html: str) -> str | None:
    text = f"{title}\n{html}".lower()
    for phrase in _BANNED_PHRASES:
        if phrase in text:
            return f"rejected: off-brand content ('{phrase}' is excluded by brand rules)"
    return None


def generate_article(db: Session, now: datetime | None = None) -> dict:
    """Ask Claude for one article, rotating the focus metro/topic. Raises
    ai.AIError on API failure; returns {} on unparseable output."""
    now = now or datetime.now(timezone.utc)
    b = _brand(db)
    cfg = get_config(db)
    n = db.query(BlogPost).count()
    metro = b["metros"][n % len(b["metros"])]
    topic_pool = [t.strip() for t in (cfg["topics"] or "").split(",") if t.strip()] or [
        "phishing and email security", "ransomware readiness for small business",
        "backups and disaster recovery", "Microsoft 365 security settings",
        "when to outsource IT vs hire", "Wi-Fi and network security basics",
        "cyber insurance requirements", "password managers and MFA rollout",
        "signs your business has outgrown break-fix IT", "employee security training",
    ]
    topic = topic_pool[n % len(topic_pool)]
    kw = ", ".join(b["keywords"][:5]) if b["keywords"] else "managed IT services, cybersecurity"
    system = _SYSTEM.format(metros=", ".join(b["metros"]), voice=b["voice"], cta=b["cta"])
    user = (f"Focus metro: {metro}\nTopic: {topic}\n"
            f"Work these phrases in naturally where they fit: {kw}\n"
            f"Today's date: {now:%B %Y}")
    raw = ai.complete(system, user, smart=True, max_tokens=4000)
    out = ai.parse_article(raw)   # quote-proof sections format, JSON fallback
    if not out:
        raw = ai.complete(system, user + "\nIMPORTANT: use EXACTLY the TITLE:/"
                          "EXCERPT:/HTML: format - nothing before TITLE:, no JSON, "
                          "no code fences.", smart=True, max_tokens=4000)
        out = ai.parse_article(raw)
    if not out:
        return {}
    title = str(out.get("title") or "").strip()
    html = str(out.get("html") or "").strip()
    excerpt = str(out.get("excerpt") or "").strip()
    if not title or len(html) < 400:
        return {}
    return {"title": title[:200], "excerpt": excerpt[:400], "html": html}


def publish_article(db: Session, article: dict, *, source: str = "auto") -> BlogPost:
    """Publish one article to WordPress, record the outcome, cross-post the
    teaser. Never raises — the BlogPost row carries success or failure."""
    cfg = get_config(db)
    row = BlogPost(title=article.get("title") or "(untitled)",
                   excerpt=article.get("excerpt"), html=article.get("html"),
                   source=source)
    reason = _guard(row.title, row.html or "")
    if reason:
        row.status, row.error = "failed", reason[:400]
        db.add(row); db.commit()
        return row
    try:
        res = wordpress.publish_post(db, title=row.title, content_html=row.html or "",
                                     excerpt=row.excerpt or "", status=cfg["wp_status"])
        row.status, row.wp_post_id, row.url = "posted", res.get("id"), res.get("link")
    except Exception as e:  # noqa: BLE001
        row.status, row.error = "failed", str(e)[:400]
    db.add(row)
    db.commit()

    if row.status == "failed":
        try:
            from . import notifications
            msg = (f"Website post “{row.title[:80]}” failed to publish: "
                   f"{row.error} — see Content Studio → Website.")
            db.add(Notification(client_id=None, target_user_id=None, kind="website",
                                severity="warning", message=msg[:1000]))
            db.commit()
            notifications.fanout(db, message=msg, severity="warning", client_id=None)
        except Exception:  # noqa: BLE001
            pass
    elif (cfg["cross_post_linkedin"] and row.url
          and cfg["wp_status"] == "publish"):
        # Teaser into the existing social queue — it has its own cadence,
        # retry, and brand guards.
        try:
            from ..models import SocialPost
            teaser = (f"New on the BVTech blog: {row.title}\n\n"
                      f"{(row.excerpt or '')[:250]}")
            db.add(SocialPost(body=teaser, link=row.url, channels=["linkedin"],
                              status="queued"))
            db.commit()
        except Exception:  # noqa: BLE001
            pass
    return row


def _last_attempt(db: Session) -> BlogPost | None:
    return db.query(BlogPost).order_by(BlogPost.id.desc()).first()


def _last_posted(db: Session) -> BlogPost | None:
    return (db.query(BlogPost).filter(BlogPost.status == "posted")
            .order_by(BlogPost.id.desc()).first())


def maybe_publish(db: Session, now: datetime | None = None) -> dict:
    """Heartbeat entrypoint. Publishes at most one article per `every_days`;
    after a failure, waits an hour before retrying."""
    now = now or datetime.now(timezone.utc)
    cfg = get_config(db)
    if not cfg["enabled"]:
        return {"published": False, "reason": "disabled"}
    if not cfg["wp_configured"]:
        return {"published": False, "reason": "wordpress_not_configured"}
    if not cfg["ai_connected"]:
        return {"published": False, "reason": "ai_off"}

    last_ok = _last_posted(db)
    if last_ok and last_ok.created_at:
        age = now - (last_ok.created_at if last_ok.created_at.tzinfo
                     else last_ok.created_at.replace(tzinfo=timezone.utc))
        if age < timedelta(days=cfg["every_days"]):
            return {"published": False, "reason": "not_due"}
    last_any = _last_attempt(db)
    if last_any and last_any.status == "failed" and last_any.created_at:
        age = now - (last_any.created_at if last_any.created_at.tzinfo
                     else last_any.created_at.replace(tzinfo=timezone.utc))
        if age < timedelta(hours=1):
            return {"published": False, "reason": "cooling_down_after_failure"}

    try:
        article = generate_article(db, now)
    except Exception as e:  # noqa: BLE001
        db.add(BlogPost(title="(generation failed)", status="failed",
                        error=str(e)[:400], source="auto"))
        db.commit()
        return {"published": False, "reason": f"generation_failed: {e}"[:200]}
    if not article:
        db.add(BlogPost(title="(generation failed)", status="failed",
                        error="Claude returned an unparseable article", source="auto"))
        db.commit()
        return {"published": False, "reason": "unparseable_article"}
    row = publish_article(db, article, source="auto")
    return {"published": row.status == "posted", "post_id": row.id,
            "url": row.url, "error": row.error}
