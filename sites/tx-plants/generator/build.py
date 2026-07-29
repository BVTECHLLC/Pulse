#!/usr/bin/env python3
"""Texas Roots Almanac generator — builds article pages, index, category pages, FAQ.
Run from site root: python3 generator/build.py"""
import os, html, json, sys
sys.path.insert(0, os.path.dirname(__file__))
from content import CATEGORIES, ARTICLES, FAQS
try:
    from new_articles import NEW_ARTICLES
    ARTICLES = list(ARTICLES) + list(NEW_ARTICLES)
except ImportError:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALM = os.path.join(ROOT, "almanac")
os.makedirs(ALM, exist_ok=True)

SITE = "https://tx-plants.com"
def esc(s): return html.escape(s, quote=True)

# ---------- shared chrome ----------
def head(title, desc, canonical, schema_blocks=None, extra_css=""):
    schema = ""
    for s in (schema_blocks or []):
        schema += f'<script type="application/ld+json">{json.dumps(s)}</script>\n'
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="author" content="Jordan Polasek">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="article"><meta property="og:url" content="{canonical}">
<link rel="icon" href="../favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="../assets/favicon/favicon-32.png">
<link rel="icon" type="image/png" sizes="16x16" href="../assets/favicon/favicon-16.png">
<link rel="apple-touch-icon" href="../assets/favicon/apple-touch-icon.png">
<link rel="manifest" href="../site.webmanifest">
<meta name="theme-color" content="#1B2B22">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;0,9..144,900;1,9..144,400;1,9..144,500&family=Spline+Sans:wght@400;500;600;700&family=Spline+Sans+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="../assets/styles.css">
<style>{extra_css}</style>
{schema}</head>
<body>'''

def nav(active=""):
    def cls(x): return ' class="active"' if x==active else ''
    return f'''<header class="nav"><div class="wrap nav-inner">
  <a href="../index.html" class="brand"><svg viewBox="0 0 40 40" fill="none"><path d="M20 36V16" stroke="#5C8A3A" stroke-width="2.4" stroke-linecap="round"/><path d="M20 22C20 14 12 10 6 11c-1 7 5 14 14 11Z" fill="#5C8A3A" fill-opacity="0.85"/><path d="M20 18C20 11 27 7 33 9c1 6-4 12-13 9Z" fill="#1B2B22"/><circle cx="20" cy="36" r="2.4" fill="#C99A3B"/></svg><span class="name">Texas <b>Roots</b></span></a>
  <nav class="nav-links" id="navLinks"><a href="../start-here.html">Start Here</a><a href="../database/index.html">Plant Database</a><a href="index.html"{cls("almanac")}>Almanac</a><a href="../blog/index.html">Blog</a><a href="../weather.html">Weather</a><a href="../shop.html">Shop</a><a href="../community/index.html">Community</a><a href="../nomad.html">Go Offline</a><a href="../order.html" class="nav-cta">Order Now</a></nav>
  <button class="burger" id="burger" aria-label="Menu"><span></span><span></span><span></span></button>
