# BVTech MSP Command Center — v32.1 Changelog

**Release: April 2026**
**Codename: DEBUG OVERLAY — v32.0 bug fix**

## TL;DR

v32.0 shipped broken. Every button was silently dead because of a
JavaScript duplicate-declaration error that I never caught because
I never actually parsed the rendered JavaScript — I only tested
Python syntax, Flask routes, and backend logic in isolation.

v32.1 fixes the bug AND adds the safety net that should have been
there from the start:

1. **The v32.0 bug is fixed** (one duplicate `const` removed)
2. **Built-in debug overlay** — captures every JS error and shows
   it in a red panel at the bottom of the screen. If anything
   silently breaks again, you will see it.
3. **`/api/health` startup check** — page load pings the server
   and shows a top-right "All Systems Operational" banner with
   version, route count, task count, and module load status.
   This is the "Refresh All Systems Start" confirmation that was
   missing.
4. **Debug button in the header strip** — click 🐛 DEBUG any time
   to manually open the error console, even if there are no errors.

Every v32.0 feature — channel rewriter, staggered scheduler, post
queue, Draft & Track, retroactive backlinks CLI, polish pass — is
otherwise unchanged. They just actually work now.

---

## The bug

### Symptoms

- Dashboard renders fine, looks clean
- Every button silently does nothing
- No What's New popup
- No startup confirmation message
- No visible errors anywhere
- Browser console would have showed one red error at page load,
  but the user would have needed to know to open devtools

### Root cause

Two `const _origSwitchTab = typeof switchTab === 'function' ? switchTab : null;`
declarations. One was dead code from an old news-tab hook at line
5436 of `bvtech_app.py` that was never finished and never removed.
The other was the v31/v32 `switchTab` monkey-patch at line 6058
that's actually used by the HS Track, Automation, and Super Posting
tab auto-load hooks.

JavaScript `const` does NOT allow re-declaration. When the parser
hit the second declaration, it threw:

```
SyntaxError: Identifier '_origSwitchTab' has already been declared
```

This error aborted the ENTIRE inline `<script>` block. Every
function declared AFTER line 3116 of the rendered JS never got
created: `switchTab`, `showWhatsNew`, `queueAdd`, `queueLoad`,
`loadHsStats`, `loadAutomationTasks`, `draftAndTrack`, every
button handler, everything. That's why every `onclick="switchTab(...)"`
in the HTML was a no-op — `switchTab` was `undefined`.

The dashboard rendered because the HTML is static. Every
interaction was dead because the JS block had bailed out.

### Why I didn't catch it

I tested:
- Python `ast.parse` on every `.py` file ✓
- Flask routes registered with correct param names ✓
- Module imports ✓
- Backend logic in isolation ✓

I did NOT test:
- The actual rendered JavaScript ✗

After 4 releases (v28, v29, v30, v31, v32) of massive `str_replace`
operations on HTML/JS embedded in Python strings, any one of them
could have introduced a JS-side bug without breaking Python. I
should have been running `node --check` on the rendered JS every
release. I wasn't.

### How v32.1 found it

Booted the actual Flask app in the sandbox:
```
python3 bvtech_app.py &
curl http://127.0.0.1:5683/ > rendered.html
# Extract the <script> block
node --check script.js
```

Node reported the exact error and line number in under a second:

```
/tmp/bvtech_main.js:3116
const _origSwitchTab = typeof switchTab === 'function' ? switchTab : null;
      ^
SyntaxError: Identifier '_origSwitchTab' has already been declared
```

### The fix

Deleted the dead first declaration (line 5436). That code was
never wired up — it was a stub from when someone tried to add a
news-tab auto-load hook and never finished it. The comment above
it literally said "We'll hook into tab switch below to auto-load
news history" and then nothing happened.

The real v31/v32 monkey-patch at line 6058 is preserved and now
declares `_origSwitchTab` once, cleanly, without a conflict.

---

## 1. Built-in debug overlay

Injected at the very TOP of the main script block, BEFORE any
other JS, so it captures errors from everything else:

```javascript
(function() {
  var errors = [];
  window.addEventListener('error', function(ev) {
    record('error', ev.message, ev.filename, ev.lineno);
  });
  window.addEventListener('unhandledrejection', function(ev) {
    record('promise', ev.reason && ev.reason.message || String(ev.reason));
  });
  // Wrap console.error
  var orig = console.error;
  console.error = function() {
    record('console', [].slice.call(arguments).map(String).join(' '));
    return orig.apply(console, arguments);
  };
  // ... panel rendering, auto-show on first error, etc.
})();
```

Captures three categories:
- **`window.error`** — any uncaught JS exception
- **`unhandledrejection`** — any promise that rejects without a catch
- **`console.error`** — any explicit error log (the existing code
  already has dozens of `console.error(...)` calls that previously
  just disappeared into devtools; they now surface in the UI)

Each error shows up in a red panel pinned to the bottom of the
window, max 40% height, scrollable. Each entry shows:
- Entry number
- Error type: `[error]`, `[promise]`, or `[console]`
- The message
- Source file + line number (if available)

**Three buttons in the header of the panel:**
- **Copy** — copy all errors to clipboard (for pasting into a
  bug report)
- **Clear** — wipe the list
- **×** — hide the panel (errors are kept, just not displayed)

**Public JS API:**
```javascript
window.bvtechDebug.show()      // open the panel
window.bvtechDebug.hide()      // close but keep errors
window.bvtechDebug.clear()     // wipe the error list
window.bvtechDebug.copy()      // copy all errors to clipboard
window.bvtechDebug.count()     // return current error count
window.bvtechDebug.getErrors() // return array of error objects
window.bvtechDebug.record(type, msg, src, line)  // manually log
```

