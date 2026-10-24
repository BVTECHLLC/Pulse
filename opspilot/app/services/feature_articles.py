"""Hand-written feature articles for bvtech.org (v1.101).

These are long-form pieces Jordan wanted on the site itself, not just on
LinkedIn: more depth, plain-English breakdowns and built-in graphics (pure
HTML/CSS/inline SVG, so they pass the site's `default-src 'self'` CSP and need
no image hosting). They publish through the same native post template as the
daily posts (content_studio.render_in_chrome) and are then PINNED as the
homepage feature and the /news/ special-report card (jp_site.FEATURED_PIN).
"""
from __future__ import annotations

PHP2SHELL_SLUG = "php2shell-explained-what-small-businesses-need-to-know"
PHP2SHELL_URL = f"/blog/{PHP2SHELL_SLUG}.html"
PHP2SHELL_TITLE = "PHP2Shell, Explained: What Happened, Who's at Risk, and How to Check Your Site"
PHP2SHELL_EXCERPT = ("Two PHP flaws took 4chan and parts of Wikimedia offline and sent the web "
                     "scrambling to patch. Here's how the attack works in plain English, which "
                     "setups are actually at risk, and a free tool to check your own site.")
PHP2SHELL_DATE = "2026-10-23"

# Article-only graphics. Scoped under .px so nothing leaks into the site chrome.
_CSS = """<style>
.px-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:8px 0 36px}
.px-stat{background:linear-gradient(160deg,rgba(68,64,219,.16),rgba(14,13,44,.4));border:1px solid rgba(255,255,255,.1);border-radius:12px;padding:18px 14px;text-align:center}
.px-stat b{display:block;font-size:1.7rem;line-height:1.1;color:#F5BE58;font-family:var(--fh,inherit)}
.px-stat span{display:block;margin-top:6px;font-size:.78rem;color:var(--muted,#a3a3bd);line-height:1.4}
.px-flow{display:grid;grid-template-columns:1fr auto 1fr auto 1fr;gap:10px;align-items:stretch;margin:8px 0 34px}
.px-step{background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.1);border-radius:12px;padding:18px 16px;position:relative}
.px-step .n{display:inline-flex;width:28px;height:28px;border-radius:50%;align-items:center;justify-content:center;background:#EB6F24;color:#0E0D2C;font-weight:800;font-size:.85rem;margin-bottom:10px}
.px-step h4{margin:0 0 6px;color:var(--white,#fff);font-size:1rem;line-height:1.35}
.px-step p{margin:0;font-size:.86rem;line-height:1.6;color:var(--text,#d6d6e6)}
.px-step.bad{border-color:rgba(235,80,60,.45);background:rgba(235,80,60,.07)}
.px-arrow{display:flex;align-items:center;justify-content:center;color:#EB6F24;font-size:1.4rem}
.px-tl{list-style:none;padding:0 !important;margin:8px 0 34px;border-left:2px solid rgba(235,111,36,.4)}
.px-tl li{position:relative;padding:0 0 22px 24px;margin:0}
.px-tl li:before{content:"";position:absolute;left:-7px;top:6px;width:12px;height:12px;border-radius:50%;background:#EB6F24;box-shadow:0 0 0 4px rgba(235,111,36,.18)}
.px-tl li.us:before{background:#4440DB;box-shadow:0 0 0 4px rgba(68,64,219,.25)}
.px-tl .when{display:block;font-size:.74rem;letter-spacing:.08em;text-transform:uppercase;color:#F5BE58;font-weight:700;margin-bottom:3px}
.px-risk{margin:8px 0 34px;display:grid;gap:10px}
.px-row{display:grid;grid-template-columns:190px 1fr 74px;gap:14px;align-items:center;font-size:.9rem;color:var(--text,#d6d6e6)}
.px-bar{height:12px;border-radius:6px;background:rgba(255,255,255,.07);overflow:hidden}
.px-bar i{display:block;height:100%;border-radius:6px}
.px-lvl{font-size:.72rem;font-weight:800;letter-spacing:.06em;text-align:center;padding:3px 0;border-radius:4px}
.px-hi i{width:100%;background:linear-gradient(90deg,#EB6F24,#e5484d)} .px-hi .px-lvl{background:rgba(229,72,77,.18);color:#ff8d8f}
.px-md i{width:60%;background:linear-gradient(90deg,#F5BE58,#EB6F24)} .px-md .px-lvl{background:rgba(245,190,88,.16);color:#F5BE58}
.px-lo i{width:22%;background:#4440DB} .px-lo .px-lvl{background:rgba(68,64,219,.2);color:#a9a7ff}
.px-no i{width:4%;background:#3fb68b} .px-no .px-lvl{background:rgba(63,182,139,.16);color:#6fe0b4}
.px-check{list-style:none;padding:0 !important;margin:8px 0 30px;counter-reset:c}
.px-check li{counter-increment:c;position:relative;padding:14px 16px 14px 56px;margin:0 0 10px;background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.09);border-radius:10px}
.px-check li:before{content:counter(c);position:absolute;left:16px;top:13px;width:26px;height:26px;border-radius:7px;background:linear-gradient(135deg,#EB6F24,#F5BE58);color:#0E0D2C;font-weight:800;display:flex;align-items:center;justify-content:center;font-size:.85rem}
.px-verdicts{display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 30px}
.px-verdicts span{font-size:.8rem;padding:6px 12px;border-radius:999px;border:1px solid rgba(255,255,255,.14);color:var(--text,#d6d6e6)}
.px-verdicts .r{border-color:rgba(229,72,77,.5);color:#ff8d8f}.px-verdicts .y{border-color:rgba(245,190,88,.5);color:#F5BE58}.px-verdicts .g{border-color:rgba(63,182,139,.5);color:#6fe0b4}
.px-tool{display:flex;gap:18px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin:8px 0 36px;padding:22px 24px;border-radius:14px;background:linear-gradient(135deg,rgba(68,64,219,.18),rgba(235,111,36,.12));border:1px solid rgba(245,190,88,.35)}
.px-tool p{margin:0 !important;max-width:460px}
.px-tool a.go{display:inline-block;padding:12px 20px;border-radius:9px;background:#EB6F24;color:#0E0D2C !important;font-weight:800;text-decoration:none !important;white-space:nowrap}
.px-faq details{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.09);border-radius:10px;padding:14px 18px;margin:0 0 10px}
.px-faq summary{cursor:pointer;color:var(--white,#fff);font-weight:700;line-height:1.5}
.px-faq details p{margin:12px 0 0 !important}
.px-src{font-size:.86rem}
.px-fig{margin:6px 0 34px;padding:18px;border-radius:12px;background:rgba(14,13,44,.45);border:1px solid rgba(255,255,255,.08)}
.px-fig figcaption{font-size:.8rem;color:var(--muted,#a3a3bd);margin-top:10px;text-align:center}
@media (max-width:720px){
 .px-stats{grid-template-columns:repeat(2,1fr)}
 .px-flow{grid-template-columns:1fr}
 .px-arrow{transform:rotate(90deg);height:26px}
 .px-row{grid-template-columns:1fr 64px;gap:6px 10px}
 .px-row .px-bar{grid-column:1/-1;grid-row:2}
 .px-fig{overflow-x:auto;padding:14px}
 .px-fig svg{min-width:620px}
}
</style>"""