</div></header>'''

def footer():
    return '''<footer><div class="wrap">
  <div class="foot-grid">
    <div class="foot-brand"><a href="../index.html" class="brand"><svg viewBox="0 0 40 40" fill="none"><path d="M20 36V16" stroke="#7CB342" stroke-width="2.4" stroke-linecap="round"/><path d="M20 22C20 14 12 10 6 11c-1 7 5 14 14 11Z" fill="#7CB342" fill-opacity="0.85"/><path d="M20 18C20 11 27 7 33 9c1 6-4 12-13 9Z" fill="#EAE2CF"/><circle cx="20" cy="36" r="2.4" fill="#C99A3B"/></svg><span class="name" style="color:#F3EEE2">Texas <b style="color:#7CB342">Roots</b></span></a><p>Heirloom seeds &amp; rooted cuttings, grown and mailed by hand from El Campo, Texas. A free knowledge base for growers everywhere. Founded &amp; built by Jordan Polasek.</p></div>
    <div class="foot-col"><h4>Explore</h4><a href="../database/index.html">Plant database</a><a href="index.html">All articles</a><a href="../weather.html">Garden weather</a><a href="../database/identify.html">Identify a plant</a></div>
    <div class="foot-col"><h4>Texas Roots</h4><a href="../shop.html">Shop</a><a href="../community/index.html">Community garden</a><a href="../stand.html">The stand</a><a href="../about.html">Our story</a></div>
    <div class="foot-col"><h4>More</h4><a href="../faq.html">FAQ</a><a href="../order.html">Place an order</a><a href="../nomad.html">Go offline</a><a href="../vault.html">Knowledge Vault</a><a href="https://jordanpolasek.com">JordanPolasek.com</a><a href="https://bvtech.org">BVTech.org</a><a href="https://autumnpolasek.com">In Remembrance of Autumn 🐾</a></div>
  </div>
  <div class="foot-scripture" style="text-align:center;color:rgba(243,238,226,.55);font-style:italic;padding:0 0 18px;font-size:.9rem">&ldquo;So neither he who plants nor he who waters is anything, but only God, who gives the growth.&rdquo; &mdash; 1 Corinthians 3:7</div><div class="foot-bottom"><span>© <span id="yr"></span> Texas Roots · El Campo, TX · tx-plants.com</span><span>Written &amp; built by <a href="https://jordanpolasek.com">Jordan Polasek</a></span></div>
