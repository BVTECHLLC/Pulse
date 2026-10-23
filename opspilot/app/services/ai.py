"""v0.74 AI service — Claude, baked in.

A thin stdlib client for the Anthropic Messages API used across the portal
(the "Ask Pulse" copilot, ticket-reply drafts, advisories, summaries). The key
comes from the env/secret and is never logged. When no key is set, `enabled()`
is False and callers show a friendly "connect Claude" message instead of failing.

The HTTP call is isolated behind `_CALLER` so every AI feature is testable
offline by swapping in a stub.
"""
from __future__ import annotations

import json
import re
from urllib import error, request as urlrequest

from ..core.config import get_settings

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


def _human_api_error(code: int, body: str) -> str:
    """Turn Anthropic's JSON error body into a sentence a human can act on.
    The raw '{"type":"error","error":{"type":"invalid_request_error","mess...'
    blobs in the UI told the operator nothing."""
    msg = ""
    try:
        import json as _j
        msg = str((_j.loads(body).get("error") or {}).get("message") or "")[:220]
    except Exception:  # noqa: BLE001
        msg = (body or "")[:220]
    low = msg.lower()
    if "credit balance" in low or "billing" in low:
        return ("Claude says your Anthropic credit balance is too low - add credits at "
                "console.anthropic.com -> Settings -> Billing, then posting resumes "
                "automatically on the next tick.")
    if "model" in low and ("not found" in low or "invalid" in low):
        return f"Claude rejected the model name - {msg}"
    if code == 401:
        return "Claude rejected the API key (401) - re-enter it in Connection Center -> Claude."
    if code == 429:
        return ("Claude rate/credit limit hit (429) - it retries automatically; if this "
                "persists, check your plan at console.anthropic.com.")
    if code == 529 or "overloaded" in low:
        return "Claude is temporarily overloaded (529) - retries automatically next tick."
    return f"Claude API error (HTTP {code}): {msg or body[:200]}"


class AIError(Exception):
    pass


# v1.22: the key can come from the VAULT (set in the portal, encrypted at rest)
# or the server env. Cached briefly so enabled() stays cheap on hot paths.
_KEY_CACHE: dict = {"key": None, "ts": 0.0}
_KEY_TTL = 60.0


def _api_key() -> str | None:
    import time as _t
    if _KEY_CACHE["key"] is not None and (_t.monotonic() - _KEY_CACHE["ts"]) < _KEY_TTL:
        return _KEY_CACHE["key"] or None
    key = None
    try:
        from ..core.db import SessionLocal
        from . import secure_config
        db = SessionLocal()
        try:
            conn = secure_config.get_platform(db, "anthropic")
            cfg = (conn.config if conn else None) or {}
            key = secure_config.get_secret(cfg, "api_key")
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        key = None
    key = key or get_settings().ANTHROPIC_API_KEY
    _KEY_CACHE["key"] = key or ""
    _KEY_CACHE["ts"] = _t.monotonic()
    return key


def refresh_key_cache() -> None:
    """Call after saving a new key so it takes effect immediately."""
    _KEY_CACHE["key"] = None
    _KEY_CACHE["ts"] = 0.0


def key_source() -> str | None:
    """'vault' | 'env' | None — for the Connection Center (never the value)."""
    try:
        from ..core.db import SessionLocal
        from . import secure_config
        db = SessionLocal()
        try:
            conn = secure_config.get_platform(db, "anthropic")
            cfg = (conn.config if conn else None) or {}
            if secure_config.get_secret(cfg, "api_key"):
                return "vault"
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        pass
    return "env" if get_settings().ANTHROPIC_API_KEY else None


def enabled() -> bool:
    return bool(_api_key())


def parse_sections(raw: str) -> dict | None:
    """Parse the delimited article format:

        TITLE: <headline>
        EXCERPT: <one line>
        HTML:
        <article body html...>

    This exists because asking models for the article as JSON kept failing in
    the wild: HTML is full of double quotes (class="meta", href="...") and any
    unescaped one makes the JSON unparseable — no repair can fix it reliably.
    A line-delimited format has NO escaping rules, so it cannot break that way."""
    import re as _re
    if not raw:
        return None
    s = _re.sub(r"```[a-z]*", "", str(raw)).strip()
    m_t = _re.search(r"^[ \t>*#]*TITLE:\s*(.+)$", s, _re.M | _re.I)
    m_h = _re.search(r"^[ \t>*#]*HTML:\s*\n?(.*)\Z", s, _re.M | _re.S | _re.I)
    if not (m_t and m_h):
        return None
    m_e = _re.search(r"^[ \t>*#]*EXCERPT:\s*(.+)$", s, _re.M | _re.I)
    html_body = m_h.group(1).strip()
    if len(html_body) < 100:
        return None
    return {"title": m_t.group(1).strip()[:200],
            "excerpt": (m_e.group(1).strip() if m_e else "")[:300],
            "html": html_body}


