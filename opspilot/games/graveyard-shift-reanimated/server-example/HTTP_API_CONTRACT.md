# Linode endpoint contract (reference, not implemented)

All below endpoints are same-origin, HTTPS, authenticated by the **existing BVTech account session**. Routes are under `/api/graveyard-shift/v1`. No browser-held API secrets; cookies use Secure + HttpOnly + SameSite. CSRF protect all cookie-authenticated state mutations.

- `GET /me` → `{ profile: { accountXP, coins, souls, level, upgrades, unlockedCharacters, equippedSkins, achievements, bestRuns, settings } }`
- `POST /sessions` request `{ gameVersion, modeId, mapId, characterId, skinId }`; response `{ sessionId, seed, startedAt, expiresAt, configHash }`; validate all IDs and unlocks.
- `POST /sessions/:sessionId/events` optional chunked deterministic input or telemetry events; bounded size and monotonic sequence number.
- `POST /sessions/:sessionId/finish` request `{ eventLogHash, lastSequence, result: { durationMs, kills, runXP, coins, souls, victory } }`. Treat all `result` values as untrusted claims; server calculates/validates actual rewards and commits once. Response `{ verified: true, credited: {...}, profile: {...} }` or typed validation error.
- `POST /upgrades/:upgradeId` request `{ expectedProfileVersion }`; response updated profile; atomic rank limit/price computation in SQL transaction with idempotency key.
- `PUT /equipment` request `{ characterId, skinId, mapId }`; server validates ownership then returns canonical equipment.
- `GET /leaderboards?mode=classic&map=cemetery&limit=25&cursor=...` → public alias, validated kills/duration and stable pagination. Never leak email, IP, session tokens.
- `POST /migrations/local-save` request `{ requestedImport: {...}, consent: true }`, accept once after user review, sanity checks and manual restrictions as needed. Do not migrate local scores directly into ranked records.

Recommended error statuses: 400 invalid schema, 401 not logged in, 403 entitlement/CSRF, 404 missing, 409 version/replay conflict, 422 impossible run, 429 rate-limited, 500 generic server error. Record audit logs for progression without storing raw passwords/tokens.

**Anti-cheat:** deterministic replay of player inputs from server-issued random seed with rate/time plausibility or server-authoritative simulation; server must never award results solely because a browser posted a larger XP number. Validate one settled finish per run, signed checkpoints if needed, version pinning, expiry and duplicate submission behavior. Avoid claiming that local anti-tamper measures stop cheats.
