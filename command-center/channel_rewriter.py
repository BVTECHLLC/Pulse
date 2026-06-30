#!/usr/bin/env python3
"""
BVTech — Channel Content Rewriter  v32.0
==============================================================

When Super Posting targets "All 4 Channels", one master article
gets written, then this module does a second-pass Claude call per
channel to rewrite it into that channel's voice. Stops all four
channels from looking like clones, which Google penalizes and
which feels spammy to humans.

CHANNEL VOICES
--------------
bvtech     Corporate / authoritative. Third person. Deep detail.
           Full article length. Formal tone.
jp         First-person. Personal stories. Conversational. "I",
           "my team", "we've seen". Same length-ish as master.
linkedin   Hook-driven. ~1200 chars max. Opens with a bold claim
           or contrarian take. No HTML, plain text with line
           breaks. 3-5 short paragraphs. Ends with a question to
           drive comments.
gbp        ~300 chars max. One sentence hook + one sentence value
           + CTA. No markdown, no links in body (GBP has a
           separate CTA button). Plain text only.

USAGE
-----
    from channel_rewriter import rewrite_for_channel

    master_html = "... the full BVTech article ..."
    li_text, err = rewrite_for_channel(
        master_html=master_html,
        master_title="5 Cybersecurity Wins for Houston SMBs",
        channel="linkedin",
        api_key=cfg["anthropic_key"],
    )

FALLBACK BEHAVIOR
-----------------
If the Anthropic API call fails (no key, rate limit, network
error), rewrite_for_channel returns a SAFE FALLBACK rather than
failing the whole post. For LinkedIn this means a trimmed version
of the first paragraph of the master; for GBP it means the meta
description truncated to 280 chars. This keeps Super Posting
working even if Claude is unreachable.
"""

import json
import re
import time
from typing import Callable, Optional, Tuple

try:
    import requests
except ImportError:
    raise ImportError(
        "channel_rewriter requires the 'requests' package. "
        "Install with: pip install requests"
    )


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-20250514"


# ============================================================
# CHANNEL CONFIGS
# ============================================================
CHANNEL_CONFIGS = {
    "bvtech": {
        "label": "BVTech.org (corporate)",
        "max_tokens": 4096,
        "max_output_chars": None,  # no hard limit — full article
        "output_format": "html",
        "voice": "corporate_authority",
    },
    "jp": {
        "label": "JordanPolasek.com (first-person)",
        "max_tokens": 4096,
        "max_output_chars": None,
        "output_format": "html",
        "voice": "first_person_personal",
    },
    "linkedin": {
        "label": "LinkedIn post",
        "max_tokens": 1024,
        "max_output_chars": 1200,
        "output_format": "plain_text",
        "voice": "hook_driven_short",
    },
    "gbp": {
        "label": "Google Business Profile post",
        "max_tokens": 512,
        "max_output_chars": 300,
        "output_format": "plain_text",
        "voice": "ultra_short_cta",
    },
}


