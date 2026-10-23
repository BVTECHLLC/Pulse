"""bvtech.org free-tool pages published by Pulse (v1.95).

First tool: the PHP2Shell exposure checker. The page is built from the LIVE
tools page's own skeleton (head, header/nav, footer) so it matches the site
without us ever seeing its markup, then committed to the bvtech.org repo with
the same GitLab token the daily publisher uses. A link card is added to the
tools index by cloning one of its existing cards; when no card is
recognisable, a small callout is placed at the top of the page instead.

Safety: every value that comes back from a checked site (headers, signals) is
rendered with textContent, never innerHTML — a checked site is attacker-
controlled input. The checker itself is passive (see services/php2shell).
"""
from __future__ import annotations

import html as _h
import re

from sqlalchemy.orm import Session

PAGE_PATH = "tools/php2shell-check.html"
PAGE_URL = "/tools/php2shell-check.html"
JS_PATH = "tools/php2shell-check.js"
JS_URL = "/tools/php2shell-check.js"
TITLE = "Free PHP2Shell Exposure Check | BVTech"
DESC = ("Is your website exposed to PHP2Shell (CVE-2026-109618 / CVE-2026-109619)? "
        "Free, passive check from BVTech — no attack traffic, results in seconds.")
CARD_TITLE = "PHP2Shell Exposure Check"
CARD_EXCERPT = ("New: is your website exposed to the October 2026 PHP flaw that took "
                "4chan offline? Free, passive check in seconds.")

_MIN_SHELL = ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
              "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
              "<title></title><meta name=\"description\" content=\"\"></head>"
              "<body style=\"background:#0b0d1a;color:#e8eaf2;font-family:system-ui,"
              "sans-serif\"><main></main></body></html>")


def tool_body() -> str:
    return f"""
<section class="p2s" id="php2shell-check">
<style>
.p2s{{max-width:860px;margin:0 auto;padding:56px 20px 72px;line-height:1.6}}
.p2s .p2s-eyebrow{{font-size:.78rem;letter-spacing:.14em;text-transform:uppercase;color:#10b981;font-weight:700}}
.p2s h1{{font-size:clamp(1.9rem,4vw,2.6rem);line-height:1.15;margin:.35em 0 .4em}}
.p2s .p2s-lead{{opacity:.85;font-size:1.06rem;margin:0 0 28px}}
.p2s form.p2s-row{{display:flex;gap:10px;flex-wrap:wrap}}
.p2s input{{flex:1 1 260px;min-width:0;padding:14px 16px;border-radius:10px;border:1px solid rgba(127,127,160,.45);background:rgba(127,127,160,.08);color:inherit;font-size:1rem}}
.p2s button{{padding:14px 22px;border-radius:10px;border:0;background:#4f46e5;color:#fff;font-weight:700;font-size:1rem;cursor:pointer}}
.p2s button[disabled]{{opacity:.6;cursor:wait}}
.p2s .p2s-card{{margin-top:26px;padding:22px 24px;border-radius:14px;border:1px solid rgba(127,127,160,.35);background:rgba(127,127,160,.07)}}
.p2s .p2s-badge{{display:inline-block;padding:4px 12px;border-radius:999px;font-weight:800;font-size:.85rem;letter-spacing:.04em}}
.p2s .bad{{background:#fbebeb;color:#b42318}}.p2s .warn{{background:#f9eeda;color:#93370d}}.p2s .good{{background:#e5f4e4;color:#067647}}
.p2s ul{{padding-left:1.2em}}.p2s li{{margin:.25em 0}}
.p2s .p2s-muted{{opacity:.7;font-size:.9rem}}
.p2s .p2s-cta{{margin-top:18px;padding:16px 18px;border-radius:12px;background:rgba(79,70,229,.12);border:1px solid rgba(79,70,229,.4)}}
.p2s a{{color:#818cf8}}
.p2s h2{{font-size:1.25rem;margin:40px 0 8px}}
</style>
<div class="p2s-eyebrow">Free security tool</div>
<h1>PHP2Shell Exposure Check</h1>
<p class="p2s-lead">On October 21, 2026, PHP patched two critical flaws (CVE-2026-109618 and
CVE-2026-109619) that let attackers take over PHP websites with no login. WordPress, Drupal
and Joomla sites are all built on PHP. Enter your website to see whether it advertises a
vulnerable PHP version.</p>
<form class="p2s-row" id="p2s-form" autocomplete="off">
  <input id="p2s-host" type="text" inputmode="url" placeholder="yourbusiness.com" aria-label="Website address" required>
  <button id="p2s-go" type="submit">Check my site</button>
</form>
<p class="p2s-muted">Passive check: we load your homepage once, like any visitor, and read what
it already tells browsers. We never send attack traffic.</p>
<div id="p2s-out" aria-live="polite"></div>

<h2>What is PHP2Shell?</h2>
<p>An attacker sends an oversized upload that makes PHP run out of memory mid-request. PHP
frees that memory but keeps pointers to it, and the attacker's next request reuses them to
run code or leak server memory. It happens before your website's own code runs, so plugin
and theme updates do not fix it. Only upgrading PHP itself to 8.2.35, 8.3.36, 8.4.27 or
8.5.12 does.</p>
<h2>Need it fixed?</h2>
<p>BVTech patches and hardens business websites across Texas. Call <a href="tel:+12105383669">(210) 538-3669</a>
or email <a href="mailto:help@bvtech.org">help@bvtech.org</a>.</p>
</section>
<script src="{JS_URL}" defer></script>
"""


