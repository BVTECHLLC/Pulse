#!/usr/bin/env python3
"""Texas Roots — sitemap generator (v5). Builds sitemap.xml from the real
file tree so new plants, articles, and pages are always included."""
import os, glob, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://tx-plants.com"
TODAY = datetime.date.today().isoformat()

def priority(path):
    if path == "index.html": return "1.0"
    if path in ("shop.html","database/index.html","weather.html","almanac/index.html","nomad.html","start-here.html"): return "0.9"
    if path in ("database/identify.html",): return "0.8"
    if path.startswith("almanac/") and path != "almanac/index.html": return "0.8"
    if path.startswith("blog/"): return "0.8"
    if path.startswith("database/"): return "0.7"
    return "0.7"

def loc(path):
    if path == "index.html":
        return f"{SITE}/"
    if path.endswith("/index.html"):
        return f"{SITE}/{path[:-len('index.html')]}"
    return f"{SITE}/{path}"

# collect pages
pages = []
for p in sorted(glob.glob(os.path.join(ROOT, "*.html"))):
    pages.append(os.path.basename(p))
for sub in ("database", "almanac", "community", "blog"):
    for p in sorted(glob.glob(os.path.join(ROOT, sub, "*.html"))):
        pages.append(f"{sub}/{os.path.basename(p)}")

# order: top-level priority pages first, then the rest
TOP = ["index.html","start-here.html","shop.html","database/index.html","weather.html","almanac/index.html",
       "nomad.html","database/identify.html","about.html","grow.html","stand.html",
       "order.html","faq.html","community/index.html"]
ordered = [p for p in TOP if p in pages] + [p for p in pages if p not in TOP]

lines = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
seen = set()
for p in ordered:
    if p in seen: continue
    seen.add(p)
    lines.append(f'  <url><loc>{loc(p)}</loc><lastmod>{TODAY}</lastmod><priority>{priority(p)}</priority></url>')
lines.append('</urlset>')

open(os.path.join(ROOT, "sitemap.xml"), "w").write("\n".join(lines) + "\n")
print(f"Wrote sitemap.xml with {len(seen)} URLs")
