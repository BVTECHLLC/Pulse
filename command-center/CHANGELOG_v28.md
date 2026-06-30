# BVTech MSP Command Center — v28.0 Changelog

**Release: April 2026**
**Codename: SAFETY HOLD**

## TL;DR

v28 is a bug-fix and safety release. It fixes the "Super Scraper opens a
blank Python window and does nothing" problem, corrects the version
strings (v27 still reported itself as v26 everywhere), and most
importantly — puts a hard safety hold on the ORM Cloudflare Direct
Upload path because it contained a bug that would have wiped your
entire site on every publish. The bug never actually fired in
production because a *second* routing bug was accidentally blocking
the first one. Both are now caught server-side in v28, and the
Cloudflare Direct Upload path is held until v29 ships the proper
site-root-walk rewrite.

**Nothing you need to reinstall or reconfigure. Just drop v28 in and
your existing config carries over.**

---

## Bugs Fixed

### 1. Super Scraper blank Python window + frozen log

**Symptom:** Click "Launch Super Scraper" → a blank `C:\Python314\python.EXE`
window pops up → the browser log at the bottom of the page shows the
launch command but then sits there doing nothing for 30–60 seconds.
Eventually output appears in a burst, or the window just closes.

**Root cause:** Two stacked problems in `stream_process()`:

1. **Python block-buffers stdout whenever it's piped to a non-TTY.** When
   Flask captures subprocess output via `stdout=PIPE`, Python's C runtime
   decides "this isn't a terminal" and switches to 4KB block buffering.
   The regular scraper prints often enough to flush the buffer; the Super
   Scraper spends 10–60 seconds on the first website deep-crawl and
   LinkedIn search before it has anything to print, so the pipe stays
   completely empty. The browser log looks frozen.

2. **`subprocess.Popen()` was not passing `CREATE_NO_WINDOW` on Windows.**
   When a Flask process (or a PyInstaller-wrapped one) spawns
   `python.exe`, Windows attaches a new console window to the child
   because `python.exe` is a console-subsystem binary. Stdout is still
   being captured by the pipe, so the window stays blank forever — it
   looks broken but it isn't, it's just Windows being Windows.

**Fix:** `stream_process()` now:
- Injects `-u` right after `PYTHON_EXE` in the command (forces unbuffered
  stdout/stderr at the interpreter level).
- Sets `PYTHONUNBUFFERED=1` and `PYTHONIOENCODING=utf-8` in the child
  environment (belt and suspenders).
- Uses `bufsize=1` and `iter(process.stdout.readline, "")` so each line
  is yielded to the browser the instant it arrives.
- Passes `creationflags=subprocess.CREATE_NO_WINDOW` on Windows so no
  phantom console ever appears.

After this fix, the Super Scraper streams into the browser panel
immediately and no stray Python windows pop up anywhere.

### 2. v27 still called itself v26 everywhere

**Symptom:** Clean install of the v27 zip into a new folder — the title
bar, header badge, welcome modal, and command-center section all still
said "v26.0 FINAL". This was not a cache problem, not an old-copy-running
problem. The v27 zip was built on top of the v26 source without
updating the version strings.

**Fix:** All user-visible version strings now read `v28.0 FINAL —
Super Scraper Fixed`. There are a couple of `<!-- v26: -->` HTML
comments left in the source as historical notes about what specific
blocks originally did — those are for future me and don't render
anywhere visible.

### 3. ORM publisher mode label lied

**Symptom (latent — would have manifested as weird errors):**
`get_bvtech_publisher()` and `_get_jp_publisher()` both had a structural
bug where if you had `gh_token` set but `cf_api_token` blank, they
would return the tuple `(cf_client, "cloudflare")` — but the client's
internal `self.mode` was actually `"github"`. The caller
(`_generate_one_post`) would then branch based on the string "cloudflare"
while the underlying client would branch based on `self.mode == "github"`.
The two sides disagreed about what was happening.

**Fix:** Both publisher functions now inspect `client.mode` directly and
return the real mode string (`cloudflare_direct`, `github`, or
`wordpress`). No more lying about which deploy path is going to run.

### 4. [CRITICAL] ORM Cloudflare Direct Upload would have wiped your entire site

This is the worst bug I've ever found in this codebase and I want to
explain it carefully because it matters.

**What the old code did:** `_deploy_cf_direct()` in
`tacticalrmm_integration.py` called `_cf_create_deployment()` with a
single-entry dict: `{file_path: html_content}` — just the new blog
post. `_cf_create_deployment()` then POSTed a deployment manifest to
Cloudflare Pages Direct Upload API containing only that one file.

