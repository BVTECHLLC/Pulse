# Safe Add-on & Mod Data Format (proposal)

**Implemented:** four curated mutators in `src/data.js`: Classic, Nightmare, Glass Cannon and Turbo. These work immediately; this document is a proposal for future shareable packs.

**Do not import or execute player-uploaded JS modules, HTML, shader source, filesystem paths or arbitrary URLs.** For a public portal, community content must be validated on the server and scoped to a strict declarative schema. Untrusted modded games should not submit ranked results or reward permanent account currency until a deterministic validation system exists.

Proposed package:

```json
{
  "schemaVersion": 1,
  "packId": "nightmare-moon",
  "displayName": "Nightmare Moon",
  "authorAlias": "Community Builder",
  "version": "1.0.0",
  "description": "An accelerated night with more enemies",
  "mode": "unranked",
  "modifiers": {
    "enemySpawnMultiplier": 1.25,
    "enemySpeedMultiplier": 1.1,
    "heroDamageMultiplier": 1.0,
    "maxHeroHealthMultiplier": 1.0,
    "xpMultiplier": 1.0
  }
}
```

Validation: max 16KB JSON; required fields only, no extra keys; pack ID 3–40 URL-safe chars; name ≤50 chars; description ≤180; all multipliers finite and clamped to 0.5–2.0; authorAlias escaped on render; reject recursive objects, weird Unicode controls and invalid date/time/number. Store under a content hash. No user-provided CDN links, images, sounds, or script; assets must be pre-reviewed/served under same-origin with MIME/size restrictions. Use per-user ownership, moderation, rate limits, antivirus/scanning on any later binary asset support, and admin disable/revoke.

A future safe add-on API could introduce pre-approved enemy waves, cosmetic palettes and custom map layouts using IDs referencing bundled first-party components, but never arbitrary code. Playtest mods separately from ranked, avoid paywalls, and enforce server-side reward rules.