# Inline SVG: why a crashed request poisons the NEXT one (worker memory diagram).
_SVG_WORKER = """<figure class="px-fig"><svg viewBox="0 0 720 230" role="img" aria-labelledby="pxw-t" style="width:100%;height:auto;display:block">
<title id="pxw-t">One PHP worker handles request A, crashes out of memory, then reuses stale pointers on request B</title>
<defs><marker id="pxa" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#EB6F24"/></marker></defs>
<rect x="10" y="20" width="700" height="190" rx="14" fill="none" stroke="rgba(255,255,255,.18)" stroke-dasharray="5 5"/>
<text x="26" y="44" fill="#a3a3bd" font-size="13" font-family="sans-serif">ONE PHP WORKER PROCESS (stays alive between requests)</text>
<rect x="30" y="64" width="190" height="120" rx="10" fill="rgba(235,111,36,.12)" stroke="#EB6F24"/>
<text x="125" y="92" text-anchor="middle" fill="#fff" font-size="15" font-weight="700" font-family="sans-serif">Request A</text>
<text x="125" y="116" text-anchor="middle" fill="#d6d6e6" font-size="12" font-family="sans-serif">huge upload + upload-</text>
<text x="125" y="132" text-anchor="middle" fill="#d6d6e6" font-size="12" font-family="sans-serif">progress session data</text>
<text x="125" y="162" text-anchor="middle" fill="#ff8d8f" font-size="12" font-weight="700" font-family="sans-serif">💥 out-of-memory crash</text>
<rect x="265" y="64" width="190" height="120" rx="10" fill="rgba(229,72,77,.10)" stroke="#e5484d"/>
<text x="360" y="92" text-anchor="middle" fill="#fff" font-size="15" font-weight="700" font-family="sans-serif">Memory freed…</text>
<text x="360" y="116" text-anchor="middle" fill="#d6d6e6" font-size="12" font-family="sans-serif">…but PHP's globals still</text>
<text x="360" y="132" text-anchor="middle" fill="#d6d6e6" font-size="12" font-family="sans-serif">point at it ("dangling")</text>
<text x="360" y="162" text-anchor="middle" fill="#F5BE58" font-size="12" font-weight="700" font-family="sans-serif">use-after-free (CWE-416)</text>
<rect x="500" y="64" width="190" height="120" rx="10" fill="rgba(68,64,219,.16)" stroke="#4440DB"/>
<text x="595" y="92" text-anchor="middle" fill="#fff" font-size="15" font-weight="700" font-family="sans-serif">Request B</text>
<text x="595" y="116" text-anchor="middle" fill="#d6d6e6" font-size="12" font-family="sans-serif">reuses the stale pointers</text>
<text x="595" y="140" text-anchor="middle" fill="#ff8d8f" font-size="12" font-weight="700" font-family="sans-serif">→ run attacker code</text>
<text x="595" y="160" text-anchor="middle" fill="#ff8d8f" font-size="12" font-weight="700" font-family="sans-serif">→ or leak server memory</text>
<line x1="222" y1="124" x2="261" y2="124" stroke="#EB6F24" stroke-width="2.5" marker-end="url(#pxa)"/>
<line x1="457" y1="124" x2="496" y2="124" stroke="#EB6F24" stroke-width="2.5" marker-end="url(#pxa)"/>
</svg><figcaption>The crash happens before your website's own code even runs, so a plugin or theme update can't stop it. Only a fixed PHP build can.</figcaption></figure>"""

