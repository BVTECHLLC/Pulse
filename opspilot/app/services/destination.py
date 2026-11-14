"""Publish the "BVTech as a destination" release to bvtech.org (v1.102):

  * /explore/                    — the Yahoo-style front page (pages_explore)
  * /academy/lightning-labs/     — free interactive labs (pages_labs)
  * /tools/<slug>/               — What's My IP, Speed Test, Is It Down, EV Savings
  * worker-tools/*.js            — the edge API behind all of the above
  * site-wide nav links          — Explore + Lightning Labs, added idempotently
  * tools index cards + sitemap  — so the new pages are found
  * 404 telemetry                — the 404 page reports misses to the Worker

Everything new ships in ONE GitLab commit (so a build never sees pages whose
Worker endpoints haven't landed), then the edge cache is purged. Idempotent and
self-healing: the daily repair re-runs it if any piece goes missing. Pages are
built inside the site's own chrome (head/nav/footer from an existing page), so
they match the site without us hand-writing its markup. Authored under Jordan
Polasek for SEO on his name.
"""
from __future__ import annotations

import html as _html
import re
from pathlib import Path

from sqlalchemy.orm import Session

from . import pages_explore, pages_labs, pages_tools, pages_game, pages_local, pages_offer, captcha

AUTHOR = "Jordan Polasek"
ORG = "BVTech LLC"
SITE = "https://bvtech.org"

# Worker modules that power the new pages (published to worker-tools/ next to the
# existing tool files). Keyed by repo path -> local file in edge_tools/.
_EDGE_DIR = Path(__file__).with_name("edge_tools")
NEW_EDGE = {"worker-tools/feeds.js": "feeds.js",
            "worker-tools/explore.js": "explore.js",
            "worker-tools/netinfo.js": "netinfo.js",
            "worker-tools/labs.js": "labs.js",
            "worker-tools/daily.js": "daily.js",
            "worker-tools/answers.js": "answers.js"}

# Pages to publish: (repo_path, title, description, body, author). Folder-style
# URLs (…/index.html) to match the site's /tools/<slug>/ convention.
EXPLORE_PATH = "explore/index.html"
LABS_PATH = "academy/lightning-labs/index.html"
GAME_PATH = "graveyard-shift/index.html"


def _pages() -> list[dict]:
    out = [
        {"path": EXPLORE_PATH, "url": SITE + "/explore/",
         "title": pages_explore.TITLE, "desc": pages_explore.DESC,
         "body": pages_explore.body()},
        {"path": LABS_PATH, "url": SITE + "/academy/lightning-labs/",
         "title": pages_labs.TITLE, "desc": pages_labs.DESC, "body": pages_labs.body()},
        {"path": GAME_PATH, "url": SITE + "/graveyard-shift/",
         "title": pages_game.TITLE, "desc": pages_game.DESC, "body": pages_game.body()},
        pages_offer.review_offer(),   # /free-review/ — the lead-capture offer page
    ]
    for t in pages_tools.all_tools():
        page = {"path": f"tools/{t['slug']}/index.html",
                "url": f"{SITE}/tools/{t['slug']}/", "title": t["title"],
                "desc": t["desc"], "body": t["body"]}
        if t.get("faqs"):            # forward FAQ -> FAQPage schema (_schema)
            page["faqs"] = t["faqs"]
        out.append(page)
    out += pages_local.city_pages()          # local service-area SEO pages
    return out


# BVTech's local identity — one shared ProfessionalService node every page points
# at, so search + AI engines read a single, consistent business with explicit
# Texas service areas (Houston / Austin / San Antonio). No street/phone is
# fabricated; add real NAP here when a Google Business Profile is set up.
SERVICE_CITIES = ["Houston", "Austin", "San Antonio", "Sugar Land"]
SERVICE_TYPES = ["Managed IT Services", "Cybersecurity", "Cloud Migration",
                 "Microsoft 365 Management", "IT Support & Helpdesk",
                 "Network & Server Management", "Compliance (HIPAA, PCI, CMMC)",
                 "Backup & Disaster Recovery", "vCIO / IT Strategy"]


def _org_node() -> dict:
    return {
        "@type": ["Organization", "ProfessionalService"],
        "@id": SITE + "/#org", "name": ORG, "alternateName": "BVTech",
        "url": SITE, "email": "help@bvtech.org",
        "slogan": "Managed IT & cybersecurity for Texas small businesses",
        "description": ("Texas-based managed IT services provider (MSP) and "
                        "cybersecurity company serving small and mid-sized "
                        "businesses in Houston, Austin, San Antonio and across Texas."),
        "areaServed": ([{"@type": "City", "name": c} for c in SERVICE_CITIES]
                       + [{"@type": "State", "name": "Texas"}]),
        "serviceType": SERVICE_TYPES, "knowsAbout": SERVICE_TYPES,
        "address": {"@type": "PostalAddress", "addressRegion": "TX", "addressCountry": "US"},
        "founder": {"@type": "Person", "name": AUTHOR},
    }