def tool_js(api_base: str) -> str:
    """The checker's script, served as its own file so a site CSP that bans
    inline scripts can't silently disable the button."""
    api = api_base.rstrip("/").replace('"', "")
    return f"""(function(){{
  var API = "{api}/api/public-tools";
  var form = document.getElementById("p2s-form"), out = document.getElementById("p2s-out"),
      btn = document.getElementById("p2s-go"), inp = document.getElementById("p2s-host");
  function el(tag, cls, text){{ var e = document.createElement(tag); if (cls) e.className = cls;
    if (text != null) e.textContent = text; return e; }}
  var LABEL = {{vulnerable:["EXPOSED","bad"], vulnerable_eol:["EXPOSED (UNSUPPORTED PHP)","bad"],
    php_version_hidden:["POSSIBLY EXPOSED","warn"], patched:["PATCHED","good"],
    no_php_detected:["NO PHP DETECTED","good"], eol_unaffected:["OUTDATED PHP","warn"],
    unknown_branch:["CHECK WITH YOUR HOST","warn"]}};
  function render(r){{
    out.textContent = "";
    var card = el("div","p2s-card");
    if (r.error){{ card.appendChild(el("p",null,r.error)); out.appendChild(card); return; }}
    var lab = LABEL[r.verdict] || ["RESULT","warn"];
    card.appendChild(el("span","p2s-badge "+lab[1],lab[0]));
    card.appendChild(el("h3",null,r.host + (r.version ? " — PHP " + r.version : "")));
    card.appendChild(el("p",null,r.detail || ""));
    if (r.signals && r.signals.length){{
      card.appendChild(el("p","p2s-muted","What we saw: " + r.signals.join(" · ")));
    }}
    if (r.next_steps && r.next_steps.length){{
      var ul = el("ul"); r.next_steps.forEach(function(s){{ ul.appendChild(el("li",null,s)); }});
      card.appendChild(el("p",null,"What to do:")); card.appendChild(ul);
    }}
    var risky = ["vulnerable","vulnerable_eol","php_version_hidden"].indexOf(r.verdict) >= 0;
    var cta = el("div","p2s-cta");
    cta.appendChild(el("p",null, risky
      ? "Want us to confirm and fix it? Leave your email and we will follow up today."
      : "Want the full report and a free security review? Leave your email."));
    var lf = el("form","p2s-row"); var em = el("input"); em.type = "email";
    em.placeholder = "you@business.com"; em.required = true; em.setAttribute("aria-label","Email");
    var sb = el("button",null,"Send me the report"); sb.type = "submit";
    lf.appendChild(em); lf.appendChild(sb); cta.appendChild(lf);
    var note = el("p","p2s-muted",""); cta.appendChild(note);
    lf.addEventListener("submit", function(ev){{
      ev.preventDefault(); sb.disabled = true;
      fetch(API + "/lead", {{method:"POST", headers:{{"Content-Type":"text/plain"}},
        body: JSON.stringify({{email: em.value, tool: "PHP2Shell Check",
          result: (r.host + ": " + r.verdict + (r.version ? " (PHP " + r.version + ")" : "")).slice(0,380)}})}})
      .then(function(x){{ return x.json(); }})
      .then(function(j){{ note.textContent = j.ok ? "Thanks — we will be in touch shortly."
                                                  : (j.error || "Something went wrong."); }})
      .catch(function(){{ note.textContent = "Could not send — email help@bvtech.org."; }})
      .finally(function(){{ sb.disabled = false; }});
    }});
    card.appendChild(cta);
    out.appendChild(card);
  }}
  form.addEventListener("submit", function(ev){{
    ev.preventDefault();
    var host = inp.value.trim().replace(/^https?:\\/\\//i,"").split("/")[0];
    if (!host) return;
    btn.disabled = true; btn.textContent = "Checking…";
    out.textContent = ""; out.appendChild(el("p","p2s-muted","Loading " + host + "…"));
    fetch(API + "/php2shell-check?host=" + encodeURIComponent(host))
      .then(function(x){{ return x.json(); }}).then(render)
      .catch(function(){{ render({{error:"Could not reach the checker. Try again in a minute."}}); }})
      .finally(function(){{ btn.disabled = false; btn.textContent = "Check my site"; }});
  }});
}})();
"""


