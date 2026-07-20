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
    try:
        article = blog_autopilot.generate_article(db, now, angle=bvtech_angle(now))
    except Exception:  # noqa: BLE001 — LLM down/exhausted
        article = None
    if not article:
        # v1.50: zero-token evergreen floor — the blog publishes even when no
        # LLM (free or paid) is reachable, so a dead token balance never leaves
        # bvtech.org without a post.
        article = _compose_bvtech_deterministic(now)
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


def _news_remediation(product: str, vendor: str) -> str:
    """Deterministic, product-aware 'what to do' line — no AI, no tokens."""
    p = f"{vendor} {product}".lower()
    if any(k in p for k in ("sharepoint", "exchange", "outlook", "iis")):
        return ("On-premises servers are the exposure here — patch them today. "
                "Microsoft 365/SharePoint Online is patched for you by Microsoft.")
    if any(k in p for k in ("forti", "sonicwall", "cisco", "palo alto", "netscaler",
                            "citrix", "firewall", "vpn", "sandbox", "sma", "ivanti",
                            "pulse", "router", "gateway")):
        return ("This is an internet-facing edge/security appliance — apply the "
                "vendor fix now, and lock its management interface to a private "
                "network or VPN so it isn't reachable from the open internet.")
    if any(k in p for k in ("chrome", "firefox", "edge", "safari", "webkit", "v8")):
        return ("Update the browser AND relaunch it — the fix doesn't take effect "
                "until every window is closed and reopened.")
    if any(k in p for k in ("wordpress", "plugin", "drupal", "joomla", "wp")):
        return ("Update the plugin (or core) immediately and delete any plugins "
                "you're not actively using — every extra plugin is another door.")
    if any(k in p for k in ("oracle", "sap", "vmware", "esxi", "weblogic", "java")):
        return ("Patch the affected version now and restrict admin access to a "
                "management network; these systems are high-value targets.")
    return ("Apply the vendor's latest security update now, and review logs for "
            "signs the flaw was already used before you patched.")


def _compose_news_deterministic(now: datetime, kev: list[dict]) -> dict | None:
    """Build a real, useful daily KEV briefing from the CISA feed with ZERO AI
    tokens — factual security bulletins don't need a language model, just
    accurate data and clear remediation. Returns an article dict (title/excerpt/
    html) shaped exactly like ai.parse_article's output."""
    import html as _h
    from datetime import date as _date
    if not kev:
        return None
    date_str = now.strftime("%B %-d, %Y")
    n = len(kev)
    vendors = []
    for k in kev:
        v = (k.get("vendor") or "").strip()
        if v and v not in vendors:
            vendors.append(v)
    vsum = (vendors[0] if len(vendors) == 1
            else f"{vendors[0]} and {vendors[1]}" if len(vendors) == 2
            else f"{vendors[0]}, {vendors[1]}, and more")
    title = (f"BVTech News — {n} New KEV {'Entry' if n == 1 else 'Entries'} "
             f"Hit {vsum} — {date_str}")
    excerpt = (f"CISA added {n} actively-exploited "
               f"{'vulnerability' if n == 1 else 'vulnerabilities'} to the KEV "
               f"catalog: {vsum}. What each one is, and what to do about it.")[:200]

    def _days(added: str, due: str) -> str:
        try:
            a = _date.fromisoformat(added); d = _date.fromisoformat(due)
            n = (d - a).days
            return f"a {n}-day window" if n > 0 else "an immediate deadline"
        except (ValueError, TypeError):
            return "a short federal deadline"

    parts = [
        f"<p>CISA just added {n} new "
        f"{'vulnerability' if n == 1 else 'vulnerabilities'} to its "
        f"<strong>Known Exploited Vulnerabilities (KEV)</strong> catalog. A KEV "
        f"listing isn't theoretical — it means attackers are exploiting the flaw "
        f"right now. Here's each one in plain English, and exactly what a Texas "
        f"business should do about it.</p>"
    ]
    for k in kev:
        cve = _h.escape(k.get("cve", "CVE"))
        vendor = _h.escape(k.get("vendor", ""))
        product = _h.escape(k.get("product", ""))
        name = _h.escape((k.get("name") or "").rstrip("."))
        added = k.get("added", ""); due = k.get("due", "")
        parts.append(f"<h2>{cve} — {product or vendor}</h2>")
        parts.append(
            f"<p>{vendor} {product} carries a serious flaw"
            + (f" ({name})" if name else "")
            + f". CISA added it to the KEV catalog on {_h.escape(added)}"
            + (f", with a federal remediation deadline of {_h.escape(due)} — "
               f"{_days(added, due)}, which is CISA telling everyone how fast "
               f"this needs fixing" if due else "") + ".</p>")
        parts.append(f"<p><strong>What to do:</strong> "
                     f"{_news_remediation(k.get('product', ''), k.get('vendor', ''))}</p>")
    parts.append("<h2>The 60-second version</h2><ul>" + "".join(
        f"<li><strong>{_h.escape(k.get('cve',''))}</strong> — patch "
        f"{_h.escape(k.get('product') or k.get('vendor') or 'the affected system')}"
        + (f" by {_h.escape(k.get('due'))}" if k.get("due") else "") + "</li>"
        for k in kev) + "</ul>")
    parts.append(
        "<p>Federal agencies are the only ones legally bound by these deadlines — "
        "but the deadline length is CISA telling <em>everyone</em> how fast the "
        "house is burning. If you're not sure whether any of this hardware or "
        "software is in your environment, that's exactly the question we answer "
        'for Texas businesses every day. <a href="/contact/">Ask us</a>.</p>')
    return {"title": title, "excerpt": excerpt, "html": "\n".join(parts),
            "date": now.date().isoformat()}


