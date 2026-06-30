#!/usr/bin/env python3
"""Idiot-proof, safe updater for /etc/bvtech/agent.env (JSON).

Editing agent.env by hand keeps corrupting the JSON. This sets ONE key, keeps the
file valid, and makes a timestamped backup first. Never prints secret values.

Usage (on the box):
    python3 /srv/pulse/opspilot/automation/set_key.py anthropic_key "sk-ant-..."
    python3 /srv/pulse/opspilot/automation/set_key.py linkedin_access_token "AQV..."
    python3 /srv/pulse/opspilot/automation/set_key.py --show          # list key NAMES only

It auto-locates agent.env at $BVTECH_AGENT_ENV or /etc/bvtech/agent.env.
"""
from __future__ import annotations

import json
import os
import sys
import time

PATH = os.environ.get("BVTECH_AGENT_ENV", "/etc/bvtech/agent.env")


def _load() -> dict:
    try:
        with open(PATH, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("agent.env is not a JSON object")
        return data
    except FileNotFoundError:
        return {}
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {PATH} is not valid JSON ({e}).")
        print("Fix or restore it first; this tool won't overwrite a broken file blindly.")
        sys.exit(2)


def main() -> int:
    args = sys.argv[1:]
    data = _load()

    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args[0] == "--show":
        print(f"{PATH} has {len(data)} keys:")
        for k in sorted(data):
            v = str(data.get(k, ""))
            hint = ("set, ends …" + v[-4:]) if v else "(empty)"
            print(f"  {k:30s} {hint}")
        return 0

    if len(args) < 2:
        print("Usage: set_key.py <key_name> <value>   (or --show)")
        return 2
    key, value = args[0].strip(), args[1]

    # Timestamped backup so a mistake is always recoverable.
    if os.path.exists(PATH):
        bak = f"{PATH}.bak.{int(time.time())}"
        try:
            with open(PATH, encoding="utf-8-sig") as src, open(bak, "w") as dst:
                dst.write(src.read())
            print(f"backup: {bak}")
        except Exception as e:  # noqa: BLE001
            print(f"WARNING: could not write backup ({e}); continuing")

    data[key] = value
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)
    # Re-validate.
    json.load(open(PATH, encoding="utf-8-sig"))
    print(f"OK: set '{key}' ({len(value)} chars). agent.env still VALID JSON ✓")
    print("Done. The next cron run (or a manual run) will use the new value.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
