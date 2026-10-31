# Deployment for Claude / external build agent

**Read [`PORTAL_INTEGRATION.md`](PORTAL_INTEGRATION.md) first.** This game is deployed through the existing OpsPilot FastAPI portal at `portal.bvtech.org/kart/` with a separate Node `volt-rush` Compose service. **Do not use the original standalone Nginx/Systemd installation approach.**

The authoritative deployment sequence is GitHub feature branch `claude/pulse-rmm-msp-features-c4ug25` -> fast-forward `main` -> cron rebuild of **api only** -> **manual** rebuilding of the Node game service by someone with SSH access -> smoke tests and physical iPhone check. Preserve `/arena`, `/signal`, `/graveyard-shift` and all other existing mounts.
