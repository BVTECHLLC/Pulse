"""v0.34 Content Studio — generate publish-ready, on-brand pages for BVTech.org.

This turns a title + body into a complete blog/security-advisory HTML page that
matches bvtech.org exactly. Two modes:

  * TEMPLATE-CLONE (preferred, pixel-perfect): given the HTML of an existing
    bvtech.org blog post as a skeleton, we swap in the new <title>, meta
    description, canonical/OG URLs, schema.org JSON-LD, <h1>, the dateline, and
    the article body — keeping the site's real header, footer, fonts, and CSS.
    Use this on the Linode box / in the website repo where a real post exists.

  * STANDALONE (no skeleton needed): a self-contained on-brand page using the
    BVTech design tokens, so previews work anywhere (e.g. inside the portal)
    before the website repo is wired up.

The text the post is *about* is written by Claude (daily, headless); this module
is the deterministic wrapper that makes the output safe to drop into /blog/.
No tenant data is ever embedded — these are public threat/advisory articles.
"""
from __future__ import annotations

import html
import re
from datetime import date as _date

SITE = "https://bvtech.org"
AUTHOR = "Jordan Polasek"
AUTHOR_URL = "https://jordanpolasek.com"
OG_IMAGE = f"{SITE}/assets/img/og-image.jpg"


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #
def slugify(title: str) -> str:
    s = (title or "").lower()
    s = re.sub(r"[‘’“”]", "", s)   # smart quotes
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return re.sub(r"-{2,}", "-", s)[:90] or "post"


def _inline(text: str) -> str:
    """Escape, then re-enable a tiny, safe markdown subset: **bold**, *italic*,
    [text](url), and `code`. URLs are restricted to http(s)/mailto."""
    t = html.escape(text, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", t)

    def _link(m):
        label, url = m.group(1), m.group(2)
        if not re.match(r"^(https?://|mailto:|/)", url):
            return label
        return f'<a href="{html.escape(url, quote=True)}">{label}</a>'

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link, t)


