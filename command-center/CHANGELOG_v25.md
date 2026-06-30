# BVTech MSP Command Center v25 — CF-DIRECT (GitHub Bypass)

**Built:** April 5, 2026
**Base:** v24 CLOUDFLARE edition

## Why v25 exists

Cloudflare has a known platform bug where the "Connect to Git" OAuth
handshake in the Pages dashboard sometimes spins forever or fails silently.
This prevented the v24 auto-poster from working even though everything was
configured correctly.

v25 fixes this by **bypassing GitHub entirely** and using Cloudflare's
Direct Upload API instead. The infrastructure for this was already written
in v24 — it just wasn't being preferred by the publisher selection logic.

## What changed from v24

### 🐛 Fixed: Publisher priority now prefers Cloudflare Direct Upload

**File:** `bvtech_app.py` — `get_bvtech_publisher()` and `_get_jp_client()`

v24 behavior:
```python
if cfg.get("gh_token") and cfg.get("gh_repo"):       # GitHub checked FIRST
    return get_cf_client(), "cloudflare"
if cfg.get("cf_api_token") and cfg.get("cf_account_id"):  # CF Direct SECOND
    return get_cf_client(), "cloudflare"
```

v25 behavior:
```python
if cfg.get("cf_api_token") and cfg.get("cf_account_id"):  # CF Direct FIRST
    return get_cf_client(), "cloudflare"
if cfg.get("gh_token") and cfg.get("gh_repo"):       # GitHub SECOND (legacy)
    return get_cf_client(), "cloudflare"
```

Both publishers (BVTech.org and JordanPolasek.com) now prefer the Direct
Upload path, which sidesteps the Cloudflare OAuth bug entirely.

### 📝 Added: Runtime mode logging

The publisher now prints which mode it's using on every call, so you can
verify from the console log which path is actually being taken. Example:

```
  [v25] BVTech publisher → Cloudflare Direct Upload mode
```

### 🏷️ Version strings bumped

The UI now shows **"v25.0 CF-DIRECT"** instead of "v24.0" so you can
visually tell the old tool from the new one.

### 📚 Added: CF_DIRECT_SETUP_GUIDE.md

Step-by-step walkthrough for getting your Cloudflare API token and Account
ID and plugging them into the Settings tab. 3-minute setup.

## What's NOT changed

Everything else is identical to v24. Same prospect scraper, same email
campaigns, same SMS, same dialer, same TacticalRMM integration, same ORM
Beast, same BVTech News generator. All your existing CSVs, configs, and
settings carry over.

## Upgrade path

1. **Back up** `bvtech_config.json` and `prospects.csv` from `C:\BVTech\`
   (copy them to a temp folder — insurance)
2. Stop the old Command Center (close the window or kill the process)
3. Extract `BVTech_MSP_CommandCenter_v25_CFDIRECT.zip` over `C:\BVTech\`
   and click "Replace All" when prompted
4. Your `bvtech_config.json` is NOT in the zip so your settings survive
5. Run `Start-BVTech.bat`
6. Follow `CF_DIRECT_SETUP_GUIDE.md` to configure Cloudflare credentials

## What this does NOT fix

- The WordPress 403 firewall error on JordanPolasek.com. That's a
  server-side WordPress issue, not a tool bug. Fix path: migrate JP to
  Cloudflare Pages (same as BVTech), then use the JP CF Direct fields.
- LinkedIn posting — already works, no changes needed.
- The Cloudflare->GitHub OAuth loop itself — that's a Cloudflare platform
  bug. We just route around it.