# ============================================================
# PROMPT BUILDERS
# ============================================================
def _build_prompt(master_html: str, master_title: str,
                  master_focus_keyword: str, channel: str,
                  canonical_url: str = "") -> str:
    """Build the rewrite prompt for a specific channel."""
    cfg = CHANNEL_CONFIGS[channel]

    # Strip HTML tags for non-HTML channels to keep the model focused
    master_text = master_html
    if cfg["output_format"] == "plain_text":
        master_text = re.sub(r"<[^>]+>", " ", master_html)
        master_text = re.sub(r"\s+", " ", master_text).strip()
        # Trim master to ~3000 chars to keep input small for short outputs
        if len(master_text) > 3000:
            master_text = master_text[:3000] + "..."

    if channel == "bvtech":
        return f"""You are rewriting an article for BVTech.org, an El Campo, Texas managed IT services provider serving San Antonio, Houston, and Austin SMBs. The tone is corporate but approachable — you are authoritative, data-driven, and reference real business outcomes. Third person. Never use "I" or "we" unless it's clearly the company voice ("BVTech recommends...", "Our team has seen...").

Rewrite the article below for BVTech.org. Keep it at roughly the same length and structure. Preserve all H2/H3 headings, lists, and FAQ sections. Do NOT invent statistics or cite sources that weren't in the original. Return ONLY the HTML of the rewritten article — no commentary, no code fences, no wrapper <html> tags, just the body content.

Original title: {master_title}
Focus keyword: {master_focus_keyword}

Original article:
{master_text}

Return ONLY the rewritten HTML body content."""

    if channel == "jp":
        return f"""You are rewriting an article for JordanPolasek.com, the personal site of Jordan Polasek, founder of BVTech LLC. The tone is first-person, conversational, and personal. Uses "I", "my team", "we've seen". Tells stories from real MSP work without inventing specifics. Less corporate than BVTech.org — more like a thoughtful peer sharing what he's learned.

Rewrite the article below in Jordan's first-person voice. Same length range, same topic, same focus keyword. Preserve H2/H3 structure and any FAQ sections but feel free to reframe them as questions Jordan gets asked in person. Do NOT invent statistics or quotes. Return ONLY the HTML body content — no commentary, no code fences.

Original title: {master_title}
Focus keyword: {master_focus_keyword}

Original article:
{master_text}

Return ONLY the rewritten HTML body content."""

    if channel == "linkedin":
        return f"""You are writing a LinkedIn post based on the article below. LinkedIn rewards short, punchy, hook-driven content that starts with a contrarian take or bold claim and ends with a question to drive comments. Plain text only — no markdown, no HTML, no emoji spam (one or two emojis max). Line breaks between short paragraphs for scan-ability.

HARD CONSTRAINTS:
- Maximum 1200 characters TOTAL
- 3-5 short paragraphs
- Opens with a hook (contrarian claim, surprising stat, or provocative question)
- Ends with a question or clear CTA that invites engagement
- Written in Jordan Polasek's first-person voice ("I", "my team")
- Mentions BVTech once or twice but doesn't sound like an ad
- If you reference the full article, end with: "Full breakdown on BVTech.org → {canonical_url or '[link]'}"

Original article title: {master_title}
Original article:
{master_text}

Return ONLY the LinkedIn post text. No preamble, no commentary, no code fences."""

    if channel == "gbp":
        return f"""You are writing a Google Business Profile local post. These are short updates that appear on a business's Google listing in Search and Maps. They must be extremely concise — MAXIMUM 300 CHARACTERS INCLUDING SPACES. GBP already has a separate call-to-action button (added automatically), so do NOT include links in the body text.

Structure:
- Sentence 1: hook or value statement
- Sentence 2 (optional): key detail
- Keep it informational, local, and friendly
- No emoji (GBP strips most of them anyway)
- No markdown

Original article title: {master_title}
Topic: {master_focus_keyword}
Article summary (for context only, not to reproduce verbatim):
{master_text[:800]}

Return ONLY the GBP post text, 300 characters max. No preamble, no commentary, no code fences, no quotes around the output."""

    raise ValueError(f"Unknown channel: {channel}")


# ============================================================
# API CALL
# ============================================================
def _call_anthropic(prompt: str, max_tokens: int, api_key: str,
                    model: str = DEFAULT_MODEL,
                    timeout: int = 60) -> Tuple[Optional[str], Optional[str]]:
    """Make one API call and return (text, error)."""
    if not api_key:
        return None, "no anthropic_key configured"
    try:
        r = requests.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_API_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=timeout,
        )
    except requests.RequestException as e:
        return None, f"network error: {e}"

    if r.status_code != 200:
        body = r.text[:400] if r.text else ""
        return None, f"HTTP {r.status_code}: {body}"

    try:
        data = r.json()
        content = data.get("content", [])
        if not content:
            return None, "empty content array in response"
        # Concatenate all text blocks
        text_parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = "".join(text_parts).strip()
        if not text:
            return None, "no text content in response"
        return text, None
    except (ValueError, KeyError) as e:
        return None, f"response parse error: {e}"


# ============================================================
# OUTPUT POST-PROCESSING
# ============================================================
def _clean_output(text: str, channel: str) -> str:
    """Strip code fences, quotes, and hard-enforce length limits."""
    text = text.strip()

    # Strip markdown code fences if the model wrapped output in them
    if text.startswith("```"):
        lines = text.split("\n")
        if len(lines) > 1:
            lines = lines[1:]  # drop opening fence
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]  # drop closing fence
            text = "\n".join(lines).strip()

    # Strip surrounding quotes (common for short outputs)
    if len(text) > 2 and text[0] in '"\u201c\u201d' and text[-1] in '"\u201c\u201d':
        text = text[1:-1].strip()

    # Hard-enforce length limit for short channels
    cfg = CHANNEL_CONFIGS.get(channel, {})
    max_chars = cfg.get("max_output_chars")
    if max_chars and len(text) > max_chars:
        # Trim at last sentence boundary before the limit if possible
        trimmed = text[:max_chars]
        last_period = max(trimmed.rfind("."), trimmed.rfind("!"),
                           trimmed.rfind("?"))
        if last_period > max_chars * 0.7:
            text = trimmed[:last_period + 1]
        else:
            text = trimmed.rstrip() + "..."

    return text


