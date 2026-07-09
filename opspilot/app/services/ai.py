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
from urllib import error, request as urlrequest

from ..core.config import get_settings

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


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
        detail = e.read().decode(errors="replace")[:300]
        if e.code == 401:
            raise AIError("Claude rejected the API key (401) — check ANTHROPIC_API_KEY.")
        if e.code == 429:
            raise AIError("Claude rate/credit limit hit (429) — check your Anthropic plan balance.")
        raise AIError(f"Claude API error (HTTP {e.code}): {detail}")
    except Exception as e:  # noqa: BLE001
        raise AIError(f"Claude request failed: {e}")
    # Messages API returns content as a list of blocks; concatenate the text ones.
    parts = [b.get("text", "") for b in (data.get("content") or []) if b.get("type") == "text"]
    text = "".join(parts).strip()
    if not text:
        raise AIError("Claude returned an empty response.")
    return text


# Tests / offline runs override _CALLER to avoid real network I/O.
_CALLER = _http_complete


def complete(system: str, user: str, *, smart: bool = False, max_tokens: int = 1024) -> str:
    """Run a single-shot completion. `smart=True` uses the heavier model."""
    s = get_settings()
    model = s.AI_MODEL_SMART if smart else s.AI_MODEL
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
        detail = e.read().decode(errors="replace")[:300]
        if e.code == 401:
            raise AIError("Claude rejected the API key (401) — check ANTHROPIC_API_KEY.")
        if e.code == 429:
            raise AIError("Claude rate/credit limit hit (429) — check your Anthropic plan balance.")
        raise AIError(f"Claude API error (HTTP {e.code}): {detail}")
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
