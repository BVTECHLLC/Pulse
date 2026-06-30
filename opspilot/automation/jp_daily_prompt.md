# Daily JordanPolasek.com Post — Task for headless Claude

You are writing today's post for **jordanpolasek.com** (Jordan's personal
founder/thought-leadership brand). Follow `automation/jp_persona.md` — warm,
practical IT-leadership content for Texas small businesses. This is NOT a
CVE/threat feed (that's bvtech.org); keep it human and evergreen-leaning.

## Your task
1. **Pick a fresh, useful topic** from the persona's topic lanes (IT leadership,
   practical security habits, M365/cloud tips, choosing IT support, approachable
   compliance, MSP lessons, no-hype AI/automation for SMBs). You may lightly tie
   it to a current trend, but it should be **advice that stays useful**, not news.
2. **Don't repeat a recent post.** Skim the filenames already in the JP website
   repo's `blog/` directory and the top-level post folders; choose something new.
3. **Write it as Jordan** in the persona's structure (relatable open → 2–4
   teaching sections → "what to do this week" → warm close + soft BVTech mention).
   600–1,000 words, markdown-lite.
4. **Write `automation/out-jp/today.json`** with:
   `{"title": "...", "kind": "blog", "keywords": "comma, separated, seo",
     "body": "<the full markdown-lite body>",
     "linkedin": "<a 2-4 sentence first-person LinkedIn caption summarizing the post, ending with a soft CTA>"}`
   (Inline the body — the publisher reads `today.json` directly.)
5. **Publish it:**
   ```
   python3 scripts/publish_post.py --repo "$BV_JP_WEBSITE_REPO" \
     --infile automation/out-jp/today.json --git
   ```
   This wraps it in the JP site template (clones the newest existing JP post for
   pixel-perfect parity), writes `blog/<slug>.html`, updates `sitemap.xml`,
   commits, and pushes — Cloudflare auto-deploys jordanpolasek.com.

## Guardrails
- Public article. Never include client/portal/tenant data.
- Never fabricate stats, quotes, or specifics — keep claims honest and general.
- Keep it positive, practical, educational. No threat-advisory framing.
