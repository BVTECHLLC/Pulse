"""BVTech Tech Dispatch (v1.104) — our OWN take on the day's tech news.

Instead of reposting other people's articles, we gather headlines from across the
web, then have our free LLM write an ORIGINAL, first-person BVTech commentary —
what caught our eye and why it matters for a small business — paraphrasing (never
copying), quoting only briefly with attribution, and linking every source at the
end. So we add value and send visitors to the originals, rather than scraping
them. Written in Jordan Polasek's voice and published natively to bvtech.org.

No AI = no dispatch: the whole point is that it's written as us, so if the LLM is
unreachable we simply skip the day rather than post filler.
"""
from __future__ import annotations

import html as _html
import re
import urllib.request
from datetime import datetime

# A small, reliable set of positive-leaning tech sources. Headlines only.
FEEDS = [
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("Engadget", "https://www.engadget.com/rss.xml"),
    ("BleepingComputer", "https://www.bleepingcomputer.com/feed/"),
    ("Electrek", "https://electrek.co/guides/tesla/feed/"),
    ("NASA", "https://www.nasa.gov/news-release/feed/"),
]

# Keep it positive and on-topic: no politics, tragedy or doom.
_BLOCK = re.compile(
    r"\b(trump|biden|harris|election|politic|republican|democrat|congress|senate|"
    r"war|missile|ukrain|russia|israel|gaza|hamas|abortion|immigration|shooting|"
    r"killed|dead|death|dies|murder|lawsuit|sued|indict|arrest|layoff|fired|"
    r"recession|crash(es|ed)?|scandal|controvers|boycott)\b", re.I)

_UA = "Mozilla/5.0 (compatible; BVTech-Dispatch/1.0; +https://bvtech.org)"