</div></footer>
<script>document.getElementById('yr').textContent=new Date().getFullYear();const burger=document.getElementById('burger'),navLinks=document.getElementById('navLinks');burger.addEventListener('click',()=>navLinks.classList.toggle('open'));navLinks.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>navLinks.classList.remove('open')));const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}}),{threshold:.12});document.querySelectorAll('.reveal').forEach(el=>io.observe(el));</script>
</body></html>'''

# ---------- render article body blocks ----------
def render_blocks(blocks):
    out = []
    for b in blocks:
        t = b[0]
        if t == "p": out.append(f"<p>{esc(b[1])}</p>")
        elif t == "h": out.append(f"<h2>{esc(b[1])}</h2>")
        elif t == "quote": out.append(f'<blockquote>{esc(b[1])}</blockquote>')
        elif t == "tip": out.append(f'<div class="tip"><span class="tip-label">Jordan&rsquo;s tip</span>{esc(b[1])}</div>')
        elif t == "ul": out.append("<ul>"+"".join(f"<li>{esc(i)}</li>" for i in b[1])+"</ul>")
        elif t == "ol": out.append("<ol>"+"".join(f"<li>{esc(i)}</li>" for i in b[1])+"</ol>")
        elif t == "steps":
            items = "".join(f'<div class="step-item"><div class="step-n">{n+1}</div><div><h4>{esc(title)}</h4><p>{esc(desc)}</p></div></div>' for n,(title,desc) in enumerate(b[1]))
            out.append(f'<div class="steps-flow">{items}</div>')
        elif t == "table":
            hdr = "".join(f"<th>{esc(h)}</th>" for h in b[1])
            rows = "".join("<tr>"+"".join(f"<td>{esc(c)}</td>" for c in r)+"</tr>" for r in b[2])
            out.append(f'<div class="table-wrap"><table><thead><tr>{hdr}</tr></thead><tbody>{rows}</tbody></table></div>')
    return "\n".join(out)

# ---------- HowTo schema if article has steps ----------
def howto_schema(art):
    steps = []
    for b in art["body"]:
        if b[0] == "steps":
            for title, desc in b[1]:
                steps.append({"@type":"HowToStep","name":title,"text":desc})
    if not steps: return None
    return {"@context":"https://schema.org","@type":"HowTo","name":art["title"],
            "description":art["summary"],"step":steps,
            "author":{"@type":"Person","name":"Jordan Polasek","url":"https://jordanpolasek.com"}}

ARTICLE_CSS = """
.crumbs{font-family:'Spline Sans Mono',monospace;font-size:.78rem;color:var(--ink-faint);padding:24px 0 0}
.crumbs a{color:var(--sprout);text-decoration:none}
.art-hero{padding:30px 0 50px;border-bottom:1px solid var(--line)}
.art-hero .cat-pill{display:inline-block;font-family:'Spline Sans Mono',monospace;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;padding:5px 12px;border-radius:30px;color:#fff;margin-bottom:18px}
.art-hero h1{font-size:clamp(2.2rem,4.5vw,3.4rem);max-width:20ch;margin-bottom:18px;line-height:1.08}
.art-hero .summary{font-size:1.2rem;color:var(--ink-soft);max-width:60ch;line-height:1.6;margin-bottom:22px}
.art-meta{display:flex;align-items:center;gap:16px;font-size:.9rem;color:var(--ink-faint)}
.art-meta .by{display:flex;align-items:center;gap:9px}
.art-meta .av{width:34px;height:34px;border-radius:50%;background:var(--sprout);color:#fff;display:flex;align-items:center;justify-content:center;font-family:'Fraunces',serif;font-weight:600}
.art-layout{display:grid;grid-template-columns:1fr 280px;gap:54px;padding:50px 0 70px;align-items:start}
.art-body{max-width:none;font-size:1.08rem;line-height:1.75}
.art-body h2{font-size:1.7rem;margin:38px 0 14px;color:var(--ink)}
.art-body p{margin-bottom:18px;color:var(--ink-soft)}
.art-body ul,.art-body ol{margin:0 0 20px 22px;color:var(--ink-soft)}
.art-body li{margin-bottom:9px;padding-left:4px}
.art-body blockquote{border-left:3px solid var(--sprout);background:var(--paper-warm);padding:18px 24px;margin:26px 0;font-family:'Fraunces',serif;font-size:1.3rem;font-style:italic;color:var(--ink);border-radius:0 4px 4px 0}
.tip{background:rgba(201,154,59,.13);border:1px solid rgba(201,154,59,.4);border-radius:4px;padding:18px 22px;margin:26px 0;color:var(--ink-soft);font-size:1rem}
.tip-label{display:block;font-family:'Spline Sans Mono',monospace;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;color:var(--gold);margin-bottom:6px;font-weight:600}
.steps-flow{margin:26px 0;display:flex;flex-direction:column;gap:2px}
.step-item{display:flex;gap:18px;padding:18px;background:var(--paper-warm);border:1px solid var(--line);border-bottom:0}
.step-item:last-child{border-bottom:1px solid var(--line)}
.step-n{font-family:'Fraunces',serif;font-weight:900;font-size:1.5rem;color:var(--sprout);min-width:32px;line-height:1.2}
.step-item h4{font-size:1.1rem;margin-bottom:4px}
.step-item p{margin:0;font-size:.97rem}
.table-wrap{overflow-x:auto;margin:26px 0}
.art-body table{width:100%;border-collapse:collapse;font-size:.96rem}
.art-body th{background:var(--ink);color:var(--paper);text-align:left;padding:12px 14px;font-family:'Spline Sans',sans-serif;font-weight:600;font-size:.9rem}
.art-body td{padding:11px 14px;border-bottom:1px solid var(--line);color:var(--ink-soft);vertical-align:top}
.art-body tr:nth-child(even) td{background:var(--paper-warm)}
.art-side{position:sticky;top:90px}
.art-side .card{background:var(--paper-warm);border:1px solid var(--line);border-radius:4px;padding:22px;margin-bottom:18px}
.art-side h4{font-family:'Spline Sans Mono',monospace;font-size:.72rem;letter-spacing:.07em;text-transform:uppercase;color:var(--clay);margin-bottom:12px}
.art-side a{display:block;color:var(--ink-soft);text-decoration:none;font-size:.92rem;padding:7px 0;border-bottom:1px solid var(--line);transition:color .2s}
.art-side a:last-child{border-bottom:0}.art-side a:hover{color:var(--sprout)}
.art-illus{width:100%;border:1px solid var(--line);border-radius:4px;margin-bottom:8px}
.art-cta{background:var(--ink);color:var(--paper);border-radius:4px;padding:24px}
.art-cta h4{color:var(--gold)}.art-cta p{font-size:.92rem;color:rgba(243,238,226,.8);margin-bottom:14px}
.art-cta a{color:var(--sprout-bright);font-weight:600;text-decoration:none;border:0;padding:0}
.related{background:var(--paper-warm);padding:60px 0;border-top:1px solid var(--line)}
.related h3{font-size:1.5rem;margin-bottom:24px}
.rel-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}
.rel-card{background:var(--paper-card);border:1px solid var(--line);border-radius:4px;padding:22px;text-decoration:none;color:inherit;transition:transform .2s,box-shadow .2s}
.rel-card:hover{transform:translateY(-4px);box-shadow:5px 7px 0 var(--shadow)}
.rel-card .rc-cat{font-family:'Spline Sans Mono',monospace;font-size:.68rem;letter-spacing:.06em;text-transform:uppercase;margin-bottom:8px}
.rel-card h4{font-size:1.12rem;line-height:1.25;margin-bottom:6px}
.rel-card p{font-size:.88rem;color:var(--ink-faint);line-height:1.5}
@media(max-width:900px){.art-layout{grid-template-columns:1fr;gap:30px}.art-side{position:static}.rel-grid{grid-template-columns:1fr}}
"""

def build_article(art):
    cat = CATEGORIES[art["category"]]
    url = f"{SITE}/almanac/{art['slug']}.html"
    # schema: Article + optional HowTo + Breadcrumb
    article_schema = {"@context":"https://schema.org","@type":"Article",
        "headline":art["title"],"description":art["summary"],
        "author":{"@type":"Person","name":"Jordan Polasek","url":"https://jordanpolasek.com"},
        "publisher":{"@type":"Organization","name":"Texas Roots","url":SITE},
        "mainEntityOfPage":url,"articleSection":cat["name"],"inLanguage":"en-US"}
    crumb = {"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
        {"@type":"ListItem","position":1,"name":"Almanac","item":f"{SITE}/almanac/"},
        {"@type":"ListItem","position":2,"name":cat["name"],"item":f"{SITE}/almanac/#{art['category']}"},
        {"@type":"ListItem","position":3,"name":art["title"],"item":url}]}
    schemas = [article_schema, crumb]
    ht = howto_schema(art)
    if ht: schemas.append(ht)

    # related: same category, then others
    related = [a for a in ARTICLES if a["category"]==art["category"] and a["slug"]!=art["slug"]][:3]
    if len(related) < 3:
        related += [a for a in ARTICLES if a["category"]!=art["category"]][:3-len(related)]
    rel_html = "".join(
        f'''<a href="{r['slug']}.html" class="rel-card"><div class="rc-cat" style="color:{CATEGORIES[r['category']]['color']}">{esc(CATEGORIES[r['category']]['name'])}</div><h4>{esc(r['title'])}</h4><p>{esc(r['summary'][:90])}…</p></a>'''
        for r in related)

    # side nav: other articles in category
    same = [a for a in ARTICLES if a["category"]==art["category"]]
    side_links = "".join(f'<a href="{a["slug"]}.html"{" style=font-weight:600;color:var(--sprout)" if a["slug"]==art["slug"] else ""}>{esc(a["title"])}</a>' for a in same)

    body = render_blocks(art["body"])
    page = head(f"{art['title']} | Texas Roots Almanac", art["summary"], url, schemas, ARTICLE_CSS)
    page += nav("almanac")
    page += f'''<div class="wrap"><div class="crumbs"><a href="index.html">Almanac</a> / <a href="index.html#{art['category']}">{esc(cat['name'])}</a> / {esc(art['title'])}</div></div>
