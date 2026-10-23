# PHP2Shell response — BVTech (Oct 2026)

**CVEs:** CVE-2026-109618 (OOM corruption, GHSA-w8hw-w9fx-j79w) and
CVE-2026-109619 (stale global state, GHSA-6wmf-4rv5-p3rp). Disclosed and
patched 21 Oct 2026. Fixed in PHP 8.2.35 / 8.3.36 / 8.4.27 / 8.5.12. PHP
5.4–8.1 are affected; 8.1 and older get source-only backports, no binaries.

## How the bugs work

Both are use-after-free bugs in PHP's request startup, triggered by a fatal
out-of-memory error:

1. During multipart (RFC 1867) parsing, `session.upload_progress` handling can
   initialise session state early: `PS(id)` and the unserializer bookkeeping in
   `BG(unserialize)`.
2. The attacker pushes the worker into an out-of-memory fatal error mid-request.
   PHP bails out, the request heap is destroyed, and those globals are left
   pointing at freed memory. So are `EG(last_fatal_error_backtrace)` and, on
   the OPcache side, a desynced `CG(map_ptr_last)`.
3. The worker process survives, and the next request on the same worker uses
   the stale pointers. That gives the attacker either remote code execution or
   a leak of reclaimed heap memory, which comes back URL-encoded in a
   `PHPSESSID` cookie even if the app never calls `session_start()`.

Apache with mod_php is the highest-risk setup, because this all happens before
any application code runs. With PHP-FPM, how exploitable it is depends on the
app. The CLI has no network exposure.

## Where we stood

| Asset | Runtime | PHP? | Exposure |
|---|---|---|---|
| portal (Pulse/OpsPilot) | Python 3.12 / FastAPI in Docker | No | Not affected by the CVEs |
| bvtech.org, jordanpolasek.com, tx-plants.com, autumnpolasek.com | Static HTML on Cloudflare Pages | No | Not affected; nothing executes server-side |
| Postgres, Redis, Caddy, cloudflared containers | — | No | Not affected |
| Linode host (Ubuntu 24.04) | — | Verify with the box audit | See the box audit below |
| WordPress publisher | legacy fallback, not connected | n/a | We call it as a client; nothing hosted |

## What we changed anyway (v1.94.0)

The CVEs can't run on our stack, but the attack technique (oversized bodies
used to create memory pressure) and the scanning wave that followed affect any
web server:

- **RequestGuard** (`app/core/request_guard.py`) is the outermost ASGI layer. It:
  - returns 413 for any body over 10 MB, whether declared up front or streamed chunked;
  - returns 415 for inbound `multipart/form-data`, since the portal has no upload endpoints;
  - returns a 404 for PHP and WordPress probe paths (`*.php`, `/wp-*`, `/xmlrpc`, `phpunit`, `/.env`, `/.git/`) before the audit logger, rate limiter or database runs.
- **Caddy** enforces `request_body max_size 10MB` at the proxy.
- **SSRF fix found during the audit:** the public `headers-check` tool let urllib
  follow redirects automatically, so only the first hostname was vetted. A
  public site that redirected to an internal address got past the guard. The
  new `_fetch_public` follows redirects manually and re-runs the SSRF guard on
  every hop. Residual risk: DNS rebinding between the check and the connect.
- **Free exposure check** at `GET /api/public-tools/php2shell-check?host=`. It
  is passive: a single ordinary homepage request. It reads the advertised PHP
  version (`X-Powered-By` or `Server`), the `PHPSESSID` cookie and CMS
  fingerprints. It reports one of `vulnerable`, `vulnerable_eol`, `patched`,
  `php_version_hidden` or `no_php_detected`, plus next steps. It never sends an
  exploit payload.

## For client sites that DO run PHP

1. Upgrade the PHP runtime itself. Plugin and theme updates don't fix this.
2. Until then, keep a WAF with PHP2Shell rules in front. Cloudflare's free
   managed ruleset includes them.
3. Stopgap: set `session.upload_progress.enabled = 0` in php.ini or the FPM pool
   (`ini_set` has no effect on it), keep `post_max_size` low, and restart workers.
4. After patching, hunt for new admin users, unknown files in uploads
   directories and new cron jobs. Exploitation started around 17 Oct.