def markdown_lite(body: str) -> str:
    """Convert a lightweight markdown body to the site's article HTML:
    `## h2`, `### h3`, `- ` bullet lists, `> ` callouts, and paragraphs."""
    out: list[str] = []
    lines = (body or "").replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.startswith("### "):
            out.append(f"<h3>{_inline(line[4:].strip())}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2>{_inline(line[3:].strip())}</h2>")
        elif line.startswith("# "):
            out.append(f"<h2>{_inline(line[2:].strip())}</h2>")  # h1 is the title
        elif line.startswith(("- ", "* ")):
            items = []
            while i < len(lines) and lines[i].strip().startswith(("- ", "* ")):
                items.append(f"<li>{_inline(lines[i].strip()[2:])}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        elif line.startswith("> "):
            out.append(f'<blockquote>{_inline(line[2:].strip())}</blockquote>')
        else:
            out.append(f"<p>{_inline(line.strip())}</p>")
        i += 1
    return "\n".join(out)


def _excerpt(body: str, limit: int = 155) -> str:
    text = re.sub(r"[#>*`\-]", "", (body or "")).strip()
    text = re.sub(r"\s+", " ", text)
    return (text[:limit].rsplit(" ", 1)[0] + "…") if len(text) > limit else text


# --------------------------------------------------------------------------- #
# Post model (plain dict in, validated here)
# --------------------------------------------------------------------------- #
def normalize_post(post: dict) -> dict:
    title = (post.get("title") or "").strip()
    if not title:
        raise ValueError("title is required")
    body = post.get("body") or ""
    slug = post.get("slug") or slugify(title)
    pub = post.get("date") or _date.today().isoformat()
    desc = (post.get("description") or _excerpt(body)).strip()
    return {
        "title": title,
        "slug": slug,
        "date": pub,
        "description": desc,
        "keywords": (post.get("keywords") or "").strip(),
        "author": post.get("author") or AUTHOR,
        "kind": post.get("kind") or "blog",   # blog | advisory
        "body_html": markdown_lite(body),
        "url": f"{SITE}/blog/{slug}.html",
    }


def _schema_blocks(p: dict) -> str:
    import json
    breadcrumb = {"@context": "https://schema.org", "@type": "BreadcrumbList",
                  "itemListElement": [
                      {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
                      {"@type": "ListItem", "position": 2, "name": "Blog", "item": f"{SITE}/blog/"},
                      {"@type": "ListItem", "position": 3, "name": p["title"]}]}
    article = {"@context": "https://schema.org", "@type": "BlogPosting",
               "headline": p["title"],
               "author": {"@type": "Person", "name": p["author"], "url": AUTHOR_URL,
                          "@id": f"{SITE}/#founder"},
               "publisher": {"@type": "Organization", "name": "BVTech LLC", "url": SITE,
                             "@id": f"{SITE}/#org",
                             "logo": {"@type": "ImageObject", "url": f"{SITE}/assets/img/logo.png"}},
               "url": p["url"], "mainEntityOfPage": p["url"],
               "datePublished": p["date"], "dateModified": p["date"],
               "image": OG_IMAGE, "inLanguage": "en",
               "description": p["description"]}
    if p["keywords"]:
        article["keywords"] = p["keywords"]
    return ('<script type="application/ld+json">' + json.dumps(breadcrumb) + "</script>\n"
            '<script type="application/ld+json">' + json.dumps(article) + "</script>")


# --------------------------------------------------------------------------- #
# Mode 1 — template clone (pixel-perfect parity with the live site)
# --------------------------------------------------------------------------- #
def render_from_skeleton(skeleton_html: str, post: dict) -> str:
    """Produce a new post by transplanting content into a real bvtech.org blog
    page (header/footer/CSS preserved verbatim). Robust to the exact markup:
    we replace the <title>, description, canonical+OG urls, the schema JSON-LD
    blocks, the <h1>, and the <article ...>…</article> (or .article-body) body."""
    p = normalize_post(post)
    h = skeleton_html
    dateline = _date.fromisoformat(p["date"]).strftime("%B %-d, %Y")

    # <title>
    h = re.sub(r"<title>.*?</title>",
               f"<title>{html.escape(p['title'])} | {p['author']} | BVTech LLC</title>",
               h, count=1, flags=re.S)
    # meta description
    h = re.sub(r'(<meta\s+name="description"\s+content=")(.*?)(")',
               lambda m: m.group(1) + html.escape(p["description"], quote=True) + m.group(3),
               h, count=1, flags=re.S)
    # canonical + og:url + the post URL anywhere it appears as a /blog/*.html
    h = re.sub(r'(<link\s+rel="canonical"\s+href=")(.*?)(")',
               lambda m: m.group(1) + p["url"] + m.group(3), h, count=1, flags=re.S)
    h = re.sub(r'(<meta\s+property="og:url"\s+content=")(.*?)(")',
               lambda m: m.group(1) + p["url"] + m.group(3), h, count=1, flags=re.S)
    h = re.sub(r'(<meta\s+property="og:title"\s+content=")(.*?)(")',
               lambda m: m.group(1) + html.escape(p["title"], quote=True) + m.group(3),
               h, count=1, flags=re.S)
    h = re.sub(r'(<meta\s+property="og:description"\s+content=")(.*?)(")',
               lambda m: m.group(1) + html.escape(p["description"], quote=True) + m.group(3),
               h, count=1, flags=re.S)
    # schema.org JSON-LD: drop ALL existing ld+json blocks, inject fresh ones in <head>
    h = re.sub(r'<script type="application/ld\+json">.*?</script>', "", h, flags=re.S)
    h = h.replace("</head>", _schema_blocks(p) + "\n</head>", 1)
    # <h1>
    h = re.sub(r"<h1[^>]*>.*?</h1>", f"<h1>{html.escape(p['title'])}</h1>",
               h, count=1, flags=re.S)
    # the article body
    new_body = (f'<p class="meta">By {p["author"]} · {dateline}</p>\n{p["body_html"]}')
    if re.search(r'<div class="article-body">.*?</div>', h, flags=re.S):
        h = re.sub(r'(<div class="article-body">).*?(</div>)',
                   lambda m: m.group(1) + new_body + m.group(2), h, count=1, flags=re.S)
    else:
        h = re.sub(r"(<article[^>]*>).*?(</article>)",
                   lambda m: m.group(1) + new_body + m.group(2), h, count=1, flags=re.S)
    return h


# --------------------------------------------------------------------------- #
# Mode 2 — standalone (self-contained on-brand page; works with no skeleton)
# --------------------------------------------------------------------------- #
_STANDALONE = """<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} | {author} | BVTech LLC</title>
<meta name="description" content="{desc_attr}">
<meta name="author" content="{author}">
<link rel="canonical" href="{url}">
<meta name="theme-color" content="#0E0D2C">
<meta property="og:type" content="article">
<meta property="og:title" content="{title_attr}">
<meta property="og:description" content="{desc_attr}">
<meta property="og:url" content="{url}">
<meta property="og:site_name" content="BVTech LLC">
<meta property="og:image" content="{og_image}">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Lato:wght@300;400;700;900&family=Poppins:wght@400;500;600;700;800&display=swap" rel="stylesheet">
{schema}
<style>
:root{{--bg:#0E0D2C;--bg2:#13123A;--bg3:#1A1950;--accent:#4440DB;--accent2:#5B57E8;
--green:#26C485;--gold:#F5BE58;--text:rgba(255,255,255,.88);--muted:rgba(255,255,255,.65);
--border:rgba(255,255,255,.07);--fh:'Poppins',sans-serif;--fb:'Lato',sans-serif}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:var(--fb);color:var(--text);
background:radial-gradient(1100px 560px at 80% -10%,#2a2596 0%,var(--bg) 55%);min-height:100vh}}
a{{color:var(--accent2)}}
.site-head{{display:flex;align-items:center;justify-content:space-between;max-width:1160px;
margin:0 auto;padding:20px 24px;border-bottom:1px solid var(--border)}}
.site-head .logo{{font-family:var(--fh);font-weight:800;font-size:18px;color:#fff;letter-spacing:.3px}}
.site-head .logo span{{color:var(--accent2)}}
.site-head a.cta{{font-family:var(--fh);font-weight:700;font-size:13px;background:var(--accent);
color:#fff;padding:9px 16px;border-radius:10px;text-decoration:none}}
.article-body{{max-width:760px;margin:0 auto;padding:60px 24px 100px;font-family:var(--fb)}}
.article-body h1{{font-family:var(--fh);font-weight:800;font-size:clamp(1.8rem,3.5vw,2.4rem);
line-height:1.2;margin-bottom:16px;color:#fff}}
.article-body .meta{{color:var(--accent2);font-size:.85rem;margin-bottom:32px;font-weight:700}}
.article-body p{{margin-bottom:20px;line-height:1.9;color:var(--text)}}
.article-body h2{{font-family:var(--fh);font-weight:700;font-size:1.45rem;margin:42px 0 16px;color:#fff}}
.article-body h3{{font-family:var(--fh);font-weight:600;font-size:1.15rem;margin:32px 0 12px;color:#fff}}
.article-body ul{{margin:0 0 20px;padding-left:22px;line-height:1.9}}
.article-body blockquote{{border-left:3px solid var(--accent);margin:24px 0;padding:6px 18px;
color:var(--muted);background:rgba(68,64,219,.07);border-radius:0 8px 8px 0}}
.article-body a{{color:var(--accent2);text-decoration:underline}}
.article-body code{{background:rgba(255,255,255,.08);padding:2px 6px;border-radius:5px;font-size:.92em}}
.tag{{display:inline-block;font-family:var(--fh);font-size:11px;font-weight:700;letter-spacing:.5px;
text-transform:uppercase;color:var(--gold);border:1px solid rgba(245,190,88,.4);
padding:4px 10px;border-radius:999px;margin-bottom:18px}}
.site-foot{{max-width:760px;margin:0 auto;padding:24px;border-top:1px solid var(--border);
color:var(--muted);font-size:13px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px}}
</style>
</head>
<body>
<header class="site-head">
<a href="/" class="logo"><span>BV</span>Tech LLC</a>
<a href="/book/" class="cta">Book a Call</a>
</header>
<main class="article-body">
<a href="/blog/" style="color:var(--muted);font-size:13px;text-decoration:none">← All Articles</a>
<div style="margin-top:18px"><span class="tag">{tag}</span></div>
<h1>{title}</h1>
<p class="meta">By {author} · {dateline}</p>
{body_html}
</main>
<footer class="site-foot">
<span>© {year} BVTech LLC · El Campo, TX</span>
<span><a href="/">bvtech.org</a></span>
</footer>
</body>
</html>
"""


def render_standalone(post: dict) -> str:
    p = normalize_post(post)
    dateline = _date.fromisoformat(p["date"]).strftime("%B %-d, %Y")
    tag = "Security Advisory" if p["kind"] == "advisory" else "Insights"
    return _STANDALONE.format(
        title=html.escape(p["title"]),
        title_attr=html.escape(p["title"], quote=True),
        desc_attr=html.escape(p["description"], quote=True),
        author=html.escape(p["author"]),
        url=p["url"], og_image=OG_IMAGE, schema=_schema_blocks(p),
        dateline=dateline, tag=tag, body_html=p["body_html"],
        year=_date.fromisoformat(p["date"]).year,
    )


def render(post: dict, skeleton_html: str | None = None) -> str:
    """Render a post — pixel-perfect clone if a skeleton is supplied, else the
    self-contained on-brand page."""
    return render_from_skeleton(skeleton_html, post) if skeleton_html else render_standalone(post)
