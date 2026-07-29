#!/usr/bin/env python3
"""Texas Roots — The Offline Knowledge Vault (/vault.html).

A companion to Project NOMAD: the actual, curated directory of the best FREE
knowledge to keep — the world's biggest offline databases (Kiwix/ZIM), free
audiobooks, and free learning/reference libraries — plus how to build your own
offline knowledge server on hardware you own. Same honest voice as the rest of
the site. Every link is a real, free, reputable source.

Reuses the shared nav/footer/head scaffolding from build_nomad so branding stays
identical.
"""
import os, sys, html, json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from build_nomad import nav, footer, FONTS, FAVICON, SITE  # shared scaffolding

def esc(s): return html.escape(str(s), quote=True)


# --------------------------------------------------------------------------- #
# Curated resource data. (title, blurb, [(label, url), ...])
# Everything here is free and real. Descriptions are honest, not hype.
# --------------------------------------------------------------------------- #
OFFLINE_DBS = [
    ("Kiwix — the reader that runs it all",
     "The free, open-source app that opens giant '.zim' knowledge files offline on phone, computer, or a Raspberry Pi. Start here: Kiwix is the shelf; the .zim files below are the books.",
     [("kiwix.org", "https://kiwix.org"), ("Browse the ZIM library", "https://library.kiwix.org")]),
    ("All of Wikipedia (offline)",
     "The entire English Wikipedia — millions of articles, with or without images — in one file you can read with the power off. ~90 GB with images, far less without. The single most valuable thing to keep.",
     [("Wikipedia ZIM (via Kiwix)", "https://library.kiwix.org/#lang=eng&category=wikipedia")]),
    ("Project Gutenberg — 70,000+ free books",
     "Every out-of-copyright classic ever digitized — literature, science, history, how-to. A whole public library in a couple of gigabytes.",
     [("gutenberg.org", "https://www.gutenberg.org"), ("Gutenberg ZIM", "https://library.kiwix.org/#category=gutenberg")]),
    ("The Survivor Library",
     "Scans of pre-1950s manuals on how the world worked before the grid: blacksmithing, medicine, farming, machining, chemistry — the knowledge to rebuild from scratch.",
     [("survivorlibrary.com", "https://www.survivorlibrary.com")]),
    ("Where There Is No Doctor / Dentist (Hesperian)",
     "The world's most-used village health guides — diagnosis and treatment when no clinic is reachable. Free PDFs, translated into dozens of languages. Keep these.",
     [("Hesperian Health Guides", "https://hesperian.org/books-and-resources/")]),
    ("Medicine & health (WHO + more)",
     "WHO clinical guidance, the Wikipedia Medicine collection, and first-aid references — a real medical shelf for when the internet (and maybe the doctor) is gone.",
     [("WikiMed Medical Encyclopedia", "https://library.kiwix.org/#category=wikipedia&lang=eng"), ("WHO publications", "https://www.who.int/publications")]),
    ("iFixit — repair everything",
     "Step-by-step teardown and repair guides for phones, appliances, cars, and machines. Fixing beats replacing when nothing ships to you anymore.",
     [("ifixit.com", "https://www.ifixit.com/Guide"), ("iFixit ZIM", "https://library.kiwix.org/#category=ifixit")]),
    ("Stack Overflow & Stack Exchange (offline)",
     "Millions of real questions-and-answers on programming, electronics, gardening, cooking, survival, and more — the collective troubleshooting of the internet, downloadable.",
     [("Stack Exchange ZIMs", "https://library.kiwix.org/#category=stack_exchange")]),
    ("Khan Academy (offline)",
     "Full courses — math from counting to calculus, science, history — video and practice, offline. A school in a box for kids or yourself.",
     [("khanacademy.org", "https://www.khanacademy.org"), ("Khan ZIM", "https://library.kiwix.org/#category=other&q=khan")]),
    ("WikiHow + Wikibooks + Wikivoyage",
     "How to do almost anything (wikiHow), free open textbooks (Wikibooks), and offline travel/terrain guides for every region (Wikivoyage).",
     [("wikiHow ZIM", "https://library.kiwix.org/#q=wikihow"), ("Wikibooks", "https://www.wikibooks.org"), ("Wikivoyage", "https://www.wikivoyage.org")]),
    ("Appropriate Technology Library (CD3WD)",
     "Thousands of low-tech, low-cost how-to documents — clean water, food storage, building, energy, small-farm tools — designed for the developing world and off-grid life.",
     [("Search 'CD3WD' / Appropriate Tech", "https://www.google.com/search?q=cd3wd+appropriate+technology+library+download")]),
    ("Offline maps (whole world)",
     "The entire planet's roads, trails, and terrain from OpenStreetMap — free, and it works with no signal. Organic Maps and OsmAnd download regions to your phone.",
     [("Organic Maps", "https://organicmaps.app"), ("OsmAnd", "https://osmand.net"), ("OpenStreetMap", "https://www.openstreetmap.org")]),
]