def _schema(p: dict) -> str:
    import json as _json
    graph = [
        {"@type": "WebPage", "@id": p["url"] + "#webpage",
         "name": p["title"].split("|")[0].strip(), "description": p["desc"],
         "url": p["url"], "isPartOf": {"@id": SITE + "/#website"},
         "about": {"@id": SITE + "/#org"}, "publisher": {"@id": SITE + "/#org"},
         "author": {"@type": "Person", "name": AUTHOR, "url": SITE}},
        {"@type": "WebSite", "@id": SITE + "/#website", "url": SITE, "name": ORG,
         "publisher": {"@id": SITE + "/#org"}},
        _org_node(),
    ]
    faqs = p.get("faqs")
    if faqs:
        graph.append({"@type": "FAQPage", "@id": p["url"] + "#faq",
                      "mainEntity": [{"@type": "Question", "name": q,
                                      "acceptedAnswer": {"@type": "Answer", "text": a}}
                                     for q, a in faqs]})
    data = {"@context": "https://schema.org", "@graph": graph}
    return '<script type="application/ld+json">' + _json.dumps(data) + "</script>"


_VIEWPORT_META = ('<meta name="viewport" content="width=device-width, initial-scale=1, '
                  'viewport-fit=cover">')

# WCAG 2.2 AA quick wins applied to every built page: a visible keyboard focus
# ring on all interactive elements (2.4.7 / 2.4.11) and honouring reduced-motion
# (2.3.3). Scoped so it never fights the page's own :hover styles.
_A11Y_CSS = (
    '<style id="bv-a11y">'
    'a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,'
    'textarea:focus-visible,summary:focus-visible,[tabindex]:focus-visible{'
    'outline:3px solid #F5BE58!important;outline-offset:2px!important;border-radius:4px}'
    '@media (prefers-reduced-motion:reduce){*,*::before,*::after{'
    'animation-duration:.001ms!important;animation-iteration-count:1!important;'
    'transition-duration:.001ms!important;scroll-behavior:auto!important}}'
    '</style>')


def ensure_viewport(h: str) -> tuple[str, bool]:
    """Guarantee a correct, mobile/Tesla-friendly viewport on any page. The site
    chrome's own tag may be missing or weak (e.g. a fixed width), which makes a
    page render desktop-zoomed on phones and in-car browsers. Idempotent: a tag
    that already says width=device-width is left alone. Returns (html, changed)."""
    if not h or "<head" not in h.lower():
        return h, False
    m = re.search(r'<meta\s+name=["\']viewport["\'][^>]*>', h, re.I)
    if m:
        if "width=device-width" in m.group(0).lower():
            return h, False
        return h[:m.start()] + _VIEWPORT_META + h[m.end():], True
    hm = re.search(r'<head[^>]*>', h, re.I)
    if hm:
        return h[:hm.end()] + "\n" + _VIEWPORT_META + h[hm.end():], True
    return h, False


def build_page(chrome: str, p: dict) -> str:
    """Put a page body into the site chrome and fix head (title, desc, canonical,
    OG, one fresh schema block). Never touches nav/footer."""
    from . import content_studio
    h, _ = ensure_viewport(chrome)
    t = _html.escape(p["title"]); d = _html.escape(p["desc"], quote=True)
    h = re.sub(r"<title>.*?</title>", f"<title>{t}</title>", h, count=1, flags=re.S | re.I)
    h = re.sub(r'(<meta\s+name="description"\s+content=")[^"]*(")', lambda m: m.group(1) + d + m.group(2),
               h, count=1, flags=re.I)
    for prop, val in (("og:title", t), ("og:description", d), ("og:url", p["url"])):
        h = re.sub(rf'(<meta\s+property="{prop}"\s+content=")[^"]*(")', lambda m, v=val: m.group(1) + v + m.group(2),
                   h, count=1, flags=re.I)
    h = re.sub(r'(<link\s+rel="canonical"\s+href=")[^"]*(")', lambda m: m.group(1) + p["url"] + m.group(2),
               h, count=1, flags=re.I)
    # drop existing page-level ld+json blocks that describe the CLONED page, add ours
    h = re.sub(r'<script type="application/ld\+json">.*?</script>', "", h, flags=re.S)
    h = h.replace("</head>", _schema(p) + "\n" + _A11Y_CSS + "\n</head>", 1)
    return content_studio._swap_main(h, p["body"])


# --------------------------------------------------------------------------- #
# Site-wide nav: add Explore + Lightning Labs. Additive and idempotent — a page
# only changes if it has the anchor AND lacks the new link, and nothing is ever
# removed. Pages whose nav we don't recognize are skipped, never corrupted.
# --------------------------------------------------------------------------- #
NAV_EDITS = [
    # (already-present marker, anchor to insert AFTER, html to insert)
    ('href="/explore/"', '<li><a href="/tools/">🧰 Free Tools (all)</a></li>',
     '\n<li><a href="/explore/">🧭 Explore</a></li>'),
    ('href="/academy/lightning-labs/"', '<li><a href="/academy/labs/">🧪 Hands-On Labs</a></li>',
     '\n<li><a href="/academy/lightning-labs/">⚡ Lightning Labs</a></li>'),
    ('portal.bvtech.org/answers', '<li><a href="/academy/">🎓 Academy Home</a></li>',
     '\n<li><a href="https://portal.bvtech.org/answers">💬 BVTech Answers</a></li>'),
    ('/graveyard-shift/', '<li><a href="/academy/">🎓 Academy Home</a></li>',
     '\n<li><a href="/graveyard-shift/">🧛 Graveyard Shift</a></li>'),
    ('portal.bvtech.org/arena', '<li><a href="/academy/">🎓 Academy Home</a></li>',
     '\n<li><a href="https://portal.bvtech.org/arena/">⚔️ Play Breach Protocol</a></li>'),
]


