# SIGNAL 199X — Safety & Operations Checklist

## Before sharing publicly

**Status: CLOSED ALPHA BUILD — NOT YET APPROVED FOR AN UNSUPERVISED PUBLIC LAUNCH.**

- Publish final terms, privacy policy, and a real abuse/deletion contact channel. Ask legal counsel to review age restrictions and all applicable child privacy requirements. The game is restricted to age 13+ and must not be presented as a child-safe service without additional work.
- Leave free-text chat OFF. Approved phrases are the only player messages in the default build. Even quick-chat needs real moderators to review context, repeated behavior, and potential coordinated harassment.
- Assign moderators and an appeals process. At least once daily during a live alpha, inspect reports with `node admin.mjs reports`; handle threats promptly and do not publicly disclose reporters.
- Establish an incident response workflow and abuse desk; configure host firewall, DDoS protection, rate limits, resource alerts, disk-space monitoring and patch cadence. This game is a single Node process with a SQLite database, not a horizontally scalable MMO backend.
- Make encrypted, consistent, **offsite** DB backups; test restores. Limit filesystem access; keep Node listening on localhost and use HTTPS. Do not run as root or serve `data/`.
- Test browser/phone performance and concurrent player capacity before growth. Hard WebSocket limit in this build is 80 sockets. This is an operational safety rail, not a promise of 80 smooth concurrent players.
- Add automated security scanning, dependency/Node version maintenance, account verification/recovery, a public moderation team interface, anti-bot/captcha, formal security review, robust CSRF and WebSocket edge-case fuzzing, external penetration tests, accessibility audit and load tests before a wide release.

## Moderation behavior

The server does not broadcast free text by default. Optional free text (`ENABLE_TEXT_CHAT=true`) is checked by a conservative filter and player/session rate limits. Filters will miss evasion and can block harmless speech; **they are not human moderators**. A player can choose `TEAM > REPORT` for a nearby player's account and reason, or `BLOCK` to hide their messages/character. Reports store neither the full conversation nor a screen recording; do not infer wrongdoing solely from report count.

Operator CLI examples (same user/data directory as service):

```
node admin.mjs reports
node admin.mjs players
node admin.mjs mute PlayerName 30 "Repeated spam"
node admin.mjs ban PlayerName 24 "Harassment after warning"
node admin.mjs unmute PlayerName
node admin.mjs unban PlayerName
node admin.mjs close 12
node admin.mjs delete PlayerName
```

Account moderation CLI updates the SQLite row; the game checks active sessions for new bans approximately every five seconds and disconnects banned players. The CLI is server-side only; do not expose it through the web server.

## Youth privacy and data

Only age 13+ may register or preview. This is self-attestation, **not reliable age verification**. There is no COPPA parental consent, guardian account, age-appropriate default configuration by jurisdiction, or in-product account deletion workflow. Privacy/terms HTML are draft placeholders. Do not silently enable targeted ads, tracking, monetization, data sales, or unreviewed third-party assets.

Game database stores account identifiers, password-derived hash+salt, hashed sessions, in-game progress, and a player ID block list; reports contain reporter ID, accused ID, category and timestamp. Operational logs are minimal. Define/report your exact retention policy and ensure access/deletion request handling. Contact the operator through the BVTech site; do not publish employee personal contacts.

## Anti-cheat boundaries

Players send inputs/actions only. Node decides movement, collision, damage, inventory, purchases, loot RNG, minigame rewards and daily prize caps. Malicious clients can still automate inputs, solve exposed client-side puzzles, flood actions, exploit bugs, or use multiple accounts. The minigames limit prize value (12 rewarding plays/day) rather than claiming cheat-proof skill validation. Treat public PvP achievements as casual, not tournament-secure.

## Recommended next milestones

Phase 1: Closed alpha with volunteer moderators, telemetry and abuse handling. Phase 2: Bigger Rift level designs, dynamic puzzles, synchronized environmental hazards, better character direction animation, soundtrack, sound preferences and accessibility. Phase 3: Friends/parties across server restarts, guilds, proper instanced home interiors, co-op housing games, matchmaking and boss phases. Phase 4: external security review, identity integration, backups/restore drills, automated deployments and load-tested multi-server architecture.