def parse_article(raw: str) -> dict | None:
    """Sections format first (quote-proof), JSON fallback (models sometimes
    return JSON regardless of instructions)."""
    out = parse_sections(raw)
    if out:
        return out
    out = parse_json_object(raw)
    if out and out.get("title") and out.get("html"):
        return out
    return None


def parse_json_object(raw: str) -> dict | None:
    """Best-effort extraction of ONE JSON object from model output.

    Models wrap JSON in prose or ```json fences, emit literal newlines inside
    string values (invalid strict JSON), and get truncated at the token limit
    mid-string. All of those made the naive `json.loads(raw[{...}])` blow up
    ("Claude returned an unparseable article"). This handles each case; returns
    None only when there's no salvageable object at all."""
    import json as _json
    import re as _re
    if not raw:
        return None
    s = _re.sub(r"```(?:json)?", "", str(raw)).strip()
    start = s.find("{")
    if start < 0:
        return None
    s = s[start:]
    end = s.rfind("}")
    candidates = ([s[:end + 1]] if end > 0 else []) + [s]
    for cand in candidates:
        try:
            out = _json.loads(cand, strict=False)   # strict=False: literal \n in strings OK
            if isinstance(out, dict):
                return out
        except Exception:  # noqa: BLE001
            continue
    # Truncated output: try closing an open string, then balance brackets/braces.
    for suffix in ('"', ""):
        t = s + suffix
        t += "]" * max(0, t.count("[") - t.count("]"))
        t += "}" * max(0, t.count("{") - t.count("}"))
        try:
            out = _json.loads(t, strict=False)
            if isinstance(out, dict):
                return out
        except Exception:  # noqa: BLE001
            continue
    return None


def _http_complete(system: str, user: str, *, model: str, max_tokens: int) -> str:
    key = _api_key()
    if not key:
        raise AIError("Claude is not connected — paste your Anthropic API key in "
                      "Settings → Connection Center (or set ANTHROPIC_API_KEY).")
    payload = {"model": model, "max_tokens": max_tokens, "system": system,
               "messages": [{"role": "user", "content": user}]}
    req = urlrequest.Request(
        ANTHROPIC_URL, data=json.dumps(payload).encode(), method="POST",
        headers={"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION,
                 "content-type": "application/json"})
    try:
        with urlrequest.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode())
    except error.HTTPError as e:
        raise AIError(_human_api_error(e.code, e.read().decode(errors="replace")[:400]))
    except Exception as e:  # noqa: BLE001
        raise AIError(f"Claude request failed: {e}")
    # Messages API returns content as a list of blocks; concatenate the text ones.
    parts = [b.get("text", "") for b in (data.get("content") or []) if b.get("type") == "text"]
    text = "".join(parts).strip()
    if not text:
        raise AIError("Claude returned an empty response.")
    return text


def free_llm_enabled() -> bool:
    """A free (non-Claude) LLM is configured — used to spare paid tokens."""
    return bool(get_settings().free_llm_enabled)


# v1.98 SELF-HEALING free model + v1.101 PROVIDER REDUNDANCY. Groq retires
# models on a schedule; when the configured one disappeared every call failed and
# all three sites quietly fell back to their evergreen posts for weeks. Now: on a
# model error ask the provider which models exist and switch; if a provider is
# down entirely, try the next configured one (FREE_LLM2_*, FREE_LLM3_*).
_FREE_MODEL_PREFS = ("llama-3.3-70b-versatile", "openai/gpt-oss-120b",
                     "meta-llama/llama-4-maverick-17b-128e-instruct",
                     "moonshotai/kimi-k2-instruct", "qwen/qwen3-32b",
                     "gemini-2.5-flash", "gemini-2.0-flash",
                     "openai/gpt-oss-20b", "llama-3.1-8b-instant")
_free_model_override: str | None = None          # primary provider's switched model
_overrides: dict = {}                             # base -> switched model (backups)
_UA = "BVTech-OpsPilot/1.0 (+https://bvtech.org)"