**Manual trigger:** there's a new **🐛 DEBUG** button in the
header badge strip next to ⚙️ SETTINGS. Click it any time to
pop open the console, even when there are no errors — useful
for confirming "OK, nothing broken."

---

## 2. `/api/health` startup check

New Flask route that reports app health:

```python
@app.route("/api/health")
def v32_health():
    modules_to_check = [
        "channel_rewriter", "post_queue", "hubspot_tracker",
        "local_automation", "posts_index", "google_business_profile",
        "cloudflare_pages_deploy", "super_scraper",
    ]
    modules_ok = 0
    module_errors = []
    for m in modules_to_check:
        try:
            __import__(m)
            modules_ok += 1
        except Exception as ex:
            module_errors.append(f"{m}: {ex}")

    runner = getattr(builtins, "_BVTECH_TASK_RUNNER", None)
    task_count = len(runner.all_tasks()) if runner else 0

    return jsonify({
        "ok": modules_ok == len(modules_to_check),
        "version": APP_VERSION,
        "routes": len(list(app.url_map.iter_rules())),
        "tasks": task_count,
        "modules_ok": modules_ok,
        "modules_total": len(modules_to_check),
        "module_errors": module_errors,
    })
```

Example response:
```json
{
  "ok": true,
  "version": "32.1",
  "routes": 163,
  "tasks": 9,
  "modules_ok": 8,
  "modules_total": 8,
  "module_errors": []
}
```

## 3. Health banner on page load

The dashboard now pings `/api/health` on page load and shows a
green banner in the top-right corner:

> ✅ All Systems Operational
> v32.1 · 163 routes · 9 tasks · 8/8 modules
> Click to dismiss

Auto-dismisses after 8 seconds. Click to dismiss immediately.

If any module fails to load or any task is broken, the banner
turns red and says "⚠️ All Systems Degraded" with the same stats.
You can see at a glance whether everything loaded.

This is the "Refresh All Systems Start" confirmation that was
missing in v32.0 — the popup that never showed because the JS
block had died.

---

## What I tested this time

Before shipping v32.1:

1. **`python3 -c "import ast; ast.parse(open('bvtech_app.py').read())"`**
   ✓ Python syntax clean

2. **Booted the app** in the sandbox at `http://127.0.0.1:5683/`,
   fetched the rendered HTML (392 KB), extracted the inline
   `<script>` block (200 KB), and ran **`node --check`** on it.
   ✓ Zero syntax errors.

3. **Scanned for duplicate top-level `const`/`let`/`var`
   declarations** in the extracted JS:
   ```javascript
   const counts = {};
   const re = /^(const|let|var)\s+(\w+)/gm;
   // ... find dupes
   ```
   ✓ Zero duplicates.

4. **Verified 21 critical functions are defined** in the JS:
   `switchTab`, `showWhatsNew`, `queueAdd`, `queueLoad`,
   `queueRemove`, `draftAndTrack`, `loadAutomationTasks`,
   `runTaskNow`, `toggleTask`, `installToWindows`, `hsTrackVerify`,
   `hsTrackLog`, `saveBccAddress`, `loadBccAddress`, `saveSettings`,
   `showToast`, `ormPostNow`, `escapeHtml`, `loadHsStats`,
   `loadAutomationLog`, `loadAutomationStats`.
   ✓ All 21 defined.

5. **Hit `/api/health`** via the running Flask app.
   ✓ Returns `ok=True, v=32.1, routes=163, modules=8/8`.

6. **Verified the debug overlay code** is present and correctly
   scoped at the top of the script block.
   ✓ Present.

7. **Verified the health banner JS** runs on `DOMContentLoaded`.
   ✓ Present.

This is what I should have been doing across all of v28-v32. From
now on, every release gets `node --check` on the rendered JS as
part of the pre-ship checklist.

---

## Files changed in v32.1

- `bvtech_app.py`:
  - **DELETED** dead `const _origSwitchTab` declaration at line 5436
    (the bug)
  - Added ~85 lines of debug overlay JS at the top of the script
    block (captures `window.error`, `unhandledrejection`,
    `console.error`)
  - Added ~25 lines of health-banner JS that fires on
    `DOMContentLoaded`
  - Added `/api/health` route (~35 lines)
  - Added 🐛 DEBUG button to the header badge strip
  - `APP_VERSION` bumped 32.0 → 32.1
  - Header version badge bumped
  - `_V31_WHATS_NEW` updated with v32.1 bug-fix highlights
  - localStorage version check bumped `32.0` → `32.1`
- `CHANGELOG_v32.1.md` (this file)

Every other Python module is byte-identical to v32.0.

---

## Lessons for next release

1. **Always `node --check` the rendered JavaScript** as part of
   the pre-ship test. Python `ast.parse` is not enough when you
   have a single-file app with 200 KB of JS embedded in Python
   strings.

2. **Never do large `str_replace` operations on embedded JS**
   without verifying the before and after both parse cleanly.
   The fix for v32.0 literally took 2 seconds once I ran Node
   against the rendered JS. It would have caught this bug before
   shipping every time.

3. **Keep the debug overlay** forever. It's 85 lines of code and
   it turns "nothing happens" into "here's the exact error at
   line 3116". That's worth it.

4. **Keep the health banner** forever. The user kept telling me
   they were missing the "Refresh All Systems Start" confirmation
   and I didn't understand what they meant. Now there's a
   dedicated server-side health check and a visible banner
   confirming the app is alive on every page load.