# ============================================================
# FALLBACK BUILDERS
# ============================================================
def _fallback(master_html: str, master_title: str,
              master_meta_description: str, channel: str,
              canonical_url: str = "") -> str:
    """Safe fallback when the API call fails. Returns something
    usable so the post still goes out.
    """
    # Strip HTML for text-based channels
    plain = re.sub(r"<[^>]+>", " ", master_html)
    plain = re.sub(r"\s+", " ", plain).strip()

    if channel == "bvtech" or channel == "jp":
        return master_html  # use the master as-is

    if channel == "linkedin":
        # First sentence of the article or meta desc, plus a link
        first_chunk = (master_meta_description
                        or plain[:400]).strip()
        sentence_end = max(first_chunk.rfind("."),
                            first_chunk.rfind("!"),
                            first_chunk.rfind("?"))
        if sentence_end > 100:
            first_chunk = first_chunk[:sentence_end + 1]
        li = f"{master_title}\n\n{first_chunk}"
        if canonical_url:
            li += f"\n\nFull breakdown on BVTech.org → {canonical_url}"
        if len(li) > 1200:
            li = li[:1197] + "..."
        return li

    if channel == "gbp":
        text = master_meta_description or master_title
        if len(text) > 280:
            text = text[:277] + "..."
        return text

    return plain[:500]


# ============================================================
# MAIN ENTRY POINT
# ============================================================
def rewrite_for_channel(master_html: str,
                         master_title: str,
                         channel: str,
                         api_key: str = "",
                         master_focus_keyword: str = "",
                         master_meta_description: str = "",
                         canonical_url: str = "",
                         logger: Optional[Callable[[str], None]] = None,
                         model: str = DEFAULT_MODEL,
                         ) -> Tuple[str, Optional[str]]:
    """Rewrite the master article for one target channel.

    Returns (text, error_or_None). On API failure, returns a safe
    fallback as `text` and a non-None error string so the caller
    can log the issue but still publish.
    """
    log = logger or (lambda m: None)

    if channel not in CHANNEL_CONFIGS:
        return master_html, f"unknown channel: {channel}"

    cfg = CHANNEL_CONFIGS[channel]
    log(f"[channel_rewriter] {channel} ({cfg['label']}): starting")

    # BVTech keeps the master as-is — it IS the master voice.
    # Only rewrite for jp/linkedin/gbp.
    if channel == "bvtech":
        log(f"[channel_rewriter] bvtech: using master (no rewrite needed)")
        return master_html, None

    if not api_key:
        fallback = _fallback(master_html, master_title,
                              master_meta_description, channel,
                              canonical_url)
        log(f"[channel_rewriter] {channel}: no api key, using fallback ({len(fallback)} chars)")
        return fallback, "no anthropic_key — used fallback"

    prompt = _build_prompt(master_html, master_title,
                            master_focus_keyword, channel,
                            canonical_url)
    text, err = _call_anthropic(prompt, cfg["max_tokens"], api_key,
                                 model=model)
    if err:
        fallback = _fallback(master_html, master_title,
                              master_meta_description, channel,
                              canonical_url)
        log(f"[channel_rewriter] {channel}: API error ({err}), using fallback")
        return fallback, err

    cleaned = _clean_output(text, channel)
    log(f"[channel_rewriter] {channel}: rewrote {len(cleaned)} chars")
    return cleaned, None


def rewrite_all_channels(master_html: str,
                          master_title: str,
                          api_key: str = "",
                          master_focus_keyword: str = "",
                          master_meta_description: str = "",
                          canonical_url: str = "",
                          logger: Optional[Callable[[str], None]] = None,
                          channels: Optional[list] = None,
                          ) -> dict:
    """Rewrite the master for all requested channels. Returns a
    dict keyed by channel with {"text", "error"} entries.

    Default channels = ["bvtech", "jp", "linkedin", "gbp"].
    """
    channels = channels or ["bvtech", "jp", "linkedin", "gbp"]
    results = {}
    for ch in channels:
        text, err = rewrite_for_channel(
            master_html=master_html,
            master_title=master_title,
            channel=ch,
            api_key=api_key,
            master_focus_keyword=master_focus_keyword,
            master_meta_description=master_meta_description,
            canonical_url=canonical_url,
            logger=logger,
        )
        results[ch] = {"text": text, "error": err}
        # Tiny delay between calls to be polite to the API
        if ch != channels[-1]:
            time.sleep(0.3)
    return results
