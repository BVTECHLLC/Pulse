#!/usr/bin/env python3
"""Texas Roots — master build (v6.5).

Runs every generator, then post-processes ALL html so internal links are
extension-less (e.g. /weather not /weather.html). This matches how Cloudflare
Pages actually serves files (it 308-redirects /x.html -> /x), so every link
resolves with a single 200 and there are no redirect hops to break or cache
badly. Run this instead of the individual generators.
"""
import os, sys, glob, re, subprocess, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

def run(script):
    print(f"  -> {script}")
    subprocess.run([sys.executable, os.path.join(HERE, script)], check=True, cwd=ROOT)

# 1) generate everything
print("Generating pages...")
for s in ("build.py","build_plants.py","build_nomad.py","build_vault.py","build_start_here.py","build_sitemap.py"):
    run(s)

# 2) make every internal link extension-less (href + absolute tx-plants.com URLs)
print("Post-processing links to extension-less...")
HREF = re.compile(r'(href=")((?!https?:|mailto:|tel:|data:|//)[^"]*?\.html(?:[#?][^"]*)?)(")')
ABS  = re.compile(r'https://tx-plants\.com/[^"\s]*?\.html')

def href_repl(m):
    pre,url,post = m.group(1),m.group(2),m.group(3)
    frag=''
    for sep in ('#','?'):
        if sep in url:
            i=url.index(sep); frag=url[i:]; url=url[:i]; break
    if not url.endswith('.html'): return m.group(0)
    base=url[:-5]
    if base=='index': new='./'
    elif base.endswith('/index'): new=base[:-5]
    else: new=base
    return f'{pre}{new}{frag}{post}'

def abs_repl(m):
    base=m.group(0)[:-5]
    return base[:-5] if base.endswith('/index') else base

n=0
for f in glob.glob(os.path.join(ROOT,'**','*.html'), recursive=True):
    # blog/ is SKIPPED on purpose: the Pulse daily publisher appends posts and
    # listing cards there and matches them by their .html hrefs — normalizing
    # those links would break the auto-blogger's card recognition. Cloudflare
    # 308s /blog/x.html -> /blog/x anyway, so visitors still get clean URLs.
    rel = os.path.relpath(f, ROOT).replace(os.sep, '/')
    if rel.startswith('blog/'):
        continue
    s=open(f,encoding='utf-8').read()
    c=ABS.sub(abs_repl, HREF.sub(href_repl, s))
    if c!=s: open(f,'w',encoding='utf-8').write(c); n+=1
print(f"  link-normalized {n} html files")

# 3) sitemap: strip .html from <loc> too (canonical URLs)
sm=os.path.join(ROOT,'sitemap.xml')
if os.path.exists(sm):
    s=open(sm).read()
    s=re.sub(r'(<loc>https://tx-plants\.com/[^<]*?)\.html(</loc>)',
             lambda m:(m.group(1)[:-5]+'/'+m.group(2)) if m.group(1).endswith('/index') else (m.group(1)+m.group(2)), s)
    # index.html at root handled: /index -> /
    s=s.replace('<loc>https://tx-plants.com/index</loc>','<loc>https://tx-plants.com/</loc>')
    open(sm,'w').write(s)
    print("  sitemap normalized")

print("BUILD COMPLETE.")