# --------------------------------------------------------------------------- #
# ZERO-TOKEN evergreen post library (the always-on floor). Only used when no
# LLM is available at all — a free one (Groq/etc.) or Claude produces fresh
# posts first. Each entry is a real, on-voice post as structured data; the
# renderer turns it into the site's article HTML. Rotates by day so the floor
# never repeats two days running.
# --------------------------------------------------------------------------- #
def _render_evergreen(topic: dict, *, byline: str, cta_html: str,
                      date_str: str) -> dict:
    import html as _h
    parts = [f"<p>{topic['intro']}</p>"]
    for sec in topic["sections"]:
        parts.append(f"<h2>{_h.escape(sec['h2'])}</h2>")
        if isinstance(sec["body"], list):
            parts.append("<ul>" + "".join(f"<li>{b}</li>" for b in sec["body"]) + "</ul>")
        else:
            parts.append(f"<p>{sec['body']}</p>")
    parts.append(cta_html)
    return {"title": topic["title"], "excerpt": topic["excerpt"][:200],
            "html": "\n".join(parts), "date": date_str}


_BV_CTA = ('<p>If any of this hits close to home, that’s exactly what we help '
           'Texas businesses with every day. <a href="/contact/">Book a free '
           '15-minute IT assessment</a> — no pressure, no sales theater.</p>')
_JP_CTA = ('<p>That’s how I think about it, anyway. If you want a second set of '
           'eyes on your own setup, <a href="https://bvtech.org/contact/">reach '
           'out</a> — happy to talk it through.</p>')