AUDIOBOOKS = [
    ("LibriVox — free public-domain audiobooks",
     "Thousands of complete audiobooks read by volunteers — every classic, free forever, downloadable as MP3s to keep offline. The heart of free listening.",
     [("librivox.org", "https://librivox.org")]),
    ("Loyal Books",
     "A friendlier front-end to the public-domain audiobook and ebook world — browse by genre, stream or download, no account needed.",
     [("loyalbooks.com", "http://www.loyalbooks.com")]),
    ("Open Culture — the free-media hub",
     "Curated lists of 1,000+ free audiobooks, 1,000+ free online courses, and free movies and textbooks — the internet's best index of legally-free learning media.",
     [("Free Audiobooks list", "https://www.openculture.com/freeaudiobooks"), ("Free Courses", "https://www.openculture.com/freeonlinecourses")]),
    ("Lit2Go (USF)",
     "Free audiobooks and poems with matching text and reading levels — excellent for kids, language learners, and read-alongs.",
     [("etc.usf.edu/lit2go", "https://etc.usf.edu/lit2go/")]),
    ("Internet Archive — audio & radio",
     "Millions of hours: audiobooks, old-time radio, live music, lectures, and speeches. A near-bottomless, free, downloadable audio library.",
     [("archive.org/audio", "https://archive.org/details/audio")]),
    ("Storynory (for kids)",
     "Free audio stories for children — original tales, fairy tales, and classics, read aloud. Great for the little ones with or without a screen.",
     [("storynory.com", "https://www.storynory.com")]),
    ("LearnOutLoud",
     "A big directory of free audiobooks, lectures, and educational audio and video across every subject.",
     [("learnoutloud.com/Free-Audio-Video", "https://www.learnoutloud.com/Free-Audio-Video")]),
    ("Librophile",
     "Search and stream free public-domain and Creative-Commons audiobooks and ebooks in one clean interface.",
     [("librophile.com", "https://www.librophile.com")]),
]

LEARNING = [
    ("Internet Archive & Open Library",
     "The digital library of everything: books to borrow, archived websites, software, film, and audio. Open Library alone lends millions of books free.",
     [("archive.org", "https://archive.org"), ("openlibrary.org", "https://openlibrary.org")]),
    ("OpenStax — free, real textbooks",
     "Peer-reviewed, university-level textbooks (math, science, business, humanities) — free PDFs you can download and keep. Genuinely good, not filler.",
     [("openstax.org", "https://openstax.org")]),
    ("MIT OpenCourseWare",
     "Actual MIT course materials — lecture notes, problem sets, many with video — free and downloadable across nearly every subject MIT teaches.",
     [("ocw.mit.edu", "https://ocw.mit.edu")]),
    ("Standard Ebooks",
     "Beautifully typeset, carefully proofread public-domain books — the classics done right, free, in every format.",
     [("standardebooks.org", "https://standardebooks.org")]),
    ("Wikiversity & Wikibooks",
     "Community-built free courses and open textbooks on everything from languages to engineering — editable, downloadable, offline-friendly.",
     [("wikiversity.org", "https://www.wikiversity.org"), ("wikibooks.org", "https://www.wikibooks.org")]),
    ("DevDocs & MDN (for the makers)",
     "Every programming language and web-platform reference in one fast, installable, offline-capable app — for anyone who builds or fixes technology.",
     [("devdocs.io", "https://devdocs.io"), ("MDN Web Docs", "https://developer.mozilla.org")]),
    ("Public-domain field manuals & guides",
     "U.S. government survival, first-aid, and field manuals are public domain — free to download and keep. Verify against modern guidance, but the fundamentals endure.",
     [("Archive.org military manuals", "https://archive.org/search?query=army+field+manual+survival")]),
    ("Permaculture & seed-saving (ties to the garden)",
     "Free guides on growing, saving seed, and closing the loop — the knowledge behind the Texas Roots survival garden itself.",
     [("Grow a survival garden", "almanac/how-to-grow-a-survival-garden.html"), ("Save & clone your plants", "almanac/how-to-clone-plants.html"), ("Browse survival crops", "database/index.html#survival")]),
]