**What Cloudflare Pages Direct Upload actually does:** Every
deployment is a **complete replacement of the site**. Whatever files
you put in the deployment manifest become the *entirety* of what's
served. Files not in the manifest stop existing.

**What this means in practice:** If this code had ever successfully
fired on your live site, it would have uploaded a deployment containing
only `blog/my-new-post.html`. BVTech.org (186 files — home page,
services, locations, Spanish translations, case studies, blog archive,
assets, everything) would have been replaced with a single blog post.
JordanPolasek.com would have been replaced with a single blog post.
The sites would have been nuked on the very first publish, and the
nuke would have repeated on every subsequent publish.

**Why the sites are still intact:** Pure luck. Bug #3 above (the mode-
label lie) and the broken Cloudflare → GitHub OAuth connection Jordan
has been fighting with for months meant the CF Direct Upload path was
never actually reached in the running code. The two bugs were blocking
each other. If Jordan had fixed either one in isolation, the other
would have fired and the site would have been wiped.

**Fix:** `_deploy_cf_direct()` now refuses to run and returns an
explicit error:

> v28 SAFETY HOLD: Cloudflare Direct Upload is disabled. The previous
> implementation would have wiped your entire site on every publish
> (it only uploaded the new blog post, and CF Direct Upload replaces
> the full deployment). This is fixed in v29 with a site-root walk.
> For now, ORM auto-post is on hold. Do NOT enable the scheduler or
> click Publish All until v29.

The old buggy function is preserved as
`_deploy_cf_direct_UNSAFE_v27_ORIGINAL` for reference only, clearly
marked DO NOT CALL.

`_generate_one_post()` in `bvtech_app.py` now recognizes the mode
string `"disabled_v28_hold"` returned by `get_bvtech_publisher()` /
`_get_jp_publisher()` and surfaces the safety-hold error to the ORM
queue as a normal post failure, so queued posts are marked `error`
with a clear message instead of either silently disappearing or
detonating the site.

**User-visible changes:**

- The ORM tab now shows a red safety-hold banner at the top whenever
  your config has Cloudflare Direct Upload credentials set (the
  combination that would have triggered the bug). The banner explains
  what's going on and tells you to wait for v29.
- The banner is driven off `/api/config`, which you can verify by
  clearing the CF credentials in Settings and reloading — it'll
  disappear.
- If you clicked Publish Next or Publish All with CF creds set, queued
  posts get marked with the safety-hold error instead of hitting the
  broken path.
- WordPress and GitHub deploy modes are not affected by the hold.
  They still work exactly as before. Only Cloudflare Pages Direct
  Upload is held.

---

## What's coming in v29

The real fix for the CF Direct Upload path. The deployment manifest
needs to include every file on your live site, not just the new blog
post. The plan:

1. Add a `site_root` config field pointing at a local mirror of your
   extracted site (e.g. the folder you get when you unzip
   `CompletedBVTechWebsite_V38.zip`).
2. On each publish, walk the `site_root` directory, build the full
   manifest (every HTML file, every asset, every redirect rule), inject
   the new `blog/{slug}.html`, regenerate `blog/index.html` so the post
   actually shows up in the listing, and upload the complete tree in
   one deployment.
3. This is the same thing `wrangler pages deploy ./site` does under the
   hood. It does not require the `wrangler` CLI, the GitHub bridge,
   the broken Cloudflare → GitHub OAuth dance, or any other piece of
   the Rube Goldberg machine that's been getting in the way. Just the
   API token that's already in your settings.
4. Add a one-shot "Test Auto-Post" button that publishes a single
   throwaway test post through the full pipeline so you can verify it
   worked *before* trusting it on a schedule.

v29 is the real fix. v28 is the "don't let the existing code burn
your house down while we wait for the real fix" release.

---

## Files changed in v28

- `bvtech_app.py` — `stream_process()` rewrite, `get_bvtech_publisher()`
  fix, `_get_jp_publisher()` fix, `_generate_one_post()` safety-hold
  handling, ORM tab banner markup and JS, version strings throughout.
- `tacticalrmm_integration.py` — `_deploy_cf_direct()` safety hold,
  old implementation preserved as `_deploy_cf_direct_UNSAFE_v27_ORIGINAL`.
- `CHANGELOG_v28.md` — this file.

Nothing else touched. `super_scraper.py`, `prospect_scraper.py`,
`power_dialer.py`, `email_campaign.py`, `sms_campaign.py`,
`dialpad_integration.py`, `autopilot.py`, and the rest are byte-for-byte
identical to v27.