def apply_nav(h: str) -> tuple[str, bool]:
    changed = False
    for present, anchor, ins in NAV_EDITS:
        if present in h:
            continue                       # already has this link
        i = h.find(anchor)
        if i < 0:
            continue
        at = i + len(anchor)
        h = h[:at] + ins + h[at:]
        changed = True
    return h, changed


# Top-level nav: add an Explore item next to Blog (most visible). Tolerant: only
# where a top-level Blog link exists and Explore isn't already top-level.
# The top-level Explore link carries a small "NEW" badge so visitors notice it.
# Inline-styled so it looks right regardless of the page's own nav CSS.
_NEW_BADGE = ('<span style="display:inline-block;margin-left:5px;padding:1px 6px;border-radius:999px;'
              'background:linear-gradient(135deg,#EB6F24,#F5BE58);color:#0E0D2C;font-size:.6rem;'
              'font-weight:800;letter-spacing:.06em;vertical-align:middle">NEW</span>')
_TOP_EXPLORE = '<li><a href="/explore/">🧭 Explore' + _NEW_BADGE + '</a></li>'
_TOP_EXPLORE_OLD = '<li><a href="/explore/">Explore</a></li>'


def apply_top_nav(h: str) -> tuple[str, bool]:
    # Only skip if the badged TOP-LEVEL item already exists (the dropdown's
    # "🧭 Explore" link must not count, or the most-clickable spot never gets it).
    if _TOP_EXPLORE in h:
        return h, False
    if _TOP_EXPLORE_OLD in h:                      # migrate v1.102 plain link -> badged
        return h.replace(_TOP_EXPLORE_OLD, _TOP_EXPLORE, 1), True
    m = re.search(r'(<li[^>]*>\s*<a href="/blog/"[^>]*>\s*Blog\s*</a>\s*</li>)', h)
    if not m:
        return h, False
    return h[:m.end()] + "\n" + _TOP_EXPLORE + h[m.end():], True


# --------------------------------------------------------------------------- #
# Business ⇄ Academy mode bar (v1.133). A self-contained, fully-scoped band that
# reframes the whole site as two clear audiences: the MSP/IT BUSINESS side
# (services, tools, blog, book a review) and the free ACADEMY side (labs,
# answers, explore, arcade). It never touches or removes the page's own nav —
# it is added under the header as an additive layer, so it is safe on a live
# site whose exact nav markup we don't control. Everything is scoped under
# #bvModeBar, the visible mode is chosen from the URL (with a remembered manual
# override for neutral pages), and the toggle switches link sets client-side.
# Idempotent: a page that already has id="bvModeBar" is skipped.
# --------------------------------------------------------------------------- #
_MODEBAR_MARKER = 'id="bvModeBar"'

# Links are grouped by audience. Each: (href, label). The first business entry
# and first academy entry double as that mode's "home" for the heading link.
_MODEBAR_BIZ = [
    ("/", "🏠 Home"),
    ("/tools/", "🧰 Free Tools"),
    ("/blog/", "📰 Blog"),
    ("/academy/", "🎓 Academy ›"),          # cross-link so each side reaches the other
]
_MODEBAR_BIZ_CTA = ("/free-review/", "🛡️ Free Security Review")
_MODEBAR_ACA = [
    ("/academy/", "🎓 Academy Home"),
    ("/academy/labs/", "🧪 Hands-On Labs"),
    ("/academy/lightning-labs/", "⚡ Lightning Labs"),
    ("https://portal.bvtech.org/answers", "💬 Answers"),
    ("/explore/", "🧭 Explore"),
    ("/kart/", "🏎️ Arcade"),
    ("/", "💼 Business ›"),                   # cross-link back to the business side
]


def _modebar_links(group: list) -> str:
    return "".join(f'<a href="{href}">{label}</a>' for href, label in group)