def card(title, blurb, links):
    ls = " ".join(
        f'<a class="src" href="{esc(u)}" {"" if u.startswith("almanac") or u.startswith("database") else "target=_blank rel=noopener"}>{esc(l)} ↗</a>'
        for l, u in links)
    return f'''<div class="vault-card reveal">
      <h4>{esc(title)}</h4>
      <p>{esc(blurb)}</p>
      <div class="srcs">{ls}</div>
    </div>'''


def grid(items):
    return '<div class="vault-grid">' + "".join(card(*it) for it in items) + '</div>'


VAULT_CSS = """
.vlt-hero{background:linear-gradient(135deg,#0F1813,#1B2B22);color:var(--paper);padding:88px 0 66px;position:relative;overflow:hidden}
.vlt-hero::before{content:"";position:absolute;inset:0;opacity:.06;background-image:radial-gradient(circle at 1px 1px,#7CB342 1px,transparent 0);background-size:26px 26px}
.vlt-hero .wrap{position:relative;z-index:2;max-width:64ch}
.vlt-hero .eyebrow{color:var(--gold)}
.vlt-hero h1{font-size:clamp(2.3rem,5.4vw,3.9rem);line-height:1.04;margin-bottom:18px}
.vlt-hero h1 em{font-style:italic;color:var(--sprout-bright);font-weight:500}
.vlt-hero .lede{color:rgba(243,238,226,.86);font-size:1.2rem;line-height:1.6;margin-bottom:26px}
.vlt-hero .jump{display:flex;gap:10px;flex-wrap:wrap}
.vlt-hero .jump a{color:var(--paper);border:1px solid rgba(243,238,226,.4);border-radius:999px;padding:8px 16px;text-decoration:none;font-size:.92rem;font-weight:600}
.vlt-hero .jump a:hover{background:rgba(243,238,226,.12)}
.vlt-body{padding:64px 0}
.vlt-sec{margin:0 0 58px;scroll-margin-top:84px}
.vlt-sec .kicker{font-family:'Spline Sans Mono',monospace;font-size:.74rem;letter-spacing:.1em;text-transform:uppercase;color:var(--clay)}
.vlt-sec h2{font-size:clamp(1.7rem,3vw,2.4rem);margin:6px 0 8px;line-height:1.1}
.vlt-sec .intro{font-size:1.12rem;color:var(--ink-soft);line-height:1.7;max-width:70ch;margin-bottom:8px}
.vault-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(288px,1fr));gap:16px;margin:26px 0}
.vault-card{background:var(--paper-card);border:1px solid var(--line);border-radius:11px;padding:20px 20px 16px;display:flex;flex-direction:column;transition:transform .18s ease,box-shadow .18s ease,border-color .18s}
.vault-card:hover{transform:translateY(-3px);box-shadow:0 12px 30px rgba(16,33,26,.1);border-color:var(--sprout)}
.vault-card h4{font-size:1.12rem;margin:0 0 8px;line-height:1.25;color:var(--ink)}
.vault-card p{font-size:.96rem;color:var(--ink-soft);line-height:1.6;margin:0 0 14px;flex:1}
.vault-card .srcs{display:flex;flex-wrap:wrap;gap:8px}
.vault-card .src{font-size:.83rem;font-weight:600;color:var(--sprout);text-decoration:none;background:var(--paper-warm);border:1px solid var(--line);border-radius:7px;padding:5px 10px}
.vault-card .src:hover{border-color:var(--sprout);background:#fff}
.vlt-build{background:var(--ink);color:var(--paper);border-radius:14px;padding:40px 36px;margin:12px 0 8px}
.vlt-build h3{color:var(--sprout-bright);font-size:1.5rem;margin:0 0 6px}
.vlt-build p.sub{color:rgba(243,238,226,.8);font-size:1.05rem;line-height:1.6;margin:0 0 26px;max-width:66ch}
.vlt-steps{counter-reset:s;display:grid;gap:2px}
.vlt-steps .st{display:grid;grid-template-columns:46px 1fr;gap:16px;padding:16px 0;border-bottom:1px solid rgba(243,238,226,.14)}
.vlt-steps .st:last-child{border-bottom:0}
.vlt-steps .st .n{font-family:'Fraunces',serif;font-weight:900;font-size:1.7rem;color:var(--gold);line-height:1}
.vlt-steps .st h4{font-size:1.14rem;margin:0 0 4px;color:var(--paper)}
.vlt-steps .st p{margin:0;font-size:.98rem;color:rgba(243,238,226,.82);line-height:1.6}
.vlt-steps .st a{color:var(--sprout-bright);text-decoration:none;font-weight:600}
.vlt-disc{background:var(--paper-warm);border:1px dashed var(--line);border-radius:8px;padding:18px 22px;margin:34px 0 0;font-size:.94rem;color:var(--ink-faint);line-height:1.62}
.vlt-cta{text-align:center;padding:8px 0 0}
.vlt-cta a{color:var(--sprout);font-weight:700;text-decoration:none;border-bottom:2px solid var(--line)}
@media(max-width:640px){.vlt-build{padding:30px 22px}}
"""


