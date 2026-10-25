"""Content moderation for anything a human posts on BVTech (v1.103).

BVTech Answers and any other user-generated content must pass through `check()`
before it is stored or shown. The policy, per the owner: keep it clean, keep it
on-topic (tech/IT/business/learning), and protect the brand. This filter blocks,
decisively and server-side:

  * profanity and slurs (incl. common obfuscations: f*ck, sh1t, f u c k, f.u.c.k)
  * politics and other off-topic hot-button content
  * hate / harassment / threats / self-harm encouragement
  * spam (too many links, promo phrases, gibberish, shouting, repetition)
  * contact-info fishing (emails, phone numbers, "DM me on telegram", …)

Design notes:
  * Pure functions, no I/O — trivial to unit-test exhaustively, and it can run at
    the edge or in the app.
  * Normalization defeats common evasion: unicode NFKC, zero-width strip, leet
    de-substitution, repeat collapsing, and separator removal between letters.
  * It errs toward blocking on strong signals; clean text passes untouched. It is
    a filter, not a human — borderline-but-clean content is allowed (the owner
    chose auto-publish-clean), and the worst stuff never gets through.
  * There is NO automated posting anywhere: this only ever gates real human input.
"""
from __future__ import annotations

import re
import unicodedata

# --- strong profanity + slurs (word-stems; matched on normalized text) --------
# A blocklist for a family-friendly site. Kept compact; obfuscations are handled
# by normalization, so we don't need every spelling variant here.
_PROFANITY = [
    "fuck", "shit", "bitch", "bastard", "asshole", "dickhead", "cock", "pussy",
    "cunt", "whore", "slut", "motherfucker", "wanker", "bollocks", "twat",
    "jackass", "dumbass", "jerkoff", "goddamn", "bullshit", "crap",
]
# Slurs and hate terms — zero tolerance. Stems only; normalization catches tricks.
_SLURS = [
    "nigger", "nigga", "faggot", "fag", "retard", "retarded", "spic", "kike",
    "chink", "gook", "wetback", "tranny", "coon", "dyke", "beaner", "raghead",
    "paki", "sandnigger", "jiggaboo", "nazi",
]
# Harassment / threats / self-harm encouragement.
_ABUSE = [
    r"kill yourself", r"\bkys\b", r"kill u", r"neck yourself", r"go die",
    r"hope you die", r"i will kill", r"i'?ll kill", r"you should die",
    r"end yourself", r"drink bleach", r"commit suicide",
]
# Politics / off-topic hot buttons (this is a tech community, not a soapbox).
_POLITICS = [
    "trump", "biden", "harris", "obama", "kamala", "desantis", "vance", "newsom",
    "democrat", "republican", "liberal", "conservative", "leftist", "rightwing",
    "right wing", "maga", "antifa", "gop", "election", "voter", "ballot",
    "abortion", "pro life", "pro choice", "immigration", "immigrant", "deport",
    "gun control", "second amendment", "2nd amendment", "vaccine mandate",
    "transgender", "lgbtq politics", "palestine", "israel", "gaza", "hamas",
    "zionist", "ukraine war", "putin", "communist", "socialism", "fascist",
    "critical race", "woke", "blm", "defund",
]
# Spammy promotional phrases.
_SPAM_PHRASES = [
    "make money", "earn money", "work from home", "click here", "buy now",
    "free money", "free gift", "act now", "limited time", "100% free",
    "crypto", "bitcoin", "forex", "casino", "betting", "viagra", "cialis",
    "weight loss", "get rich", "investment opportunity", "double your",
    "nigerian prince", "wire transfer", "gift card", "promo code", "discount code",
    "follow me", "subscribe to my", "check out my channel", "join my",
    "dm me", "message me on", "contact me on", "hit me up", "telegram", "whatsapp",
    "onlyfans", "cashapp", "venmo me", "paypal me",
]

# Contact info patterns (keep personal contact out of a public board).
_EMAIL = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", re.I)
_PHONE = re.compile(r"(?:\+?\d[\s.-]?){7,}\d")
_URL = re.compile(r"\b(?:https?://|www\.)\S+|\b[a-z0-9-]+\.(?:com|net|org|io|xyz|ru|cn|info|biz|top|link|shop|store)\b", re.I)

_ZW = dict.fromkeys(map(ord, "​‌‍‎‏﻿­⁠"), None)
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t",
                       "8": "b", "9": "g", "@": "a", "$": "s", "!": "i", "|": "i"})


