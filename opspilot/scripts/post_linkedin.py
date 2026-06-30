#!/usr/bin/env python3
"""Post the day's article to LinkedIn (as Jordan).

Reads `linkedin_access_token` + `linkedin_person_urn` from /etc/bvtech/agent.env
(JSON) and publishes a text share (optionally linking the article). Called by the
daily runners after a post is published. Best-effort: if the token is missing or
expired, it prints a clear message and exits non-zero so the caller can skip on.

Usage:
  python3 scripts/post_linkedin.py --from-json automation/out/published-2026-06-30.json
  python3 scripts/post_linkedin.py --text "..." --url "https://bvtech.org/blog/..."

The post text priority: explicit --text > the JSON's "linkedin" field >
a caption built from the JSON's title. The article URL (if any) is appended /
attached so followers can click through.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib import error, request

AGENT_ENV = os.environ.get("BVTECH_AGENT_ENV", "/etc/bvtech/agent.env")
API = "https://api.linkedin.com/v2/ugcPosts"
MAX_LEN = 2900   # LinkedIn hard limit is 3000; leave headroom for the URL


def _load_creds() -> tuple[str, str]:
    """token, person_urn — from env first, then the JSON agent.env."""
    tok = (os.environ.get("LINKEDIN_ACCESS_TOKEN") or "").strip()
    urn = (os.environ.get("LINKEDIN_PERSON_URN") or "").strip()
    if not (tok and urn) and Path(AGENT_ENV).is_file():
        try:
            with open(AGENT_ENV, encoding="utf-8-sig") as fh:
                d = {str(k).lower(): v for k, v in json.load(fh).items()}
            tok = tok or str(d.get("linkedin_access_token", "")).strip()
            urn = urn or str(d.get("linkedin_person_urn", "")).strip()
        except Exception as e:  # noqa: BLE001
            print(f"warn: could not read {AGENT_ENV}: {e}", file=sys.stderr)
    return tok, urn


def _caption(args) -> tuple[str, str]:
    """Returns (text, url)."""
    text, url = (args.text or ""), (args.url or "")
    if args.from_json:
        try:
            data = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"error: cannot read {args.from_json}: {e}", file=sys.stderr)
            sys.exit(2)
        url = url or data.get("url", "")
        if not text:
            text = (data.get("linkedin") or "").strip()
        if not text:   # fall back to a simple caption from the title
            title = data.get("title", "New post")
            text = f"{title}\n\nNew on the blog — full read below. 👇"
    if not text:
        print("error: nothing to post (need --text or --from-json)", file=sys.stderr)
        sys.exit(2)
    return text, url


def _normalize_urn(urn: str) -> str:
    return urn if urn.startswith("urn:li:") else f"urn:li:person:{urn}"


def post(token: str, person_urn: str, text: str, url: str = "") -> int:
    body = text if not url else f"{text}\n\n{url}"
    body = body[:MAX_LEN]
    share: dict = {
        "shareCommentary": {"text": body},
        "shareMediaCategory": "ARTICLE" if url else "NONE",
    }
    if url:
        share["media"] = [{"status": "READY", "originalUrl": url}]
    payload = {
        "author": _normalize_urn(person_urn),
        "lifecycleState": "PUBLISHED",
        "specificContent": {"com.linkedin.ugc.ShareContent": share},
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    req = request.Request(API, data=json.dumps(payload).encode(), method="POST",
                          headers={"Authorization": f"Bearer {token}",
                                   "Content-Type": "application/json",
                                   "X-Restli-Protocol-Version": "2.0.0"})
    try:
        with request.urlopen(req, timeout=30) as r:
            pid = r.headers.get("x-restli-id") or "(ok)"
            print(f"LinkedIn: posted ✓ {pid}")
            return 0
    except error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        print(f"LinkedIn: HTTP {e.code} — {detail}", file=sys.stderr)
        if e.code in (401, 403):
            print("  → token is likely expired/insufficient. Re-auth and update "
                  "linkedin_access_token in agent.env.", file=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001
        print(f"LinkedIn: failed — {e}", file=sys.stderr)
        return 3


def main() -> int:
    ap = argparse.ArgumentParser(description="Post the day's article to LinkedIn")
    ap.add_argument("--from-json")
    ap.add_argument("--text")
    ap.add_argument("--url")
    ap.add_argument("--tag", default="", help="label for logs (e.g. bvtech|jp)")
    args = ap.parse_args()

    token, urn = _load_creds()
    if not token or not urn:
        print("LinkedIn: no linkedin_access_token / linkedin_person_urn found — "
              "skipping (add them to agent.env to enable).", file=sys.stderr)
        return 4
    text, url = _caption(args)
    return post(token, urn, text, url)


if __name__ == "__main__":
    raise SystemExit(main())