_BV_EVERGREEN = [
    {"title": "The 3-2-1 Backup Rule, in Plain English",
     "excerpt": "Three copies, two kinds of media, one off-site. Why the rule that sounds boring is the one that saves businesses.",
     "intro": "Everybody nods along when you say “back up your data.” Almost nobody can tell you whether their backups actually work. Here’s the rule we build every client’s recovery plan around — and how to test yours in fifteen minutes.",
     "sections": [
        {"h2": "What 3-2-1 actually means", "body": ["<strong>3 copies</strong> of anything you can’t afford to lose — the live copy plus two backups.", "<strong>2 different kinds of media</strong> so one failure can’t take out both backups.", "<strong>1 copy off-site</strong> (cloud counts) so a fire, flood, or ransomware hitting the office doesn’t take the backup with it."]},
        {"h2": "The part people skip", "body": "A backup you’ve never restored from is a hope, not a backup. Once a quarter, actually pull a file back from each copy and confirm it opens. The first time you test a backup should never be the day you need it."},
     ]},
    {"title": "Multi-Factor Authentication Is the Cheapest Insurance You’ll Ever Buy",
     "excerpt": "MFA blocks the vast majority of account takeovers, costs nothing, and takes an afternoon. Here’s where to turn it on first.",
     "intro": "If I could get every business owner in Texas to do one security thing this week, it wouldn’t be a fancy firewall. It would be turning on multi-factor authentication everywhere it’s offered. Here’s why, and where to start.",
     "sections": [
        {"h2": "Why a stolen password isn’t enough anymore", "body": "Passwords leak — in breaches, in phishing, in reused-everywhere habits. MFA means a leaked password alone can’t get anyone in; they’d also need the code on your phone. That single extra step stops the overwhelming majority of account takeovers."},
        {"h2": "Turn it on here first", "body": ["Email — it’s the master key that resets every other password.", "Banking and payroll.", "Your Microsoft 365 or Google Workspace admin account.", "Anything with customer data."]},
        {"h2": "Skip SMS if you can", "body": "Text-message codes are better than nothing, but an authenticator app (or a hardware key) can’t be intercepted by SIM-swapping. Five minutes to set up, and it’s meaningfully stronger."},
     ]},
    {"title": "“We’re Too Small to Be a Target” Is Exactly Why You’re a Target",
     "excerpt": "Attackers automate. They don’t pick you — they scan everyone and hit whoever’s unlocked. Small doesn’t mean invisible.",
     "intro": "It’s the most common thing I hear from small business owners: “Who’d bother with us?” I understand the instinct. It’s also exactly backwards, and here’s the honest reason.",
     "sections": [
        {"h2": "Attacks are automated, not personal", "body": "The people trying doors on the internet aren’t hand-picking victims. They run software that scans millions of addresses looking for anything unpatched or misconfigured, then hit whatever’s open. Your size never comes up — only whether your door was locked."},
        {"h2": "Small businesses are the sweet spot", "body": "Big enough to have money and data worth taking, small enough to often lack a dedicated IT team. That combination is why small and mid-sized businesses absorb a huge share of attacks — not despite being small, but because of it."},
     ]},
    {"title": "The Email That Looks Real Is the Whole Problem",
     "excerpt": "Modern phishing doesn’t look like a scam. It looks like your boss, your vendor, your bank. Here’s how to slow down and catch it.",
     "intro": "The Nigerian-prince email was easy to laugh off. Today’s phishing is a short, polite note that looks exactly like it came from your boss or your bookkeeper. That’s the point — and here’s how to spot it anyway.",
     "sections": [
        {"h2": "The tells that still work", "body": ["Urgency — “right now,” “before end of day,” “don’t call me, I’m in a meeting.”", "A payment detail that changed — new bank account, new wiring instructions.", "A reply-to address that’s subtly off from the name shown.", "A link that doesn’t match where it claims to go (hover before you click)."]},
        {"h2": "The one habit that beats all of it", "body": "For anything involving money or credentials, verify through a second channel you already trust — call the person on the number you have, not the one in the email. Thirty seconds of friction has saved businesses tens of thousands of dollars."},
     ]},
    {"title": "Your Firewall Is Not Your Whole Security Plan",
     "excerpt": "A firewall matters, but it’s one layer. Real security is a stack — and most breaches walk in through the gaps between.",
     "intro": "“We have a firewall” is a sentence I hear a lot, usually as a full answer to “how’s your security?” A firewall is real and useful. It’s also one layer of many, and attackers make their living in the gaps.",
     "sections": [
        {"h2": "What a firewall does and doesn’t do", "body": "It controls traffic in and out of your network — valuable. It does nothing about a phished password, a malicious email attachment, an unpatched laptop, or an employee clicking a bad link. Those don’t knock on the firewall; they’re invited in."},
        {"h2": "Think in layers", "body": ["Patched, up-to-date devices.", "MFA on every account.", "Endpoint protection that catches malware on the machine itself.", "Backups you’ve tested.", "People who know how to spot a scam."]},
     ]},
    {"title": "Patch Management: The Boring Habit That Prevents the Emergencies",
     "excerpt": "Most breaches exploit a flaw that already had a fix available. Staying patched is unglamorous and it works.",
     "intro": "When you read about a big breach, the flaw usually had a patch available — sometimes for months. The break-in wasn’t clever; it was a door someone forgot to close. Boring, consistent patching is how you close them.",
     "sections": [
        {"h2": "Why the gap exists", "body": "Updates are annoying. They interrupt work, occasionally break things, and it’s easy to click “remind me later” forever. Attackers count on exactly that delay — the window between a fix being released and you installing it is their opportunity."},
        {"h2": "Make it automatic", "body": "The fix isn’t discipline, it’s automation: managed updates that install on a schedule, with someone watching for the rare one that needs a careful hand. Set it up once and the emergencies quietly stop happening."},
     ]},
]