<div class="art-hero"><div class="wrap">
<span class="cat-pill" style="background:{cat['color']}">{esc(cat['name'])}</span>
<h1>{esc(art['title'])}</h1>
<p class="summary">{esc(art['summary'])}</p>
<div class="art-meta"><span class="by"><span class="av">J</span> By Jordan Polasek</span> · <span>{art['read_min']} min read</span> · <span>El Campo, TX</span></div>
</div></div>
<div class="wrap"><div class="art-layout">
<article class="art-body">
<img class="art-illus" src="../assets/img/kb/{art['icon']}" alt="{esc(art['title'])} illustration">
{body}
<hr style="border:0;border-top:1px solid var(--line);margin:40px 0 24px">
<p style="font-size:.95rem;color:var(--ink-faint)">Written by <a href="https://jordanpolasek.com" style="color:var(--sprout)">Jordan Polasek</a>, founder of Texas Roots, from his greenhouse in El Campo, Texas. Free to share. If this helped, the best thanks is to <a href="../shop.html" style="color:var(--sprout)">grow something</a> or pass it along.</p>
</article>
<aside class="art-side">
<div class="card"><h4>More in {esc(cat['name'])}</h4>{side_links}</div>
<div class="card art-cta"><h4>Start growing</h4><p>Heirloom seeds &amp; rooted cuttings from this greenhouse, mailed to your door.</p><a href="../shop.html">Browse the catalog →</a></div>
</aside>
</div></div>
<section class="related"><div class="wrap"><h3>Keep reading</h3><div class="rel-grid">{rel_html}</div></div></section>
'''
    page += footer()
    open(os.path.join(ALM, f"{art['slug']}.html"), "w").write(page)

# ---------- almanac index ----------
INDEX_CSS = """
.alm-hero{background:var(--ink);color:var(--paper);padding:80px 0 70px;position:relative;overflow:hidden}
.alm-hero::after{content:"";position:absolute;inset:0;background:url(../assets/img/tunnel-golden.jpg) center/cover;opacity:.14}
.alm-hero .wrap{position:relative;z-index:2;max-width:70ch}
.alm-hero .eyebrow{color:var(--gold)}
.alm-hero h1{font-size:clamp(2.6rem,5.5vw,4rem);margin-bottom:18px}
.alm-hero h1 em{font-style:italic;color:var(--sprout-bright);font-weight:500}
.alm-hero p{color:rgba(243,238,226,.85);font-size:1.16rem;max-width:60ch}
.alm-search{margin-top:28px;display:flex;gap:10px;max-width:480px}
.alm-search input{flex:1;padding:13px 16px;border:1.5px solid rgba(243,238,226,.3);border-radius:3px;background:rgba(243,238,226,.1);color:var(--paper);font-family:inherit;font-size:1rem}
.alm-search input::placeholder{color:rgba(243,238,226,.5)}
.cat-nav{position:sticky;top:68px;z-index:50;background:rgba(243,238,226,.95);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:14px 0}
.cat-nav-inner{display:flex;gap:10px;flex-wrap:wrap}
.cat-nav a{font-size:.85rem;font-weight:600;text-decoration:none;color:var(--ink-soft);padding:7px 14px;border:1px solid var(--line);border-radius:30px;transition:all .2s}
.cat-nav a:hover{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.cat-section{padding:60px 0 20px}
.cat-head{display:flex;align-items:baseline;gap:16px;margin-bottom:8px}
.cat-head h2{font-size:1.9rem}
.cat-head .dot{width:14px;height:14px;border-radius:50%;flex:none}
.cat-desc{color:var(--ink-soft);margin-bottom:28px;font-size:1.05rem}
.art-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:22px;margin-bottom:20px}
.art-card{background:var(--paper-card);border:1px solid var(--line);border-radius:4px;overflow:hidden;text-decoration:none;color:inherit;display:flex;flex-direction:column;transition:transform .22s,box-shadow .22s}
.art-card:hover{transform:translateY(-5px);box-shadow:6px 9px 0 var(--shadow)}
.art-card .ac-img{aspect-ratio:2/1;overflow:hidden;background:var(--paper-warm);border-bottom:1px solid var(--line)}
.art-card .ac-img img{width:100%;height:100%;object-fit:cover}
.art-card .ac-body{padding:20px 22px 22px;flex:1;display:flex;flex-direction:column}
.art-card .ac-read{font-family:'Spline Sans Mono',monospace;font-size:.68rem;letter-spacing:.05em;color:var(--clay);text-transform:uppercase;margin-bottom:9px}
.art-card h3{font-size:1.2rem;line-height:1.22;margin-bottom:8px}
.art-card p{font-size:.9rem;color:var(--ink-faint);line-height:1.5;flex:1}
.art-card .ac-more{margin-top:14px;font-size:.85rem;font-weight:600;color:var(--sprout)}
.no-results{text-align:center;padding:40px;color:var(--ink-faint);display:none}
@media(max-width:900px){.art-grid{grid-template-columns:1fr}.cat-nav{display:none}}
"""

def build_index():
    url = f"{SITE}/almanac/"
    # CollectionPage + ItemList schema
    item_list = {"@context":"https://schema.org","@type":"ItemList","name":"Texas Roots Almanac",
        "description":"A free knowledge base on growing, homesteading, survival gardening, and self-sufficiency.",
        "itemListElement":[{"@type":"ListItem","position":i+1,"url":f"{SITE}/almanac/{a['slug']}.html","name":a["title"]} for i,a in enumerate(ARTICLES)]}
    page = head("The Texas Roots Almanac — Free Growing & Homesteading Knowledge Base",
                "A free, growing encyclopedia of how to grow food, homestead, survive, capture water, raise animals, repair equipment, and live more self-sufficiently. Written by Jordan Polasek in El Campo, TX.",
                url, [item_list], INDEX_CSS)
    page += nav("almanac")
    page += f'''<section class="alm-hero"><div class="wrap">