def build_vault():
    url = f"{SITE}/vault.html"
    title = "The Offline Knowledge Vault — Free Databases, Audiobooks & Learning | Texas Roots"
    desc = ("A curated directory of the world's biggest FREE offline knowledge: all of "
            "Wikipedia, Project Gutenberg, the Survivor Library, medical and repair "
            "guides, free audiobooks (LibriVox), and free courses — plus how to build "
            "your own offline knowledge server. A companion to Project NOMAD, by Jordan Polasek.")
    schema = [
        {"@context": "https://schema.org", "@type": "CollectionPage",
         "name": "The Offline Knowledge Vault",
         "description": desc,
         "author": {"@type": "Person", "name": "Jordan Polasek", "url": "https://jordanpolasek.com"},
         "publisher": {"@type": "Organization", "name": "Texas Roots", "url": SITE},
         "mainEntityOfPage": url, "inLanguage": "en-US"},
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Texas Roots", "item": f"{SITE}/"},
            {"@type": "ListItem", "position": 2, "name": "Offline Knowledge Vault", "item": url}]},
    ]
    schema_html = "".join(f'<script type="application/ld+json">{json.dumps(s)}</script>\n' for s in schema)

    body = f'''<section class="vlt-hero"><div class="wrap">
<div class="eyebrow">A companion to Project NOMAD · curated by Jordan Polasek</div>
<h1>The world's knowledge, <em>kept free — and kept offline.</em></h1>
<p class="lede">A seed bank and a knowledge bank are the same idea: gather what matters while it's easy, so you have it when it isn't. Here is the actual shelf — the biggest free databases to download, the best free audiobooks and courses, and exactly how to keep it all working with no internet at all.</p>
<div class="jump">
  <a href="#databases">📚 Offline databases</a>
  <a href="#build">🛠 Build your own</a>
  <a href="#audio">🎧 Free audiobooks</a>
  <a href="#learn">🎓 Free learning</a>
</div>
</div></section>

<div class="vlt-body"><div class="wrap">

<section class="vlt-sec" id="databases">
  <div class="kicker">The big offline databases</div>
  <h2>Download the world's libraries</h2>
  <p class="intro">These are the giants — millions of articles, books, guides, and maps you can hold on a drive at home. The tool that opens most of them is <strong>Kiwix</strong>; the rest download straight to a phone or laptop. Grab Wikipedia first; add the others as space allows.</p>
  {grid(OFFLINE_DBS)}
</section>

<section class="vlt-sec" id="build">
  <div class="vlt-build">
    <h3>🛠 Build your own offline knowledge server</h3>
    <p class="sub">You don't need to be technical, and you don't need much. Any of these gets you a private library that works in a blackout, off-grid, or anywhere with no signal.</p>
    <div class="vlt-steps">
      <div class="st"><div class="n">1</div><div><h4>Pick the hardware you already have</h4><p>An old laptop, a mini-PC, or a <strong>Raspberry Pi</strong> ($35–80). Add a big external SSD (a 2–4 TB drive holds Wikipedia, Gutenberg, maps, and more with room to spare).</p></div></div>
      <div class="st"><div class="n">2</div><div><h4>Install a reader/server</h4><p>Easiest: <a href="https://kiwix.org" target="_blank" rel="noopener">Kiwix</a> on your phone or computer for reading .zim files. To share a whole library over your home Wi-Fi, use <strong>Kiwix-serve</strong>, <a href="https://internet-in-a-box.org" target="_blank" rel="noopener">Internet-in-a-Box (IIAB)</a>, or turnkey <a href="https://www.projectnomad.us" target="_blank" rel="noopener">Project NOMAD</a>.</p></div></div>
      <div class="st"><div class="n">3</div><div><h4>Download what matters</h4><p>From the <a href="https://library.kiwix.org" target="_blank" rel="noopener">Kiwix library</a>: Wikipedia, Gutenberg, medical, iFixit, Khan, Stack Exchange. Add offline maps with <a href="https://organicmaps.app" target="_blank" rel="noopener">Organic Maps</a> or <a href="https://osmand.net" target="_blank" rel="noopener">OsmAnd</a>, and audiobooks from <a href="https://librivox.org" target="_blank" rel="noopener">LibriVox</a>.</p></div></div>
      <div class="st"><div class="n">4</div><div><h4>Test it with the power off</h4><p>Turn off your internet and open the library. If it works unplugged, it'll work when you need it. Refresh the downloads once or twice a year.</p></div></div>
    </div>
  </div>
</section>

<section class="vlt-sec" id="audio">
  <div class="kicker">Free audiobooks — separate from the databases</div>
  <h2>Thousands of books, read aloud, free</h2>
  <p class="intro">Every one of these is legal and free. Download the MP3s and they're yours to keep offline — for long drives, chores, kids at bedtime, or a night with no screen.</p>
  {grid(AUDIOBOOKS)}
</section>

<section class="vlt-sec" id="learn">
  <div class="kicker">Free learning &amp; reference</div>
  <h2>Teach yourself anything, for nothing</h2>
  <p class="intro">Real textbooks, real university courses, and reference libraries — free to use now and, in most cases, free to download and keep. Pair these with the offline server above and you have a school that never closes.</p>
  {grid(LEARNING)}
</section>

<div class="vlt-disc">A note on honesty: I don't run or profit from any tool listed here — I share what I actually use and trust. Always confirm licenses before redistributing, keep more than one copy of anything you can't replace, and treat medical and survival references as a starting point, not a replacement for a professional when one is reachable.</div>

<div class="vlt-cta"><p>Want the story behind why I keep all this offline? Read <a href="nomad.html">Project NOMAD →</a> · Or start with a <a href="almanac/how-to-grow-a-survival-garden.html">survival garden →</a></p></div>

</div></div>
'''

    page = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="author" content="Jordan Polasek">
<link rel="canonical" href="{url}">
<meta property="og:title" content="The Offline Knowledge Vault — Free & Offline Forever">
<meta property="og:description" content="All of Wikipedia, 70,000 free books, the Survivor Library, free audiobooks and courses — and how to keep them with no internet.">
<meta property="og:type" content="website"><meta property="og:url" content="{url}">
{FAVICON}
{FONTS}
<link rel="stylesheet" href="assets/styles.css">
<style>{VAULT_CSS}</style>
{schema_html}</head>
<body>'''
    page += nav()
    page += body
    page += footer()
    open(os.path.join(ROOT, "vault.html"), "w").write(page)
    print("Built vault.html")


if __name__ == "__main__":
    build_vault()