_JP_EVERGREEN = [
    {"title": "The Best IT Decision Is Usually the Boring One",
     "excerpt": "The flashy tool rarely moves the needle. The unglamorous fundamentals — backups, MFA, patching — are what actually keep a business standing.",
     "intro": "After enough years doing this, I’ve noticed the technology that saves a business is almost never the exciting kind. It’s the boring, dependable stuff nobody posts about. I’ve made my peace with that, and honestly I’ve come to love it.",
     "sections": [
        {"h2": "Exciting fails loudly; boring works quietly", "body": "The dramatic tools get the attention, but when something goes wrong at 2am, what saves you is a backup that was quietly running the whole time and a login that needed a second factor. Nobody celebrates the disaster that didn’t happen — which is exactly why it’s worth building for."},
        {"h2": "Spend your attention where it compounds", "body": "Get the fundamentals right and most “IT emergencies” never start. That’s not a lack of ambition; it’s where the real leverage is. Solid, boring infrastructure is what lets a business take a swing at the exciting stuff without falling over."},
     ]},
    {"title": "What a Slow Response Really Costs You",
     "excerpt": "The follow-up nobody sends, the ticket that sits for a day — small delays quietly decide who keeps customers and who loses them.",
     "intro": "I think a lot about response time — not just in IT, in everything. The gap between “something broke” and “someone’s on it” is where trust is either built or quietly lost. Most businesses underrate how much that gap costs.",
     "sections": [
        {"h2": "People forgive problems, not silence", "body": "Nobody expects perfection. What they can’t stand is not knowing whether anyone heard them. A fast “we’ve got it, here’s what’s happening” buys more goodwill than a slow, perfect fix. Silence is the thing that ends relationships."},
        {"h2": "Speed is a system, not a hero", "body": "Fast response isn’t about someone heroically staying up late. It’s monitoring that catches the problem before the customer does, and a clear path for who picks it up. Build the system and the speed stops depending on any one person’s energy."},
     ]},
    {"title": "You Are Probably Your Business’s Single Point of Failure",
     "excerpt": "If the passwords, the vendor relationships, and the how-it-all-works live only in your head, the business can’t run without you — and it can’t grow past you either.",
     "intro": "Here’s an uncomfortable exercise I put owners through: if you vanished for two weeks with no warning, what would break? For most small businesses the honest answer is “nearly everything,” and it’s worth sitting with why.",
     "sections": [
        {"h2": "Convenience today, fragility tomorrow", "body": "It’s efficient to keep it all in your head — the passwords, the vendor contacts, the reason things are set up the way they are. Right up until you’re sick, on vacation, or hit by a bus, and nobody else can log in or knows who to call. Convenient and fragile are often the same decision."},
        {"h2": "Write it down; share the keys", "body": "A password manager the right people can access. A short doc of critical vendors and accounts. Backups someone other than you can restore. None of it is glamorous, and all of it is what lets a business survive its founder — and eventually outgrow them."},
     ]},
    {"title": "The Twenty Minutes on Friday That Make Monday Easy",
     "excerpt": "A small end-of-week habit — close the loops, note where you stopped, tidy the desk — quietly buys back your Monday morning.",
     "intro": "For years my Fridays ended mid-thought: laptop closed, half-finished task, a vague promise to remember on Monday where I left off. I never did. The fix turned out to be about twenty minutes, and it changed how my weeks feel.",
     "sections": [
        {"h2": "Close the open loops", "body": "The last twenty minutes of the week, I write down exactly where each open thing stands and what the next step is. Not a plan — just a breadcrumb trail so Monday-morning me doesn’t have to reconstruct Friday-afternoon me’s brain from scratch."},
        {"h2": "Protect the handoff to yourself", "body": "You hand off work to your future self every single day. Most people are terrible teammates to that person. Twenty quiet minutes to set them up well is the highest-return meeting on my calendar, and it’s with me."},
     ]},
    {"title": "Where AI Actually Saves a Small Business Time — and Where It Just Wastes It",
     "excerpt": "AI is genuinely useful for the boring 80% and genuinely dangerous for the judgment calls. Knowing the line is the whole skill.",
     "intro": "Everyone wants to know if they should be “using AI” in their business. It’s the wrong question. The right one is <em>where</em> — because it’s a fantastic assistant for some things and a confident liar about others.",
     "sections": [
        {"h2": "Great at the boring, repetitive 80%", "body": ["First drafts you’re going to edit anyway.", "Summarizing long threads and documents.", "Turning messy notes into a clean checklist.", "Rewriting the same message for three different audiences."]},
        {"h2": "Keep a human on the judgment calls", "body": "Anything with legal, financial, or safety weight — or anything where being confidently wrong is expensive — needs a person who owns the outcome. AI drafts; you decide. Blur that line and it’ll eventually cost you more time than it ever saved."},
     ]},
    {"title": "The Cheapest Growth Move Is Turning On What You Already Pay For",
     "excerpt": "Most businesses are sitting on features inside tools they already own. Before you buy the next thing, use the thing you’ve got.",
     "intro": "Before a client spends on a shiny new platform, I ask to see what they already pay for. Almost every time, half the answer they were about to buy is sitting unused inside a subscription they’ve had for two years.",
     "sections": [
        {"h2": "You’re probably paying for tools you never turned on", "body": "Microsoft 365, your CRM, your accounting software — they’ve quietly grown features you’re not touching. Automations, security settings, reporting, integrations. It’s money already spent, delivering nothing, waiting to be switched on."},
        {"h2": "Audit before you add", "body": "Once or twice a year, list what you pay for monthly and what each one actually does for you. The exercise usually finds two things: subscriptions to cancel, and features to finally use. Both make you money, and neither requires buying anything new."},
     ]},
]