<div class="eyebrow">A free knowledge base · written by Jordan Polasek</div>
<h1>The Texas Roots <em>Almanac</em></h1>
<p>Everything I know about growing food, working the land, and living more self-sufficiently — written down, free for anyone, forever. No paywall, no email gate. The resource I wish I'd had when I started.</p>
<div class="alm-search"><input type="search" id="almSearch" placeholder="Search the almanac… (soil, water, chickens, land)" aria-label="Search articles"></div>
</div></section>
<div class="cat-nav"><div class="wrap cat-nav-inner">
{"".join(f'<a href="#{k}">{esc(v["name"])}</a>' for k,v in CATEGORIES.items())}
</div></div>
<div class="no-results" id="noResults">No articles match that search. Try another word.</div>
'''
    for k, v in CATEGORIES.items():
        arts = [a for a in ARTICLES if a["category"]==k]
        if not arts: continue
        cards = ""
        for a in arts:
            cards += f'''<a href="{a['slug']}.html" class="art-card" data-search="{esc((a['title']+' '+a['summary']).lower())}">
<div class="ac-img"><img src="../assets/img/kb/{a['icon']}" alt="{esc(a['title'])}" loading="lazy"></div>
<div class="ac-body"><div class="ac-read">{a['read_min']} min · {esc(v['name'])}</div><h3>{esc(a['title'])}</h3><p>{esc(a['summary'][:110])}…</p><div class="ac-more">Read →</div></div></a>'''
        page += f'''<section class="cat-section" id="{k}"><div class="wrap">
