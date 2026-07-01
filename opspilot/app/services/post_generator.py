"""v0.73 Post generator — on-brand, SEO-tuned social post drafts, no API needed.

A curated library of high-performing MSP / IT-security post angles (tips,
advisories, seasonal, social proof, CTAs). Each is woven with the business's
**city** and a rotating **keyword** so posts are locally relevant and varied —
exactly what LinkedIn and Google Business reward. Deterministic (rotates by
index), so the same inputs always produce the same varied set and it's testable.

This is intentionally dependency-free: it keeps the auto-poster running even when
an AI API key is missing or out of credit. (An AI writer can be layered on later.)
"""
from __future__ import annotations

# {city} = business city, {kw} = a keyword, {biz} = business name.
_TEMPLATES = [
    "{kw} isn't optional for {city} small businesses anymore. {biz} keeps your team protected with 24/7 monitoring, automatic patching, and tested backups. Book a free 15-minute check.",
    "Did you know 60% of small businesses that suffer a cyberattack close within 6 months? Don't be a statistic, {city}. {biz} delivers enterprise-grade {kw} at a small-business price.",
    "Quick tip: enable multi-factor authentication on every account today. It blocks 99% of automated attacks. Need help rolling out {kw} across your {city} office? {biz} has you covered.",
    "Ransomware doesn't take holidays. {biz} watches your {city} network around the clock so you can focus on running your business. Ask us about managed {kw}.",
    "Is your {city} business still relying on 'set it and forget it' IT? Modern threats need modern {kw}. {biz} monitors, patches, and backs up — automatically.",
    "Patch Tuesday came and went. Are all your machines actually updated? {biz} auto-patches every endpoint for {city} businesses, so nothing slips through. That's real {kw}.",
    "Your data is your business. {biz} runs tested, off-site backups for {city} companies — so a failed drive or ransomware hit is a hiccup, not a catastrophe. Let's talk {kw}.",
    "Cyber insurance now requires MFA, EDR, and backups. Not sure you qualify? {biz} gets {city} businesses compliant and audit-ready with managed {kw}.",
    "Slow computers cost your team hours every week. {biz} proactively tunes and monitors every {city} endpoint — faster machines, fewer tickets, better {kw}.",
    "New year, new threats. Start {city} strong with a free security assessment from {biz}: we'll show you exactly where your {kw} gaps are — no jargon, no pressure.",
    "Phishing emails are getting scary-good. Train your team and lock down your inbox. {biz} layers email security + awareness training for {city} businesses. Serious about {kw}? Let's talk.",
    "One dead server shouldn't stop your whole {city} office. {biz} builds resilient, monitored IT with real {kw} — so downtime is rare and short. Free consult available.",
]

_DEFAULT_KEYWORDS = ["managed IT", "cybersecurity", "data backup", "IT support",
                     "network security", "endpoint protection"]


def generate_ai_drafts(count: int, *, city: str = "", keywords: list[str] | None = None,
                       biz: str = "BVTech", cta_url: str = "", start: int = 0) -> list[dict]:
    """Claude-written posts when AI is connected; otherwise the template engine.
    Always returns exactly `count` drafts (tops up from templates if AI returns
    fewer), so the caller never has to handle a short/failed batch."""
    from . import ai
    count = max(1, min(count, 52))
    kws = [k.strip() for k in (keywords or []) if k.strip()] or _DEFAULT_KEYWORDS
    city = (city or "our area").strip()
    biz = (biz or "BVTech").strip()
    if not ai.enabled():
        return generate_drafts(count, city=city, keywords=kws, biz=biz, cta_url=cta_url, start=start)
    system = ("You are a senior marketing copywriter for a managed IT & security "
              "provider (MSP). Write posts that are specific, credible, and locally "
              "relevant — no fluff, no hashtag spam.")
    prompt = (f"Write {count} DISTINCT social posts for {biz}, an MSP serving {city}. "
              f"Naturally weave in these themes/keywords across the set: {', '.join(kws)}. "
              "Each post: under 500 characters, a strong first line, a concrete value or "
              "tip, and a soft call-to-action. Separate every post with a line containing "
              "only %%% and output nothing else.")
    try:
        text = ai.complete(system, prompt, smart=False, max_tokens=1600)
    except ai.AIError:
        return generate_drafts(count, city=city, keywords=kws, biz=biz, cta_url=cta_url, start=start)
    parts = [p.strip() for p in text.split("%%%") if p.strip()][:count]
    drafts = [{"body": (p + (f"\n\n👉 {cta_url}" if cta_url else "")),
               "link": (cta_url or None)} for p in parts]
    if len(drafts) < count:   # top up if Claude returned fewer than asked
        drafts += generate_drafts(count - len(drafts), city=city, keywords=kws, biz=biz,
                                  cta_url=cta_url, start=start + len(drafts))
    return drafts


def generate_drafts(count: int, *, city: str = "", keywords: list[str] | None = None,
                    biz: str = "BVTech", cta_url: str = "", start: int = 0) -> list[dict]:
    """Return `count` varied, SEO-woven post drafts as {body, link}. Deterministic:
    rotates templates + keywords by index (offset by `start` so repeated calls can
    continue the rotation instead of repeating)."""
    count = max(1, min(count, 52))
    city = (city or "your area").strip()
    kws = [k.strip() for k in (keywords or []) if k.strip()] or _DEFAULT_KEYWORDS
    biz = (biz or "BVTech").strip()
    out = []
    for i in range(start, start + count):
        tmpl = _TEMPLATES[i % len(_TEMPLATES)]
        kw = kws[i % len(kws)]
        body = tmpl.format(city=city, kw=kw, biz=biz)
        if cta_url:
            body = f"{body}\n\n👉 {cta_url}"
        out.append({"body": body, "link": (cta_url or None)})
    return out