def build_page(skeleton: str | None, body: str, *, site: str) -> str:
    """Drop `body` into the skeleton's content area and retitle the page."""
    h = skeleton or _MIN_SHELL
    t, d = _h.escape(TITLE), _h.escape(DESC, quote=True)
    url = f"{site}{PAGE_URL}"
    h = re.sub(r"<title>.*?</title>", f"<title>{t}</title>", h, count=1, flags=re.S | re.I)
    h = re.sub(r'(<meta\s+name="description"\s+content=")[^"]*(")', rf"\g<1>{d}\2", h, count=1, flags=re.I)
    h = re.sub(r'(<meta\s+property="og:title"\s+content=")[^"]*(")', rf"\g<1>{t}\2", h, count=1, flags=re.I)
    h = re.sub(r'(<meta\s+property="og:description"\s+content=")[^"]*(")', rf"\g<1>{d}\2", h, count=1, flags=re.I)
    h = re.sub(r'(<meta\s+property="og:url"\s+content=")[^"]*(")', rf"\g<1>{url}\2", h, count=1, flags=re.I)
    h = re.sub(r'(<link\s+rel="canonical"\s+href=")[^"]*(")', rf"\g<1>{url}\2", h, count=1, flags=re.I)
    m = re.search(r"<main\b[^>]*>", h, re.I)
    end = h.lower().rfind("</main>")
    if m and end > m.end():
        return h[:m.end()] + body + h[end:]
    hdr = re.search(r"</header>", h, re.I)
    ftr = h.lower().rfind("<footer")
    if hdr and ftr > hdr.end():
        return h[:hdr.end()] + "<main>" + body + "</main>" + h[ftr:]
    b = re.search(r"<body\b[^>]*>", h, re.I)
    bend = h.lower().rfind("</body>")
    if b and bend > b.end():
        return h[:b.end()] + "<main>" + body + "</main>" + h[bend:]
    return build_page(_MIN_SHELL, body, site=site)


def _callout() -> str:
    return ('<div class="p2s-callout" style="margin:24px auto;max-width:960px;padding:16px 20px;'
            'border-radius:12px;border:1px solid rgba(79,70,229,.45);background:rgba(79,70,229,.12)">'
            '<strong>New &middot; ' + _h.escape(CARD_TITLE) + '</strong> &mdash; '
            + _h.escape(CARD_EXCERPT) + f' <a href="{PAGE_URL}" style="font-weight:700">'
            'Check your site &rarr;</a></div>')


def link_into_index(index_html: str) -> tuple[str, bool, str]:
    """Add the tool to the tools index. Returns (html, changed, how)."""
    from . import jp_site
    if "php2shell-check" in index_html:
        return index_html, False, "already linked"
    new, changed = jp_site.inject_post_into_listing(
        index_html, title=CARD_TITLE, url=PAGE_URL, excerpt=CARD_EXCERPT,
        date_str="", style="blog-file", file_dir="tools")
    if changed:
        return new, True, "card cloned"
    h = index_html
    for rx in (r"</h1>", r"<main\b[^>]*>", r"</header>"):
        m = re.search(rx, h, re.I)
        if m:
            return h[:m.end()] + _callout() + h[m.end():], True, "callout"
    return h, False, "no insertion point"


def publish_php2shell_tool(db: Session) -> dict:
    """Commit the checker page + its link on the tools index to bvtech.org."""
    from ..core.config import get_settings
    from . import cloudflare, jp_site
    cfg = jp_site.get_config(db, "bvtech")
    if not cfg["configured"]:
        return {"ok": False, "error": "bvtech.org not connected (GitLab token needed)"}
    site = jp_site.SITES["bvtech"]["site"]
    try:
        ops = jp_site._repo_ops(cfg)
        index_html = ops["fetch"]("tools/index.html")
        skeleton = index_html or ops["fetch"]("index.html")
        page = build_page(skeleton, tool_body(), site=site)
        js_exists = ops["fetch"](JS_PATH) is not None
        ops["commit"](JS_PATH, tool_js(get_settings().PUBLIC_BASE_URL),
                      "tools: PHP2Shell checker script (via Pulse)", js_exists)
        exists = ops["fetch"](PAGE_PATH) is not None
        ops["commit"](PAGE_PATH, page, "tools: PHP2Shell exposure check (via Pulse)", exists)
        how = "no tools index found"
        if index_html:
            new_index, changed, how = link_into_index(index_html)
            if changed:
                ops["commit"]("tools/index.html", new_index,
                              "tools: link the PHP2Shell exposure check (via Pulse)", True)
        purge = cloudflare.purge_urls(db, "bvtech", [f"{site}{PAGE_URL}", f"{site}{JS_URL}",
                                                     f"{site}/tools/"])
        return {"ok": True, "url": f"{site}{PAGE_URL}", "page_updated": exists,
                "index_link": how, "cache_purged": purge.get("ok")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}