<div class="cat-head"><span class="dot" style="background:{v['color']}"></span><h2>{esc(v['name'])}</h2></div>
<p class="cat-desc">{esc(v['desc'])}</p>
<div class="art-grid">{cards}</div>
</div></section>'''
    page += '''<script>
const search=document.getElementById('almSearch'),cards=document.querySelectorAll('.art-card'),noRes=document.getElementById('noResults');
search&&search.addEventListener('input',()=>{const q=search.value.toLowerCase().trim();let any=false;
cards.forEach(c=>{const m=!q||c.dataset.search.includes(q);c.style.display=m?'':'none';if(m)any=true;});
document.querySelectorAll('.cat-section').forEach(s=>{const vis=[...s.querySelectorAll('.art-card')].some(c=>c.style.display!=='none');s.style.display=vis?'':'none';});
noRes.style.display=any?'none':'block';});
</script>'''
    page += footer()
    open(os.path.join(ALM, "index.html"), "w").write(page)

# ---------- FAQ ----------
def build_faq():
    url = f"{SITE}/faq.html"
    faq_schema = {"@context":"https://schema.org","@type":"FAQPage","mainEntity":[
        {"@type":"Question","name":q,"acceptedAnswer":{"@type":"Answer","text":a}} for q,a in FAQS]}
    css = """
.faq-hero{background:var(--ink);color:var(--paper);padding:70px 0 60px;text-align:center}
.faq-hero .eyebrow{color:var(--gold);justify-content:center}
.faq-hero h1{font-size:clamp(2.2rem,4.5vw,3.4rem);margin-bottom:14px}
.faq-hero p{color:rgba(243,238,226,.82);font-size:1.1rem;max-width:50ch;margin:0 auto}
.faq-list{max-width:760px;margin:0 auto;padding:60px 0}
.faq-item{border-bottom:1px solid var(--line)}
.faq-q{width:100%;text-align:left;background:none;border:0;padding:24px 0;font-family:'Fraunces',serif;font-size:1.3rem;font-weight:600;color:var(--ink);cursor:pointer;display:flex;justify-content:space-between;gap:20px;align-items:center}
.faq-q .ic{color:var(--sprout);font-size:1.5rem;flex:none;transition:transform .25s}
.faq-item.open .faq-q .ic{transform:rotate(45deg)}
.faq-a{max-height:0;overflow:hidden;transition:max-height .3s ease}
.faq-a p{padding:0 0 24px;color:var(--ink-soft);font-size:1.05rem;line-height:1.7}
"""
    page = head("FAQ — Texas Roots", "Common questions about Texas Roots: seeds, cuttings, shipping, soil, the honor stand, and the free knowledge base. Answered by Jordan Polasek.", url, [faq_schema], css)
    # FAQ uses root-relative nav (it's at site root, not in /almanac)
    page = page.replace('href="../', 'href="')
    page += '''<header class="nav"><div class="wrap nav-inner">
  <a href="index.html" class="brand"><svg viewBox="0 0 40 40" fill="none"><path d="M20 36V16" stroke="#5C8A3A" stroke-width="2.4" stroke-linecap="round"/><path d="M20 22C20 14 12 10 6 11c-1 7 5 14 14 11Z" fill="#5C8A3A" fill-opacity="0.85"/><path d="M20 18C20 11 27 7 33 9c1 6-4 12-13 9Z" fill="#1B2B22"/><circle cx="20" cy="36" r="2.4" fill="#C99A3B"/></svg><span class="name">Texas <b>Roots</b></span></a>
  <nav class="nav-links" id="navLinks"><a href="start-here.html">Start Here</a><a href="database/index.html">Plant Database</a><a href="almanac/index.html">Almanac</a><a href="blog/index.html">Blog</a><a href="weather.html">Weather</a><a href="shop.html">Shop</a><a href="community/index.html">Community</a><a href="nomad.html">Go Offline</a><a href="order.html" class="nav-cta">Order Now</a></nav>
  <button class="burger" id="burger" aria-label="Menu"><span></span><span></span><span></span></button>
</div></header>'''
    page += '''<section class="faq-hero"><div class="wrap"><div class="eyebrow">Questions &amp; answers</div><h1>Frequently asked questions</h1><p>Everything people ask me about the plants, the shipping, the soil, and the stand. Don't see yours? Just ask on the order page.</p></div></section>
<div class="wrap"><div class="faq-list">'''
    for q,a in FAQS:
        page += f'''<div class="faq-item"><button class="faq-q">{esc(q)}<span class="ic">+</span></button><div class="faq-a"><p>{esc(a)}</p></div></div>'''
    page += '''</div></div>
<script>document.querySelectorAll('.faq-q').forEach(b=>b.addEventListener('click',()=>{const it=b.parentElement,a=it.querySelector('.faq-a');it.classList.toggle('open');a.style.maxHeight=it.classList.contains('open')?a.scrollHeight+'px':'0';}));</script>'''
    # footer with root-relative links
    page += footer().replace('href="../','href="')
    open(os.path.join(ROOT, "faq.html"), "w").write(page)

if __name__ == "__main__":
    for art in ARTICLES: build_article(art)
    build_index()
    build_faq()
    print(f"Built {len(ARTICLES)} articles + index + FAQ")