def _providers() -> list[dict]:
    s = get_settings()
    out = []
    for base, key, model in ((s.FREE_LLM_BASE, s.FREE_LLM_KEY, s.FREE_LLM_MODEL),
                             (s.FREE_LLM2_BASE, s.FREE_LLM2_KEY, s.FREE_LLM2_MODEL),
                             (s.FREE_LLM3_BASE, s.FREE_LLM3_KEY, s.FREE_LLM3_MODEL)):
        if key and base:
            out.append({"base": base.rstrip("/"), "key": key, "model": model or ""})
    return out


def _free_models(prov: dict | None = None) -> list[str]:
    """Model ids a free provider currently serves (OpenAI-compatible)."""
    prov = prov or _providers()[0]
    req = urlrequest.Request(prov["base"] + "/models", method="GET",
                             headers={"authorization": f"Bearer {prov['key']}",
                                      "user-agent": _UA})
    with urlrequest.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode())
    return [m.get("id", "").removeprefix("models/") for m in (data.get("data") or [])
            if m.get("id")]


def _pick_free_model(avoid: str, prov: dict | None = None) -> str | None:
    prov = prov or _providers()[0]
    ids = _free_models(prov)
    for m in (prov.get("model"),) + _FREE_MODEL_PREFS:
        if m and m in ids and m != avoid:
            return m
    for m in ids:                                 # any general chat model
        if m != avoid and re.search(r"llama|gpt-oss|qwen|kimi|mistral|gemma|gemini", m, re.I) \
                and not re.search(r"guard|whisper|tts|embed|vision|prompt|image|audio", m, re.I):
            return m
    return None