def normalize(text: str) -> str:
    """Fold text so obfuscations collapse onto their plain form."""
    t = unicodedata.normalize("NFKC", text or "").translate(_ZW).lower()
    t = t.translate(_LEET)
    t = re.sub(r"(.)\1{2,}", r"\1", t)                 # waaay -> way, !!! -> !
    t = t.replace("ph", "f")                           # phuck -> fuck (matching only)
    t = t.replace("_", " ")                            # x_nigger_x -> boundaries work
    return t


def _despace(text: str) -> str:
    """Remove separators BETWEEN single letters so 'f u c k' / 'f.u.c.k' collapse,
    without welding ordinary words together."""
    return re.sub(r"\b(\w(?:[\W_]+\w\b){2,})", lambda m: re.sub(r"[\W_]+", "", m.group(0)), text)


_VOWELS = set("aeiou")


def _fuzzy(word: str) -> str:
    """A pattern for `word` that tolerates separators between characters
    (f.u.c.k, f u c k, f-u-c-k) and a MASKED vowel (f*ck, sh!t, b!tch). A vowel
    slot must be FILLED — by the vowel or a punctuation mask — never empty, so
    'coon' can't collapse to 'con' and false-match 'configure'."""
    parts = []
    for ch in word:
        if ch in _VOWELS:
            parts.append("(?:" + ch + r"|[^\w\s])")   # the vowel OR one mask char
        else:
            parts.append(re.escape(ch))
    return r"\b" + r"[\W_]*".join(parts)


def _hits(words: list[str], norm: str, despaced: str) -> list[str]:
    out = []
    for w in words:
        pat = _fuzzy(w) if w.isalpha() else w
        if re.search(pat, norm) or re.search(pat, despaced):
            out.append(w)
    return out


def check(text: str, *, kind: str = "post", max_urls: int = 1) -> dict:
    """Moderate a piece of user text. Returns:
        {ok, reasons:[...], categories:[...], severity:"clean|block"}
    ok=False means DO NOT publish; `reasons` is safe to show the user."""
    raw = (text or "").strip()
    norm = normalize(raw)
    desp = normalize(_despace(raw))
    reasons: list[str] = []
    cats: list[str] = []

    def flag(cat, reason):
        if cat not in cats:
            cats.append(cat)
        reasons.append(reason)

    if _hits(_SLURS, norm, desp):
        flag("hate", "Slurs and hate speech aren't allowed here.")
    if _hits(_ABUSE, norm, desp):
        flag("abuse", "Harassment, threats and self-harm content aren't allowed.")
    if _hits(_PROFANITY, norm, desp):
        flag("profanity", "Please keep it clean — no profanity.")
    if _hits(_POLITICS, norm, desp):
        flag("politics", "Let's keep it to tech, not politics or hot-button topics.")
    if _hits(_SPAM_PHRASES, norm, desp):
        flag("spam", "That reads like spam or self-promotion.")

    # contact info
    if _EMAIL.search(raw):
        flag("contact", "Please don't post email addresses — keep personal contact off the board.")
    if _PHONE.search(re.sub(r"\s+", " ", raw)) and kind != "none":
        flag("contact", "Please don't post phone numbers.")

    # spam heuristics
    urls = _URL.findall(raw)
    if len(urls) > max_urls:
        flag("spam", f"Too many links (max {max_urls}).")
    letters = re.sub(r"[^a-z]", "", raw.lower())
    caps = re.sub(r"[^A-Z]", "", raw)
    if len(letters) >= 15 and len(caps) / max(1, len(re.sub(r"[^a-zA-Z]", "", raw))) > 0.7:
        flag("spam", "Please don't SHOUT in all caps.")
    # gibberish: a long run with almost no vowels, or one word repeated
    words = re.findall(r"[a-z]+", norm)
    if words:
        longest = max(words, key=len)
        if len(longest) >= 12 and not re.search(r"[aeiou]", longest):
            flag("spam", "That looks like gibberish or a keyboard mash.")
        for tok in words:
            if len(tok) >= 8 and len(set(tok)) / len(tok) < 0.35:
                flag("spam", "That looks like gibberish or a keyboard mash.")
                break
        if re.search(r"(qwerty|asdfgh|zxcvbn|qazwsx|wasd){1,}", norm):
            flag("spam", "That looks like a keyboard mash.")
        if len(words) >= 6 and len(set(words)) <= 2:
            flag("spam", "Please don't repeat the same words.")

    ok = not reasons
    return {"ok": ok, "reasons": reasons, "categories": cats,
            "severity": "clean" if ok else "block"}


def is_clean(text: str, **kw) -> bool:
    return check(text, **kw)["ok"]