def _mode_bar_html() -> str:
    biz = _modebar_links(_MODEBAR_BIZ)
    biz += (f'<a class="bv-cta" href="{_MODEBAR_BIZ_CTA[0]}">{_MODEBAR_BIZ_CTA[1]}</a>')
    aca = _modebar_links(_MODEBAR_ACA)
    css = (
        '#bvModeBar{--bvNavy:#0E0D2C;--bvBlue:#4440DB;--bvOrange:#EB6F24;--bvGold:#F5BE58;'
        'font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'background:linear-gradient(90deg,#0E0D2C 0%,#201b4d 60%,#2a1f54 100%);'
        'border-top:1px solid rgba(255,255,255,.06);border-bottom:2px solid var(--bvGold);'
        'box-shadow:0 6px 18px -10px rgba(0,0,0,.6);position:relative;z-index:50}'
        '#bvModeBar *{box-sizing:border-box}'
        '#bvModeBar .bv-in{max-width:1200px;margin:0 auto;display:flex;align-items:center;'
        'gap:14px;padding:9px 16px;flex-wrap:wrap}'
        '#bvModeBar .bv-seg{display:inline-flex;background:rgba(255,255,255,.07);'
        'border:1px solid rgba(255,255,255,.14);border-radius:999px;padding:3px;flex:0 0 auto}'
        '#bvModeBar .bv-seg button{appearance:none;border:0;cursor:pointer;font:inherit;'
        'font-weight:800;letter-spacing:.02em;color:#cdd0ea;background:transparent;'
        'padding:6px 15px;border-radius:999px;display:flex;align-items:center;gap:6px;'
        'font-size:.86rem;transition:.18s}'
        '#bvModeBar .bv-seg button:hover{color:#fff}'
        '#bvModeBar[data-mode="business"] .bv-b,#bvModeBar[data-mode="academy"] .bv-a{'
        'background:linear-gradient(135deg,var(--bvOrange),var(--bvGold));color:var(--bvNavy);'
        'box-shadow:0 2px 10px -2px rgba(245,190,88,.5)}'
        '#bvModeBar .bv-links{display:flex;align-items:center;gap:4px;flex:1 1 auto;'
        'overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none}'
        '#bvModeBar .bv-links::-webkit-scrollbar{display:none}'
        '#bvModeBar .bv-links a{white-space:nowrap;color:#e7e9f7;text-decoration:none;'
        'font-weight:600;font-size:.86rem;padding:6px 11px;border-radius:9px;transition:.15s}'
        '#bvModeBar .bv-links a:hover{background:rgba(255,255,255,.1);color:#fff}'
        '#bvModeBar .bv-links a.bv-cta{background:linear-gradient(135deg,var(--bvOrange),'
        'var(--bvGold));color:var(--bvNavy);font-weight:800;margin-left:4px}'
        '#bvModeBar .bv-links a.bv-cta:hover{filter:brightness(1.07)}'
        '#bvModeBar .bv-grp{display:none;align-items:center;gap:4px}'
        '#bvModeBar[data-mode="business"] .bv-grp-b{display:flex}'
        '#bvModeBar[data-mode="academy"] .bv-grp-a{display:flex}'
        '#bvModeBar .bv-tag{flex:0 0 auto;font-size:.66rem;font-weight:800;letter-spacing:.08em;'
        'text-transform:uppercase;color:var(--bvGold);opacity:.8;padding-right:2px}'
        '@media(max-width:640px){#bvModeBar .bv-in{gap:8px;padding:8px 12px}'
        '#bvModeBar .bv-tag{display:none}#bvModeBar .bv-seg button{padding:6px 12px;font-size:.8rem}}'
    )
    # noscript-safe: links render for crawlers; JS only toggles visibility.
    js = (
        "(function(){var b=document.getElementById('bvModeBar');if(!b)return;"
        "function infer(){var p=(location.pathname||'/').toLowerCase();"
        "if(p.indexOf('/academy')===0||p.indexOf('/explore')===0||p.indexOf('graveyard-shift')>-1"
        "||p.indexOf('lightning-labs')>-1||p.indexOf('/kart')===0||p.indexOf('/arena')===0)return'academy';"
        "if(p==='/'||p===''||p.indexOf('/404')>-1){try{return localStorage.getItem('bvMode')||'business';}"
        "catch(e){return'business';}}return'business';}"
        "function set(m,save){b.setAttribute('data-mode',m);"
        "if(save){try{localStorage.setItem('bvMode',m);}catch(e){}}}"
        "b.querySelector('.bv-b').addEventListener('click',function(){set('business',1);});"
        "b.querySelector('.bv-a').addEventListener('click',function(){set('academy',1);});"
        "set(infer(),0);})();"
    )
    return (
        f'<style>{css}</style>'
        f'<nav id="bvModeBar" data-mode="business" aria-label="Business and Academy modes">'
        '<div class="bv-in">'
        '<span class="bv-tag">Choose&nbsp;your&nbsp;path</span>'
        '<div class="bv-seg" role="tablist">'
        '<button type="button" class="bv-b" role="tab" aria-label="Business mode">💼 Business</button>'
        '<button type="button" class="bv-a" role="tab" aria-label="Academy mode">🎓 Academy</button>'
        '</div>'
        f'<div class="bv-links bv-grp bv-grp-b">{biz}</div>'
        f'<div class="bv-links bv-grp bv-grp-a">{aca}</div>'
        '</div></nav>'
        f'<script>{js}</script>'
    )


def apply_mode_bar(h: str) -> tuple[str, bool]:
    """Insert the Business/Academy mode bar under the page header (or at the top
    of <body>) if it isn't already there. Idempotent and tolerant: a page with
    no <body>, or one we can't place it in, is left untouched. Full-screen game
    shells are skipped so the bar never overlaps a canvas."""
    if _MODEBAR_MARKER in h:
        return h, False
    low = h.lower()
    # Never cover a full-screen game/app shell.
    if "/graveyard-shift/" in h and "<canvas" in low:
        return h, False
    bar = _mode_bar_html()
    m = re.search(r"</header>", h, flags=re.I)        # preferred: right under the header
    if m:
        return h[:m.end()] + "\n" + bar + h[m.end():], True
    m = re.search(r"<body\b[^>]*>", h, flags=re.I)    # fallback: top of body
    if m:
        return h[:m.end()] + "\n" + bar + h[m.end():], True
    return h, False


# Self-hosted browser libraries for the PDF tools. The site CSP is default-src
# 'self', so these can't load from a CDN — they ship as same-origin files under
# /tools/lib/ and are published ONCE (skipped on later publishes if already there).
_TOOL_LIBS_DIR = Path(__file__).with_name("tool_libs")
_TOOL_LIB_FILES = {
    "tools/lib/pdf-lib.min.js": "pdf-lib.min.js",
    "tools/lib/pdf.min.js": "pdf.min.js",
    "tools/lib/pdf.worker.min.js": "pdf.worker.min.js",
}


def _add_tool_libs(files: dict, existing: set | None) -> None:
    for pub, local in _TOOL_LIB_FILES.items():
        if existing is not None and pub in existing:
            continue                       # already published — don't re-commit ~2MB
        p = _TOOL_LIBS_DIR / local
        try:
            files[pub] = p.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass


_TOOLS_GRID_MARKER = 'id="bv-instant-tools"'


def _instant_tools_section() -> str:
    """One clean, searchable, self-contained grid of every in-house browser tool
    (v1.139) — replaces the old per-tool blog-card injection that stacked a 'wall
    of text' with a repeated promo box under each tool. Scoped under
    #bv-instant-tools so it can't collide with the site's CSS."""
    cards = []
    for t in pages_tools.all_tools():
        slug, icon = t["slug"], t.get("icon", "🔧")
        title = _html.escape(t["card_title"])
        exc = re.sub(r"&amp;", "&", t.get("card_excerpt", ""))
        exc = _html.escape(re.sub(r"<[^>]+>", "", exc))
        dn = _html.escape((t["card_title"] + " " + t.get("card_excerpt", "")).lower(), quote=True)
        cards.append(
            f'<a class="bvt-card" href="/tools/{slug}/" data-n="{dn}">'
            f'<span class="bvt-ic">{icon}</span><b>{title}</b><span class="bvt-x">{exc}</span></a>')
    # Two highlighted destinations at the end of the grid.
    cards.append('<a class="bvt-card bvt-cta" href="/free-review/" data-n="free security review it audit book">'
                 '<span class="bvt-ic">🛡️</span><b>Free Security Review</b>'
                 '<span class="bvt-x">A free 20-min IT &amp; security review for your business.</span></a>')
    cards.append('<a class="bvt-card" href="/explore/" data-n="explore tech news tesla space ai games">'
                 '<span class="bvt-ic">🧭</span><b>Explore</b>'
                 '<span class="bvt-x">The fun side of tech — news, space, AI &amp; a daily game.</span></a>')
    grid = "".join(cards)
    css = (
        '#bv-instant-tools{--o:#EB6F24;--o2:#F5BE58;max-width:1080px;margin:0 auto;padding:30px 18px 8px;'
        'font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif}'
        '#bv-instant-tools .bvt-head{text-align:center;margin:0 0 20px}'
        '#bv-instant-tools h2{font-size:clamp(1.5rem,3.6vw,2.1rem);color:#fff;margin:0 0 8px;font-weight:800}'
        '#bv-instant-tools .bvt-sub{color:#aab;max-width:620px;margin:0 auto 16px;font-size:.98rem;line-height:1.5}'
        '#bv-instant-tools .bvt-search{width:100%;max-width:440px;padding:12px 16px;border-radius:999px;'
        'border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.05);color:#fff;font-size:1rem}'
        '#bv-instant-tools .bvt-search::placeholder{color:#889}'
        '#bv-instant-tools .bvt-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(225px,1fr));gap:14px}'
        '#bv-instant-tools .bvt-card{display:flex;flex-direction:column;gap:5px;padding:18px 18px 16px;border-radius:14px;'
        'text-decoration:none;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.035);transition:.16s}'
        '#bv-instant-tools .bvt-card:hover{transform:translateY(-3px);border-color:rgba(245,190,88,.5);'
        'background:rgba(245,190,88,.07)}'
        '#bv-instant-tools .bvt-ic{font-size:1.7rem;line-height:1}'
        '#bv-instant-tools .bvt-card b{color:#fff;font-size:1.02rem;font-weight:700}'
        '#bv-instant-tools .bvt-x{color:#9aa0b5;font-size:.84rem;line-height:1.45}'
        '#bv-instant-tools .bvt-cta{border-color:rgba(245,190,88,.55);'
        'background:linear-gradient(135deg,rgba(235,111,36,.18),rgba(245,190,88,.1))}'
        '#bv-instant-tools .bvt-cta b{color:var(--o2)}'
        '#bv-instant-tools .bvt-empty{text-align:center;color:#9aa0b5;padding:18px;display:none}'
    )
    js = ("(function(){var r=document.getElementById('bv-instant-tools');if(!r)return;"
          "var s=r.querySelector('.bvt-search'),cards=[].slice.call(r.querySelectorAll('.bvt-card')),"
          "empty=r.querySelector('.bvt-empty');"
          "s.addEventListener('input',function(){var q=s.value.trim().toLowerCase(),n=0;"
          "cards.forEach(function(c){var m=!q||c.getAttribute('data-n').indexOf(q)>-1;"
          "c.style.display=m?'':'none';if(m)n++;});empty.style.display=n?'none':'block';});})();")
    return (
        f'<section {_TOOLS_GRID_MARKER}><style>{css}</style>'
        '<div class="bvt-head"><h2>🧰 Free Browser Tools</h2>'
        '<p class="bvt-sub">Fast, private, in-house tools — nothing to install, no signup, nothing '
        'leaves your device. Start typing to find one.</p>'
        '<input class="bvt-search" type="search" placeholder="Search tools… (speed, image, json, color)" aria-label="Search tools">'
        '</div>'
        f'<div class="bvt-grid">{grid}</div>'
        '<p class="bvt-empty">No tools match that search.</p>'
        f'<script>{js}</script></section>')


def _tools_index_cards(index_html: str) -> tuple[str, bool]:
    """Replace the old messy per-tool injection at the top of /tools/ with ONE
    clean, searchable grid (v1.139). On re-publish the grid is updated in place.
    The hand-written category grid below ('Check Your Security', …) is preserved;
    only the auto-generated mess above it is removed. Safe-fail: if the page's
    shape isn't recognized, the grid is simply inserted at the top of <main>."""
    h = index_html
    section = _instant_tools_section()
    # (a) already present -> update our block in place (idempotent re-publish)
    if _TOOLS_GRID_MARKER in h:
        new = re.sub(r'<section id="bv-instant-tools".*?</section>', section, h,
                     count=1, flags=re.S)
        return new, (new != index_html)
    mm = re.search(r"<main\b[^>]*>", h, re.I)
    if not mm:
        return h, False
    cstart = mm.end()
    # (b) remove the legacy mess: cut from <main> to just before the hand-written
    #     grid (its first category heading), keeping that grid intact.
    anchor = h.find("Check Your Security")
    if anchor > cstart:
        head_i = h.rfind("<h", cstart, anchor)
        boundary = head_i if head_i != -1 else anchor
        for tag in ("<section", "<div"):
            wi = h.rfind(tag, max(cstart, boundary - 700), boundary)
            if wi != -1:
                boundary = min(boundary, wi) if boundary != anchor else wi
        removed = h[cstart:boundary]
        if boundary > cstart and "Check Your Security" not in removed:
            return h[:cstart] + "\n" + section + "\n" + h[boundary:], True
    # (c) fallback: no recognizable hand-written grid — just put the clean grid first
    return h[:cstart] + "\n" + section + "\n" + h[cstart:], True


_404_PING = ('<script>/*pulse-404-ping*/(function(){try{fetch("/tools-api/notfound",{method:"POST",'
             'headers:{"Content-Type":"application/json"},body:JSON.stringify({path:location.pathname,'
             'ref:document.referrer||""})});}catch(e){}})();</script>')


def _wire_404(h: str) -> tuple[str, bool]:
    if "pulse-404-ping" in h or "</body>" not in h.lower():
        return h, False
    i = h.lower().rfind("</body>")
    return h[:i] + _404_PING + "\n" + h[i:], True


_SKIP_LINK = re.compile(r"^(#|mailto:|tel:|javascript:|data:|sms:|/cdn-cgi/|/tools-api/)", re.I)
_STATIC_OK = re.compile(r"\.(css|js|png|jpe?g|webp|gif|svg|ico|pdf|woff2?|ttf|xml|txt|json|mp4|webmanifest)$", re.I)


def _repo_index(cfg: dict) -> tuple[set, set]:
    """(all file paths, all directory paths) in the repo, for link resolution."""
    from . import jp_site
    out = []
    for page in range(1, 31):
        batch = jp_site._HTTP("GET", f"{jp_site._proj_url(cfg)}/repository/tree?recursive=true"
                              f"&per_page=100&page={page}&ref={cfg['branch']}", cfg["token"])
        out += batch or []
        if not batch or len(batch) < 100:
            break
    files = {t["path"] for t in out if t.get("type") == "blob"}
    dirs = {t["path"] for t in out if t.get("type") == "tree"}
    return files, dirs


def _exists(target: str, files: set, dirs: set) -> bool:
    t = target.strip("/")
    if t == "":
        return True                                  # site root
    if target.endswith("/"):
        return (t + "/index.html") in files or t in dirs
    last = t.rsplit("/", 1)[-1]
    if "." in last:
        return t in files
    # extensionless: a folder, a pretty page, or a .html file
    return (t + "/index.html") in files or (t + ".html") in files or t in dirs


def scan_links(db: Session, site: str = "bvtech", limit_pages: int = 400) -> dict:
    """Read-only broken-INTERNAL-link scan of the live repo, plus the real 404s
    visitors hit (telemetry). Reports what to fix; changes nothing."""
    from . import jp_site, secure_config
    cfg = jp_site.get_config(db, site)
    if not cfg["configured"]:
        return {"ok": False, "error": "not connected"}
    try:
        files, dirs = _repo_index(cfg)
        htmls = [p for p in files if p.endswith(".html") and not p.startswith("worker-tools/")]
        broken: dict = {}
        checked = 0
        for path in htmls[:limit_pages]:
            h = jp_site._fetch_file(cfg, path)
            if not h:
                continue
            checked += 1
            for m in re.finditer(r'(?:href|src)=["\']([^"\'>]+)["\']', h):
                raw = m.group(1).strip()
                if _SKIP_LINK.match(raw):
                    continue
                link = re.sub(r"^https?://(?:www\.)?bvtech\.org", "", raw, flags=re.I)
                if not link.startswith("/"):
                    continue                          # external or relative anchor
                link = link.split("#")[0].split("?")[0]
                if not link or _SKIP_LINK.match(link):
                    continue
                if not _exists(link, files, dirs):
                    broken.setdefault(link, []).append(path)
        # real-world 404s
        conn = secure_config.get_platform(db, "bvtech_404")
        hits = dict((conn.config if conn else {}).get("hits") or {})
        live404 = sorted(hits.items(), key=lambda kv: kv[1].get("count", 0), reverse=True)[:30]
        return {"ok": True, "pages_scanned": checked, "broken_internal": len(broken),
                "broken": {k: sorted(set(v))[:5] for k, v in sorted(
                    broken.items(), key=lambda kv: -len(kv[1]))[:40]},
                "live_404s": [{"path": k, "count": v.get("count"), "ref": v.get("ref", "")}
                              for k, v in live404]}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return {"ok": False, "error": str(e)[:300]}


def publish(db: Session) -> dict:
    """Ship the whole destination release to bvtech.org in one commit."""
    from . import cloudflare, content_studio, jp_site
    cfg = jp_site.get_config(db, "bvtech")
    if not cfg["configured"]:
        return {"ok": False, "error": "bvtech.org not connected"}
    try:
        ops = jp_site._repo_ops(cfg)
        chrome = ops["fetch"]("blog/index.html")
        if not chrome:
            return {"ok": False, "error": "no chrome page (blog/index.html)"}
        files: dict = {}
        # 1) worker modules (+ the re-exported worker entry from tools_page)
        from . import tools_page
        for repo_path, local in {**tools_page.EDGE_FILES, **NEW_EDGE}.items():
            files[repo_path] = (_EDGE_DIR / local).read_text()
        files[tools_page.JS_PATH] = tools_page.tool_js()
        # 2) new pages, built into the chrome
        pages = _pages()
        for p in pages:
            files[p["path"]] = build_page(chrome, p)
        # 3) wrangler wiring (idempotent) + .assetsignore for worker-tools/
        wname, wcontent, worker = tools_page.plan_worker(ops)
        if wcontent:
            files[wname] = wcontent
        ignore = ops["fetch"](".assetsignore")
        if ignore is not None and "worker-tools" not in ignore:
            files[".assetsignore"] = ignore.rstrip("\n") + "\nworker-tools/\n"
        # 4) tools index cards + banner
        ti = ops["fetch"]("tools/index.html")
        if ti:
            ni, ch = _tools_index_cards(ti)
            if ch:
                files["tools/index.html"] = ni
        # 5) 404 telemetry
        for p404 in ("404.html", "404/index.html"):
            pg = ops["fetch"](p404)
            if pg:
                np, ch = _wire_404(pg)
                if ch:
                    files[p404] = np
                break
        # 6) site-wide nav links (additive, idempotent) across every repo HTML
        nav_hits = _apply_nav_everywhere(cfg, files)
        # 6b) v1.152 — the live Threat Map page, written AFTER the sweep so it
        #     always ships pristine (self-contained chrome + Pulse-fed telemetry).
        try:
            from . import pages_threatmap as _tm, threat_feed as _tf
            import json as _json
            files[_tm.PATH] = _tm.html()
            # Same-origin data file the page reads (no cross-origin Cloudflare
            # challenge): refresh it with the REAL live snapshot every publish.
            files["cyber-range/threat-feed.json"] = _json.dumps(
                _tf.snapshot(db), separators=(",", ":"))
        except Exception:  # noqa: BLE001 — never let one page break the release
            pass
        # 6c) hidden easter-egg: "Surviving the AI Apocalypse" (self-contained,
        #     noindex, not in nav/sitemap — reachable only by direct link).
        try:
            from . import pages_survive_ai as _sa
            files[_sa.PATH] = _sa.html()
        except Exception:  # noqa: BLE001
            pass
        # commit — chunked, with create/update decided from one repo listing so a
        # big mode-bar rollout neither doubles GitLab load nor times out (v1.135).
        try:
            _existing = set(jp_site._list_all_paths(cfg))
        except Exception:  # noqa: BLE001
            _existing = None
        _add_tool_libs(files, _existing)   # self-hosted pdf-lib / pdf.js (published once)
        _commit(cfg, files, f"destination: Explore hub, Lightning Labs, {len(pages_tools.all_tools())} "
                f"new tools, Business/Academy mode bar, edge API + nav/sitemap "
                f"(via Pulse) [{nav_hits} nav pages]", existing=_existing)
        # 7) sitemap
        extra = {p["url"]: None for p in pages}
        sm = jp_site.sitemap_sync(db, "bvtech", extra=extra)
        # 8) purge
        purge = [p["url"] for p in pages] + [SITE + "/", SITE + "/tools/", SITE + "/academy/"]
        try:
            from . import pages_threatmap as _tm
            purge.append(_tm.URL)
        except Exception:  # noqa: BLE001
            pass
        try:
            from . import pages_survive_ai as _sa
            purge.append(_sa.URL)
        except Exception:  # noqa: BLE001
            pass
        cloudflare.purge_urls(db, "bvtech", purge)
        return {"ok": True, "pages": [p["url"] for p in pages], "nav_pages": nav_hits,
                "worker": worker, "sitemap": sm, "files": len(files)}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return {"ok": False, "error": str(e)[:300]}


def _apply_nav_everywhere(cfg: dict, files: dict) -> int:
    """Add the new nav links to every HTML page in the repo (additive) AND harden
    every page that has a lead/contact form with the bvHuman anti-spam widget.
    Pages we already rebuilt in `files` get edited in memory; the rest are
    fetched. Bounded and best-effort; a page we can't parse is left untouched."""
    from . import jp_site
    hits = 0
    # 1) harden the pages we just built (city pages, tools, explore, …) in memory:
    #    add the Business/Academy mode bar + anti-spam widget before they ship, so
    #    even first-publish pages (not yet in the repo sweep below) carry the bar.
    for path in list(files.keys()):
        if path.endswith(".html"):
            h, cm = apply_mode_bar(files[path])
            if cm:
                files[path] = h
            h, ch = captcha.inject(files[path])
            if ch:
                files[path] = h
    # 2) sweep the live repo: nav links + CAPTCHA on existing forms.
    #    v1.133: the per-file fetches below are a burst (up to 600 calls) that can
    #    trip GitLab's rate limit even with per-call retry, aborting the publish.
    #    Throttle only the calls that actually hit the network so the sweep spreads
    #    out instead of hammering GitLab; in-memory pages (already in `files`) are
    #    free and never sleep.
    import time as _time
    paths = [p for p in jp_site._list_all_html(cfg) if not p.startswith("worker-tools/")]
    for path in paths[:600]:
        base = files.get(path)
        if base is None:
            base = jp_site._fetch_file(cfg, path)
            _time.sleep(0.035)              # gentle throttle: ~spreads 600 fetches over ~20s
        if not base:
            continue
        changed = False
        if 'class="nav' in base or "<nav" in base or "/tools/" in base:
            h, c1 = apply_nav(base)
            h, c2 = apply_top_nav(h)
            if c1 or c2:
                base, changed = h, True
        h, cm = apply_mode_bar(base)        # idempotent Business/Academy mode bar
        if cm:
            base, changed = h, True
        h, c3 = captcha.inject(base)        # idempotent; only touches lead-form pages
        if c3:
            base, changed = h, True
        h, c4 = ensure_viewport(base)       # idempotent; mobile/Tesla viewport on every page
        if c4:
            base, changed = h, True
        if changed:
            files[path] = base
            hits += 1
    return hits


def _commit(cfg: dict, files: dict, message: str, existing: set | None = None) -> None:
    """Commit every file in `files`. v1.135: a big mode-bar rollout changes
    hundreds of pages, so (a) create-vs-update is decided from one repo listing
    (`existing`) instead of a GET per file, and (b) the commit is CHUNKED with a
    longer timeout so GitLab never times out on one giant request. This change is
    additive + idempotent, so partial progress across chunks is safe and the next
    publish self-heals anything left behind."""
    from . import jp_site
    if cfg.get("forge") == "github":
        for path, content in files.items():
            jp_site._repo_ops(cfg)["commit"](path, content, message,
                                             jp_site._fetch_file(cfg, path) is not None)
        return
    if existing is None:
        try:
            existing = set(jp_site._list_all_paths(cfg))
        except Exception:  # noqa: BLE001
            existing = None

    def _action(p: str) -> str:
        if existing is not None:
            return "update" if p in existing else "create"
        return "update" if jp_site._fetch_file(cfg, p) is not None else "create"

    # Infra/config + the interdependent release files first, bulk HTML last, so a
    # Workers build triggered mid-rollout sees supporting files before the pages.
    items = sorted(files.items(), key=lambda kv: (kv[0].endswith(".html"), kv[0]))
    chunk = 60
    total = (len(items) + chunk - 1) // chunk
    for i in range(0, len(items), chunk):
        part = items[i:i + chunk]
        actions = [{"action": _action(p), "file_path": p, "content": c} for p, c in part]
        msg = message if total == 1 else f"{message} [{i // chunk + 1}/{total}]"
        jp_site._HTTP("POST", f"{jp_site._proj_url(cfg)}/repository/commits", cfg["token"],
                      {"branch": cfg["branch"], "commit_message": msg, "actions": actions},
                      timeout=120)