PHP2SHELL_BODY = _CSS + """
<div class="px-stats">
<div class="px-stat"><b>9.2</b><span>CVSS v4 severity (critical) on both CVEs</span></div>
<div class="px-stat"><b>2</b><span>flaws: CVE-2026-109618 &amp; CVE-2026-109619</span></div>
<div class="px-stat"><b>5.4→8.5</b><span>PHP versions with the vulnerable code</span></div>
<div class="px-stat"><b>Oct 21</b><span>patch day, the same day sites went dark</span></div>
</div>

<p>On Wednesday, October 21, 2026, a lot of the internet had a bad day. PHP, the language behind WordPress and a huge share of the web, shipped emergency fixes for two critical flaws now nicknamed <strong>PHP2Shell</strong>. The same day, 4chan and Something Awful went offline, the Wikimedia Foundation shut down many supporting services, and government sites in the U.K., Finland and Japan were disrupted. The FBI, NSA and the U.K.'s National Cyber Security Centre all put out warnings, and the NCSC told organizations to take systems offline if they couldn't update right away.</p>

<p>We got a lot of questions from clients this week, mostly some version of "Am I affected, and what do I actually do?" This post is the long answer, written for business owners rather than security engineers. If you only have a minute, skip to the <a href="#check">free checker</a>.</p>

<div class="callout"><p><strong>The short version:</strong> if your website runs on PHP (most WordPress, Drupal, Joomla and many custom sites do), the fix is to upgrade PHP itself to <strong>8.2.35, 8.3.36, 8.4.27 or 8.5.12</strong> or newer. Updating WordPress, plugins or themes does <em>not</em> fix this. If your host manages PHP for you, confirm with them that it's done.</p></div>

<h2>What is PHP2Shell, in plain English?</h2>

<p>Think of a PHP web server as a row of workers at a counter. Each one takes a request, does the job, cleans up and takes the next one. To be fast, a worker <em>stays alive</em> between customers instead of being replaced every time.</p>

<p>PHP2Shell abuses the cleanup step. An attacker sends a request designed to make the worker run out of memory partway through. PHP bails out and throws away that request's memory, but a few internal notes still point at the memory that was just thrown away. When the <em>next</em> request arrives at the same worker, PHP trusts those stale notes. With careful setup, an attacker can turn that into running their own code on your server, or into reading leftover memory that may hold other visitors' data.</p>

""" + _SVG_WORKER + """

<h2>How the attack works, step by step</h2>

<div class="px-flow">
<div class="px-step"><span class="n">1</span><h4>Set the trap</h4><p>A multipart upload request with PHP's "upload progress" session feature makes PHP set up session state very early, before any site code runs.</p></div>
<div class="px-arrow">➜</div>
<div class="px-step bad"><span class="n">2</span><h4>Force a crash</h4><p>The attacker pushes the worker into a fatal out-of-memory error mid-request. Memory is freed, but some global pointers aren't reset.</p></div>
<div class="px-arrow">➜</div>
<div class="px-step bad"><span class="n">3</span><h4>Spring it</h4><p>The next request on that worker uses the stale pointers: remote code execution, or leaked memory sent back in a <code>PHPSESSID</code> cookie.</p></div>
</div>

<p>There are two bugs. <strong>CVE-2026-109618</strong> is the memory corruption caused by the out-of-memory error. <strong>CVE-2026-109619</strong> is the "stale global state" left behind for the next request. Both are classed as use-after-free (CWE-416) and both are rated 9.2 out of 10. Researchers at Wiz showed pre-login code execution against WordPress, Drupal and Joomla, plus a memory leak that works no matter what application is running.</p>

<h2>A timeline of the week</h2>

<ul class="px-tl">
<li><span class="when">Since at least 2024</span>The PHP Foundation says the underlying problems had been known for a while, and work on a fix had stalled.</li>
<li><span class="when">Days before Oct 21</span>Details leak early. Cloudflare reports attackers probing sites and seeing exploitation attempts more than six hours before fixes were public.</li>
<li><span class="when">Oct 21 · 3:02 AM UTC</span>Cloudflare switches on WAF rules for every plan, including seven rules in the free managed ruleset, about nine hours before disclosure.</li>
<li><span class="when">Oct 21</span>PHP ships 8.2.35, 8.3.36, 8.4.27 and 8.5.12. 4chan and Something Awful go dark, Wikimedia pulls services offline, and the FBI, NSA and NCSC issue warnings.</li>
<li class="us"><span class="when">Oct 22–23 · BVTech</span>We audit everything we run and host, add request hardening to our client portal, and publish a free, passive PHP2Shell checker for anyone to use.</li>
</ul>

<h2>Where the AI angle comes in</h2>

<p>This is being called one of the first big "AI-era" vulnerabilities, and the reporting is honestly a little messy. OpenAI says one of its models helped find one of the bugs through a program that gives security firms access to its models. Wiz and Calif also used AI tools. The AP reported that people found the flaws first and AI agents helped work out the attack paths. There was also controversy over Chainguard posting fixes hours before the official disclosure, which critics said could have helped attackers.</p>

<p>The takeaway for a small business isn't "AI hacks everything now." It's that <strong>the window between a bug becoming known and someone exploiting it keeps shrinking.</strong> Patching "sometime this quarter" isn't good enough for internet-facing software anymore. Patching within days is the new normal.</p>

<h2>Am I at risk? It depends on your setup</h2>

<div class="px-risk">
<div class="px-row px-hi"><span><strong>Apache + mod_php</strong></span><div class="px-bar"><i></i></div><span class="px-lvl">HIGH</span></div>
<div class="px-row px-md"><span><strong>Nginx/Apache + PHP-FPM</strong></span><div class="px-bar"><i></i></div><span class="px-lvl">MEDIUM</span></div>
<div class="px-row px-lo"><span><strong>PHP command line only</strong></span><div class="px-bar"><i></i></div><span class="px-lvl">LOW</span></div>
<div class="px-row px-no"><span><strong>Static site / no PHP</strong></span><div class="px-bar"><i></i></div><span class="px-lvl">NONE</span></div>
</div>

<p>Apache with mod_php is the worst case because the whole attack happens before your site's code runs. PHP-FPM is still at risk, but how exploitable it is depends on the application. Command-line PHP and background workers don't face the internet, but they should still be patched. Sites that don't run PHP at all, like bvtech.org (static pages on Cloudflare), aren't affected.</p>

<h3>Which PHP versions are fixed?</h3>

<table>
<thead><tr><th>PHP branch</th><th>Fixed in</th><th>What to do</th></tr></thead>
<tbody>
<tr><td>8.5</td><td><strong>8.5.12</strong></td><td>Upgrade to 8.5.12 or newer</td></tr>
<tr><td>8.4</td><td><strong>8.4.27</strong></td><td>Upgrade to 8.4.27 or newer</td></tr>
<tr><td>8.3</td><td><strong>8.3.36</strong></td><td>Upgrade to 8.3.36 or newer</td></tr>
<tr><td>8.2</td><td><strong>8.2.35</strong></td><td>Upgrade to 8.2.35 or newer</td></tr>
<tr><td>8.1, 8.0, 7.4</td><td>Source-only backports</td><td>End of life: plan a move to 8.2+ now</td></tr>
<tr><td>7.3 and older (back to 5.4)</td><td>No fix</td><td>Vulnerable: upgrade urgently</td></tr>
</tbody>
</table>

<h2 id="check">Check your site for free</h2>

<p>We built a free checker that anyone can use. It's <strong>passive</strong>: it makes one ordinary request to your homepage, exactly like a visitor would, and reads what your server already advertises: the PHP version in the <code>X-Powered-By</code> or <code>Server</code> headers, whether a <code>PHPSESSID</code> cookie is set, and common CMS fingerprints. It never sends an exploit or anything harmful.</p>

<div class="px-tool"><p><strong>BVTech PHP2Shell Checker</strong><br>Enter a domain, get a plain-English verdict and next steps in seconds. Free, no signup.</p><a class="go" href="/tools/php2shell-check.html">Run the free check →</a></div>

<p>You'll get one of these results:</p>
<div class="px-verdicts"><span class="r">Vulnerable</span><span class="r">Vulnerable (end-of-life PHP)</span><span class="g">Patched</span><span class="y">PHP version hidden</span><span class="g">No PHP detected</span></div>

<p>"PHP version hidden" is common and is good hygiene, but it means the checker can't confirm either way, so ask your host or developer which version you're on.</p>

<h2>What to do this week</h2>

<ol class="px-check">
<li><strong>Upgrade PHP itself.</strong> Move to 8.2.35, 8.3.36, 8.4.27 or 8.5.12 or newer. On shared hosting, this is usually a PHP version dropdown in cPanel or your host's dashboard. Plugin and theme updates won't fix this.</li>
<li><strong>Put a WAF in front.</strong> Cloudflare's free plan includes PHP2Shell rules. It's a safety net while you patch, not a replacement for patching.</li>
<li><strong>If you can't patch today,</strong> have your developer set <code>session.upload_progress.enabled = 0</code> in php.ini or the PHP-FPM pool (it can't be changed from inside the app), keep <code>post_max_size</code> low, limit request sizes at the web server, and restart PHP workers.</li>
<li><strong>Restart after upgrading.</strong> PHP-FPM and Apache workers keep running old code until they restart.</li>
<li><strong>Look for signs of a break-in.</strong> Exploitation started before the patch, so check for new admin users, unfamiliar files in upload folders, and new scheduled tasks or cron jobs.</li>
<li><strong>Re-run the checker</strong> to confirm the new version is live.</li>
</ol>

<h2>What we did at BVTech</h2>

<p>We practice what we preach, so here's exactly what we checked and changed:</p>

<ul>
<li><strong>Audited every system we run.</strong> Our client portal runs Python, not PHP. Our public websites are static pages on Cloudflare, so nothing executes on a server. None of our sites were exposed to these CVEs.</li>
<li><strong>Hardened anyway.</strong> The technique behind this attack (oversized requests used to cause memory pressure) and the scanning wave that followed affect any web server. Our portal now rejects request bodies over 10&nbsp;MB, refuses file-upload requests it has no use for, and drops PHP and WordPress probe traffic before it touches anything else.</li>
<li><strong>Fixed what the audit turned up.</strong> Looking closely at our own public tools, we found and fixed a redirect-handling gap in one of them. Audits during a fire drill tend to find something.</li>
<li><strong>Built the free checker</strong> so clients and neighbors can answer "am I affected?" in seconds without logging in to anything.</li>
</ul>

<p>If you're a client with a PHP website we manage, we've already reviewed it or we're reaching out. If you're not sure whether something you own runs PHP, that's exactly the kind of question we're happy to answer.</p>

<h2>Frequently asked questions</h2>

<div class="px-faq">
<details><summary>I updated WordPress and all my plugins. Am I safe?</summary><p>Not necessarily. PHP2Shell is in PHP itself, the engine WordPress runs on. You need PHP 8.2.35, 8.3.36, 8.4.27 or 8.5.12 or newer. Check your hosting dashboard or ask your host.</p></details>
<details><summary>Is my Wix, Squarespace or Shopify site affected?</summary><p>Those platforms run their own infrastructure and patch it for you. You don't need to do anything on the server side.</p></details>
<details><summary>Does the BVTech checker attack my website?</summary><p>No. It makes one normal homepage request, the same as any visitor, and reads the headers your server already sends. It never sends exploit traffic.</p></details>
<details><summary>My checker result says "PHP version hidden." Is that bad?</summary><p>Hiding the version is good practice, but it means we can't confirm from the outside. Ask your host or developer for the exact PHP version, or contact us and we'll help.</p></details>
<details><summary>Is Cloudflare enough on its own?</summary><p>No. Cloudflare's rules block known attack patterns and buy you time, and attackers were already changing payloads to slip past filters. Upgrading PHP is the actual fix.</p></details>
</div>

<h2>Sources</h2>
<ul class="px-src">
<li><a href="https://en.wikipedia.org/wiki/PHP2Shell" rel="noopener" target="_blank">PHP2Shell, Wikipedia</a></li>
<li><a href="https://www.axios.com/2026/10/21/php-openai-ai-bug-hunting-cyberattacks" rel="noopener" target="_blank">Axios: OpenAI model uncovered massive flaw in web's foundational code</a></li>
<li><a href="https://www.nbcnews.com/tech/security/critical-vulnerabilities-php-update-systems-rcna604751" rel="noopener" target="_blank">NBC News: Critical vulnerabilities in PHP spark rush to update systems</a></li>
<li><a href="https://qz.com/php-vulnerabilities-ai-discovered-patch-websites-cisa-102326" rel="noopener" target="_blank">Quartz: AI-discovered PHP flaws trigger global rush to patch websites</a></li>
<li><a href="https://www.404media.co/php2shell-black-october-ai-is-changing-everything-about-hacking-no-one-knows-what-happens-next/" rel="noopener" target="_blank">404 Media: AI is changing everything about hacking</a></li>
<li>PHP security advisories GHSA-w8hw-w9fx-j79w (CVE-2026-109618) and GHSA-6wmf-4rv5-p3rp (CVE-2026-109619); Cloudflare blog, "Cloudflare deploys protections against php2shell vulnerability" (Oct 21, 2026)</li>
</ul>
"""