def _free_post(model: str, system: str, user: str, max_tokens: int,
               prov: dict | None = None) -> dict:
    prov = prov or _providers()[0]
    payload = {"model": model, "max_tokens": max_tokens,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    req = urlrequest.Request(
        prov["base"] + "/chat/completions", data=json.dumps(payload).encode(), method="POST",
        # A real User-Agent is REQUIRED: Groq (and most free LLM APIs) sit behind
        # Cloudflare, which blocks urllib's default "Python-urllib/x.y" signature
        # with HTTP 403 error 1010. Any normal UA sails through.
        headers={"authorization": f"Bearer {prov['key']}",
                 "content-type": "application/json", "user-agent": _UA})
    with urlrequest.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


def _complete_one(prov: dict, primary: bool, system: str, user: str, max_tokens: int) -> str:
    """One provider, with model auto-switch and one rate-limit retry."""
    global _free_model_override
    import time as _time
    use = (_free_model_override if primary else _overrides.get(prov["base"])) or prov["model"]
    if not use:
        try:
            use = _pick_free_model("", prov) or ""
        except Exception:  # noqa: BLE001
            use = ""
    data = None
    for attempt in range(3):
        try:
            data = _free_post(use, system, user, max_tokens, prov)
            break
        except error.HTTPError as e:
            body = e.read().decode(errors="replace")[:400]
            if attempt < 2 and e.code in (400, 404) and re.search(
                    r"model|decommission|deprecat|not.?found|does not exist", body, re.I):
                try:
                    alt = _pick_free_model(avoid=use, prov=prov)
                except Exception:  # noqa: BLE001
                    alt = None
                if alt:
                    use = alt
                    if primary:
                        _free_model_override = alt
                    else:
                        _overrides[prov["base"]] = alt
                    continue
            if attempt < 2 and e.code in (413, 429):
                if e.code == 413 or "token" in body.lower():
                    max_tokens = max(1200, max_tokens // 2)
                try:
                    wait = float(e.headers.get("retry-after") or 5)
                except (TypeError, ValueError):
                    wait = 5
                _time.sleep(min(wait, 20))
                continue
            raise AIError(f"HTTP {e.code} ({use} @ {prov['base']}): {body[:160]}")
        except AIError:
            raise
        except Exception as e:  # noqa: BLE001
            raise AIError(f"request failed ({use} @ {prov['base']}): {e}")
    if data is None:
        raise AIError(f"no answer after retries ({use} @ {prov['base']})")
    try:
        text = (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        raise AIError(f"unexpected reply shape ({prov['base']})")
    # Reasoning models can prefix hidden thinking; never publish it.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I).strip()
    if not text:
        raise AIError(f"empty reply ({use} @ {prov['base']})")
    return text


def _free_llm_complete(system: str, user: str, *, model: str, max_tokens: int) -> str:
    """Single-shot completion across the configured free providers, in order.
    `model` is ignored in favor of each provider's configured model. Raises
    AIError (every provider's reason) so the caller can use its fallback."""
    provs = _providers()
    if not provs:
        raise AIError("no free LLM configured")
    errs = []
    for i, prov in enumerate(provs):
        try:
            return _complete_one(prov, i == 0, system, user, max_tokens)
        except AIError as e:
            errs.append(str(e))
    raise AIError("free LLM failed on every provider: " + " | ".join(errs)[:500])


def free_llm_selftest() -> dict:
    """One-line health check for the box: each provider's key, models on offer
    and a real tiny call."""
    s = get_settings()
    out = {"free_llm_only": s.FREE_LLM_ONLY, "providers": []}
    provs = _providers()
    if not provs:
        return {**out, "ok": False, "error": "FREE_LLM_KEY is not set"}
    for i, prov in enumerate(provs):
        r = {"base": prov["base"], "configured_model": prov["model"]}
        try:
            ids = _free_models(prov)
            r["configured_model_available"] = prov["model"] in ids
            r["models"] = ids[:8]
        except Exception as e:  # noqa: BLE001
            r["models_error"] = str(e)[:160]
        try:
            r["reply"] = _complete_one(prov, i == 0, "Reply with exactly the word OK.",
                                       "ping", 20)[:40]
            r["ok"] = True
            r["model_used"] = ((_free_model_override if i == 0 else _overrides.get(prov["base"]))
                               or prov["model"])
        except AIError as e:
            r.update(ok=False, error=str(e)[:240])
        out["providers"].append(r)
    out["ok"] = any(p.get("ok") for p in out["providers"])
    out["redundancy"] = sum(1 for p in out["providers"] if p.get("ok"))
    if out["ok"]:
        out["model_used"] = next(p.get("model_used") for p in out["providers"] if p.get("ok"))
    else:
        out["error"] = "; ".join(p.get("error", "") for p in out["providers"])[:300]
    return out


# Tests / offline runs override _CALLER to avoid real network I/O.
_CALLER = _http_complete
# Tests override this too; the real one is chosen per-call in complete().
_FREE_CALLER = _free_llm_complete


def complete(system: str, user: str, *, smart: bool = False, max_tokens: int = 1024) -> str:
    """Run a single-shot completion. `smart=True` uses the heavier model.

    v1.50: when a FREE LLM is configured (Groq/OpenRouter/etc.), single-shot
    content runs on it instead of paid Claude tokens. If the free model fails
    AND Claude is connected, we fall through to Claude; if neither works the
    AIError propagates so the caller can use its deterministic composer."""
    s = get_settings()
    model = s.AI_MODEL_SMART if smart else s.AI_MODEL
    if s.free_llm_enabled:
        try:
            return _FREE_CALLER(system, user, model=model, max_tokens=max_tokens)
        except AIError:
            # FREE_LLM_ONLY: never spend paid Claude credit on the automated
            # pipeline — let the AIError propagate so the caller uses its
            # deterministic composer. (Also raise if Claude simply isn't set up.)
            if s.FREE_LLM_ONLY or not s.ai_enabled:
                raise
            # free model down but Claude available -> use Claude this once
    return _CALLER(system, user, model=model, max_tokens=max_tokens)


def _http_messages(system: str, messages: list, tools: list, *, model: str,
                   max_tokens: int) -> dict:
    """One turn of the Messages API WITH tools. Returns the raw response dict
    (content blocks + stop_reason) so the caller can run a tool-use loop."""
    key = _api_key()
    if not key:
        raise AIError("Claude is not connected — paste your Anthropic API key in "
                      "Settings → Connection Center (or set ANTHROPIC_API_KEY).")
    payload = {"model": model, "max_tokens": max_tokens, "system": system,
               "messages": messages, "tools": tools}
    req = urlrequest.Request(
        ANTHROPIC_URL, data=json.dumps(payload).encode(), method="POST",
        headers={"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION,
                 "content-type": "application/json"})
    try:
        with urlrequest.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode())
    except error.HTTPError as e:
        raise AIError(_human_api_error(e.code, e.read().decode(errors="replace")[:400]))
    except AIError:
        raise
    except Exception as e:  # noqa: BLE001
        raise AIError(f"Claude request failed: {e}")


# Tests override _TOOL_CALLER to script a tool-use conversation offline.
_TOOL_CALLER = _http_messages


def messages_call(system: str, messages: list, tools: list, *, smart: bool = False,
                  max_tokens: int = 1500) -> dict:
    """Tool-enabled turn (for the agentic Copilot). Returns the raw response."""
    s = get_settings()
    model = s.AI_MODEL_SMART if smart else s.AI_MODEL
    return _TOOL_CALLER(system, messages, tools, model=model, max_tokens=max_tokens)
