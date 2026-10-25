# SIGNAL 199X v3 — SAFETY & BVTECH OPERATOR CHECKLIST

**No online game can be guaranteed safe for all ages.** The current account gate is **13+ only**. Do not market it as children's software without a legal/privacy review, real moderation coverage, and features built for the intended ages and jurisdictions.

## Current controls

- Browser receives only proximity-limited, filtered social information, and position/combat rewards are authoritative on the server.
- No free-text chat by default (`TEXT_CHAT_ENABLED` must remain off until human moderation is staffed). Quick chat uses an allowlist.
- Sign-up usernames are checked against reserved/abusive variants and length/character restrictions. Free text, if enabled, has spam/rate limits, contact-info and profanity filtering, muted users and operator logs. **Filters are imperfect**, including non-English terms, slang and determined evasion.
- Guest accounts lack free-text chat; blocked players are hidden, players can report harassment/spam/cheating.
- Players are not forced into PvP; gear does not grant overwhelming PvP advantage; no theft or loss of currency/items after PvP knockouts.
- Session cookies are `HttpOnly` and `SameSite=Lax`; `Secure` with `NODE_ENV=production`. Passwords are scrypt salted. SQLite is private to the Node process. Never expose backups or database files over HTTP.
- POST origin validation, rate limits, WebSocket message length/frame checks, server movement collision, proximity checks for rewards, and per-activity reward caps.

## Before exposing to strangers

1. Keep gameplay and customer business operations separated: isolated service user, directory, Nginx virtual host and database; no privileged credentials on game host.
2. Use HTTPS/WSS, strong Nginx request limits, HSTS after verifying TLS, and a reverse proxy configuration that forwards `Host` and WebSocket upgrade headers. Block the app port from the Internet.
3. Create a public privacy policy accurately describing IP address, cookie/session, account data, interactions/reports, retention, deletion process and operator contact; include minor-specific disclosures. Template `public/privacy.html` needs review.
4. Add verified email recovery, optional 2FA or passkeys, bot defenses, privacy-friendly analytics if needed, security logs, backup restore drills, account deletion, abuse escalation and human moderation.
5. Add Discord-like safety operations before public launch: moderator shifts, evidence retention policy, user appeals, response SLAs, ban evasion controls, DDoS / WAF protection.
6. Carry out penetration testing, dependency scanning, load tests and tuning, load shedding and player caps. Node's built-in WebSocket handling is a minimal prototype; production should use an audited, maintained WebSocket implementation and robust error handling.
7. Review copyright/trademark law and game publisher rights. This project intentionally avoids direct copies of any named inspiration; do not import third-party ripped game assets.
8. Consider excluding free text entirely for the 13+ audience until proper review. A profanity filter does not by itself make communications safe.

**BVTech risk management:** place the game in a separate Linode/VM or container with a restricted service user, no access to your existing `portal.bvtech.org` data, scoped backups and monitoring. Do not share cookies or account databases across those sites.