PHP2SHELL_FAQ = [
    ("I updated WordPress and all my plugins. Am I safe from PHP2Shell?",
     "Not necessarily. PHP2Shell is in PHP itself, the engine WordPress runs on. You need "
     "PHP 8.2.35, 8.3.36, 8.4.27 or 8.5.12 or newer."),
    ("Is my Wix, Squarespace or Shopify site affected by PHP2Shell?",
     "Those platforms run their own infrastructure and patch it for you."),
    ("Does the BVTech PHP2Shell checker attack my website?",
     "No. It makes one normal homepage request and reads the headers your server already "
     "sends. It never sends exploit traffic."),
    ("Is Cloudflare enough to stop PHP2Shell?",
     "No. Cloudflare's WAF rules buy time, but upgrading PHP is the actual fix."),
]

PHP2SHELL_CTA = ('<div class="pp-cta"><h3>Not sure if your site runs PHP?</h3>'
                 '<p>Run our free checker, or let BVTech look at it for you. We have kept '
                 'Texas businesses secure and running since 2013.</p>'
                 '<a class="pp-btn" href="/tools/php2shell-check.html">Free PHP2Shell Check</a>'
                 '<a class="pp-btn pp-btn2" href="/contact/">Talk to BVTech</a></div>')


def php2shell_post() -> dict:
    return {
        "title": PHP2SHELL_TITLE,
        "slug": PHP2SHELL_SLUG,
        "date": PHP2SHELL_DATE,
        "html": PHP2SHELL_BODY,
        "description": PHP2SHELL_EXCERPT,
        "excerpt": PHP2SHELL_EXCERPT,
        "keywords": ("PHP2Shell, CVE-2026-109618, CVE-2026-109619, PHP vulnerability, "
                     "WordPress security, PHP 8.4.27, small business cybersecurity"),
        "author": "Jordan Polasek",
        "tags": ["PHP2Shell", "Special Report", "Free Tool", "WordPress", "Patch Now"],
        "crumb": "PHP2Shell Explained",
        "faq": PHP2SHELL_FAQ,
        "cta_html": PHP2SHELL_CTA,
        "feature": True,          # never swept as same-day "flood"
    }


def publish_php2shell(db) -> dict:
    """Publish (or re-publish, idempotently) the feature to bvtech.org."""
    from . import jp_site
    return jp_site.publish(db, php2shell_post(), "bvtech")