def _get(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _tag(block: str, name: str) -> str:
    m = re.search(rf"<{name}(?:\s[^>]*)?>([\s\S]*?)</{name}>", block, re.I)
    return m.group(1) if m else ""


def _clean(s: str) -> str:
    s = re.sub(r"<!\[CDATA\[([\s\S]*?)\]\]>", r"\1", s or "")
    s = re.sub(r"<[^>]+>", "", s)
    s = (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
         .replace("&#39;", "'").replace("&quot;", '"').replace("&#8217;", "’")
         .replace("&nbsp;", " ").replace("&hellip;", "…"))
    return re.sub(r"\s+", " ", s).strip()


def _parse(xml: str, source: str) -> list[dict]:
    out = []
    blocks = re.findall(r"<item[\s>][\s\S]*?</item>", xml, re.I) \
        or re.findall(r"<entry[\s>][\s\S]*?</entry>", xml, re.I)
    for b in blocks[:15]:
        title = _clean(_tag(b, "title"))
        link = _clean(_tag(b, "link"))
        if not link.startswith("http"):
            m = re.search(r'<link[^>]*href="([^"]+)"', b)
            link = m.group(1) if m else ""
        desc = _clean(_tag(b, "description") or _tag(b, "summary"))[:280]
        if title and link.startswith("https") and not _BLOCK.search(title + " " + desc):
            out.append({"title": title, "link": link, "source": source, "summary": desc})
    return out


def gather(limit: int = 9) -> list[dict]:
    """Fetch and curate the day's headlines across sources (best effort)."""
    items: list[dict] = []
    for source, url in FEEDS:
        try:
            items.extend(_parse(_get(url), source))
        except Exception:  # noqa: BLE001
            continue
    seen, uniq = set(), []
    for it in items:
        key = re.sub(r"[^a-z0-9]+", " ", it["title"].lower()).strip()[:60]
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    # spread across sources: round-robin so one feed doesn't dominate
    by_src: dict = {}
    for it in uniq:
        by_src.setdefault(it["source"], []).append(it)
    spread, i = [], 0
    while len(spread) < limit and any(by_src.values()):
        for src in list(by_src):
            if by_src[src]:
                spread.append(by_src[src].pop(0))
                if len(spread) >= limit:
                    break
        i += 1
        if i > 40:
            break
    return spread


_SYSTEM = (
    "You are Jordan Polasek, Founder of BVTech LLC — a Texas managed-IT and "
    "cybersecurity company. You write 'The BVTech Dispatch': a short, friendly, "
    "first-person round-up of what caught your eye in tech today and why it "
    "matters to a normal small business. You are NOT a news site. RULES:\n"
    "- Write ORIGINAL commentary in your own voice. Do NOT reproduce article text.\n"
    "- Paraphrase each story in your own words; you may quote at most 8 words from a "
    "headline, in quotes, with the source named. Never copy a paragraph.\n"
    "- For each pick, add YOUR take: why it's interesting or what it means for a "
    "small business owner. Be practical and upbeat. No politics, no doom.\n"
    "- Never invent facts; only use the headlines/summaries provided.\n"
    "Reply EXACTLY in this format:\n"
    "TITLE: <catchy dispatch title with today's date after an em dash>\n"
    "EXCERPT: <120-155 chars>\n"
    "HTML:\n<body: use <p>, <h2>, <strong>, <ul>/<li> only; 3-5 picks, each a short "
    "<h2> then a <p> of your take. End with <h2>Sources</h2> — but DO NOT write the "
    "source links yourself; the system appends them.>")


def _sources_html(items: list[dict]) -> str:
    lis = "".join(
        f'<li><a href="{_html.escape(it["link"])}" rel="noopener" target="_blank">'
        f'{_html.escape(it["title"])}</a> — {_html.escape(it["source"])}</li>'
        for it in items)
    return ("<h2>Sources &amp; further reading</h2><p>Credit where it's due — here are "
            "the original stories that caught our eye. Give them a read:</p>"
            f"<ul>{lis}</ul>")


def compose(db, now: datetime, items: list[dict]) -> dict | None:
    """Have the free LLM write the dispatch. Returns an article dict or None if
    the LLM is unavailable (we never publish filler for this)."""
    from . import ai
    if not items:
        return None
    briefing = "\n".join(f"- {it['title']} ({it['source']}): {it['summary'][:160]}"
                         for it in items)
    user = (f"Today is {now:%B %-d, %Y}. Here are today's headlines to react to. Pick the "
            f"3-5 most interesting for a small business audience:\n\n{briefing}")
    try:
        raw = ai.complete(_SYSTEM, user, max_tokens=1300)
    except Exception:  # noqa: BLE001 — LLM down: skip, don't post filler
        return None
    mt = re.search(r"TITLE:\s*(.+)", raw)
    me = re.search(r"EXCERPT:\s*(.+)", raw)
    mh = re.search(r"HTML:\s*([\s\S]+)", raw)
    if not (mt and mh):
        return None
    title = mt.group(1).strip()[:160]
    body = mh.group(1).strip()
    # drop any sources list the model wrote; append our own trustworthy one
    body = re.split(r"<h2>\s*sources", body, flags=re.I)[0].strip()
    body += _sources_html(items)
    excerpt = (me.group(1).strip()[:160] if me
               else "Our take on the tech worth knowing about today — and what it means for your business.")
    slug = "bvtech-dispatch-" + now.strftime("%Y-%m-%d")
    return {"title": title, "slug": slug, "html": body, "date": now.date().isoformat(),
            "description": excerpt, "excerpt": excerpt, "author": "Jordan Polasek",
            "tags": ["Tech Dispatch", "What We're Reading"], "crumb": "Tech Dispatch",
            "keywords": "tech news, BVTech dispatch, small business technology, Jordan Polasek"}


def maybe_run_daily(db, now: datetime | None = None) -> dict:
    """Heartbeat hook: publish today's dispatch at most once per day."""
    from . import secure_config
    now = now or datetime.utcnow()
    today = now.date().isoformat()
    conn = secure_config.get_platform(db, "dispatch_meta")
    raw = dict((conn.config if conn else None) or {})
    if raw.get("on") == today:
        return {"ran": False, "reason": "already_today"}
    ok, detail = run_dispatch(db, now)
    secure_config.upsert_platform(db, "dispatch_meta", "Tech Dispatch", "Publishing",
                                  {"on": today, "last": detail[:200]})
    return {"ran": True, "ok": ok, "detail": detail}


def run_dispatch(db, now: datetime | None = None) -> tuple[bool, str]:
    """Gather + compose + publish today's dispatch to bvtech.org. Skips cleanly
    when the LLM is down (no filler) or when today's is already posted."""
    from . import jp_site
    now = now or datetime.utcnow()
    if not jp_site.configured(db, "bvtech"):
        return False, "bvtech.org not connected"
    items = gather()
    if len(items) < 3:
        return True, "SKIPPED: not enough fresh headlines"
    article = compose(db, now, items)
    if not article:
        return True, "SKIPPED: AI unavailable (no filler for the dispatch)"
    if jp_site.post_exists(db, "bvtech", article["title"]):
        return True, "SKIPPED: already posted today"
    out = jp_site.publish(db, article, site="bvtech")
    if not out.get("ok"):
        return False, out.get("error") or "publish failed"
    return True, out.get("url") or article["title"]