def _compose_bvtech_deterministic(now: datetime) -> dict:
    """Zero-token evergreen bvtech blog post (rotates daily). The floor that
    publishes when no LLM is available."""
    topic = _BV_EVERGREEN[now.toordinal() % len(_BV_EVERGREEN)]
    return _render_evergreen(topic, byline="BVTech LLC", cta_html=_BV_CTA,
                             date_str=now.date().isoformat())


def _compose_jp_deterministic(now: datetime) -> dict:
    """Zero-token evergreen founder post for jordanpolasek.com (rotates daily)."""
    topic = _JP_EVERGREEN[now.toordinal() % len(_JP_EVERGREEN)]
    art = _render_evergreen(topic, byline="Jordan Polasek", cta_html=_JP_CTA,
                            date_str=now.date().isoformat())
    return art


def _publish_news_edition(db: Session, now: datetime) -> str:
    """Daily KEV briefing to bvtech.org/news/ (its own page + index), cloned
    from the newest existing edition's markup. 1/day rides the bvtech cap.

    v1.49: composed DETERMINISTICALLY from the CISA KEV feed — ZERO AI tokens.
    Factual security bulletins don't need a language model. AI is opt-in only
    (PULSE_NEWS_AI=1), and even then the deterministic edition is the fallback,
    so the /news/ page publishes daily even when the AI balance is exhausted."""
    import os as _os
    if _os.environ.get("PULSE_DISABLE_KEV_TICKER"):
        return ""
    from . import jp_site
    try:
        kev = jp_site._KEV_FETCH(6)
        if not kev:
            return " | news: no KEV data available"
        npost = None
        if _os.environ.get("PULSE_NEWS_AI") and ai.enabled():
            items = "; ".join(f"{k['cve']} ({k['vendor']} {k['product']}: {k['name']}, "
                              f"added {k['added']}, federal due {k['due']})" for k in kev)
            try:
                raw = ai.complete(_NEWS_SYSTEM,
                                  f"Today: {now:%B %d, %Y}. Real CISA KEV entries to cover "
                                  f"(exact facts): {items}", smart=True, max_tokens=4000)
                npost = ai.parse_article(raw)
            except Exception:  # noqa: BLE001 — AI down/exhausted -> deterministic
                npost = None
        if not npost:
            npost = _compose_news_deterministic(now, kev)   # zero-token default
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
    # the HTML) + JSON fallback + ONE corrective retry. v1.50: the whole LLM
    # path is wrapped — if it's down/exhausted/unparseable, fall to the
    # zero-token evergreen floor so JP publishes daily regardless.
    post = None
    try:
        raw = ai.complete(_JP_SYSTEM, prompt, smart=True, max_tokens=4000)
        post = ai.parse_article(raw)
        if not post:
            raw = ai.complete(_JP_SYSTEM, prompt + "\nIMPORTANT: use EXACTLY the "
                              "TITLE:/EXCERPT:/HTML: format - nothing before TITLE:, "
                              "no JSON, no code fences.",
                              smart=True, max_tokens=4000)
            post = ai.parse_article(raw)
    except Exception:  # noqa: BLE001
        post = None
    if not post:
        post = _compose_jp_deterministic(now)
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
