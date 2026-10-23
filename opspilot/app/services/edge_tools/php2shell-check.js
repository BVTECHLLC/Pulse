// BVTech PHP2Shell exposure check — Cloudflare Pages Function (v1.96).
// Served same-origin at bvtech.org/tools-api/php2shell-check so the site CSP
// (default-src 'self') allows it and no cross-site request can be challenged.
// Mirrors opspilot/app/services/php2shell.py. PASSIVE: one ordinary homepage
// GET; reads advertised PHP version, PHPSESSID and CMS fingerprints. Never
// sends an exploit payload. Published by Pulse (services/tools_page.py).

const FIXED = { "8.2": 35, "8.3": 36, "8.4": 27, "8.5": 12 };
const FIXED_LABEL = "8.2.35 / 8.3.36 / 8.4.27 / 8.5.12";
const UA = "BVTech-SiteCheck/1.2 (+https://bvtech.org/tools/)";
const HOST_RE = /^[a-z0-9.-]{3,253}$/;
const CMS = [
  ["WordPress", /generator"\s+content="WordPress|\/wp-content\/|\/wp-includes\//i],
  ["Drupal", /generator"\s+content="Drupal|Drupal\.settings|\/sites\/default\/files\//i],
  ["Joomla", /generator"\s+content="Joomla|\/media\/jui\/|\/media\/system\/js\//i],
  ["Magento", /Mage\.Cookies|\/static\/frontend\/Magento/i],
  ["PrestaShop", /prestashop/i],
];

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
}

// Public hostnames only: no IP literals, no internal names. (Workers cannot
// reach private networks anyway; this keeps the tool from being pointed at odd
// targets.)
export function cleanHost(h) {
  h = (h || "").trim().toLowerCase().replace(/^[a-z]+:\/\//, "").split("/")[0].split(":")[0];
  if (!HOST_RE.test(h) || h.includes("..") || !h.includes(".")) return null;
  if (/^[0-9.]+$/.test(h)) return null;
  if (h === "localhost" || /\.(local|internal|localhost|lan)$/.test(h)) return null;
  return h;
}

export function assess(maj, min, patch) {
  const ver = `${maj}.${min}.${patch}`;
  if (maj < 5 || (maj === 5 && min < 4))
    return { version: ver, status: "eol_unaffected",
      detail: "Older than 5.4: predates these bugs, but is itself years past end-of-life and has other known flaws." };
  const need = FIXED[`${maj}.${min}`];
  if (need === undefined) {
    if (maj < 8 || (maj === 8 && min < 2))
      return { version: ver, status: "vulnerable_eol",
        detail: `PHP ${maj}.${min} is end-of-life: affected, and no official patched release exists. Upgrade to a supported branch (${FIXED_LABEL}).` };
    return { version: ver, status: "unknown_branch",
      detail: "Newer branch than this checker knows. Confirm with the PHP security advisory." };
  }
  if (patch >= need)
    return { version: ver, status: "patched", detail: `PHP ${ver} includes the PHP2Shell fix (${maj}.${min}.${need}+).` };
  return { version: ver, status: "vulnerable", detail: `PHP ${ver} is VULNERABLE. Upgrade to ${maj}.${min}.${need} or later.` };
}

export function report(host, headers, body) {
  const signals = [];
  let version = null;
  for (const name of ["x-powered-by", "server"]) {
    const v = headers.get(name);
    if (!v) continue;
    const m = v.match(/PHP\/(\d+)\.(\d+)\.(\d+)/i);
    if (m) { version = [+m[1], +m[2], +m[3]]; signals.push(`${name}: ${v.slice(0, 80)}`); }
    else if (/php/i.test(v)) signals.push(`${name}: ${v.slice(0, 80)}`);
  }
  const cookies = headers.getSetCookie ? headers.getSetCookie() : [headers.get("set-cookie") || ""];
  if (cookies.some((c) => /^PHPSESSID/i.test(c))) signals.push("cookie: PHPSESSID");
  const cms = CMS.filter(([, rx]) => rx.test(body || "")).map(([n]) => n);
  cms.forEach((c) => signals.push(`platform: ${c}`));
  const behindCf = !!headers.get("cf-ray") || /cloudflare/i.test(headers.get("server") || "");
  const out = { host, cves: ["CVE-2026-109618", "CVE-2026-109619"], fixed_versions: FIXED_LABEL,
    php_detected: signals.length > 0, cms, signals, behind_cloudflare: behindCf };
  if (version) {
    const a = assess(...version);
    Object.assign(out, { verdict: a.status, version: a.version, detail: a.detail });
  } else if (signals.length) {
    Object.assign(out, { verdict: "php_version_hidden", version: null,
      detail: `This site runs PHP (${signals.slice(0, 3).join(", ")}) but hides its version. It is exposed unless the PHP runtime was upgraded to ${FIXED_LABEL} on or after 21 Oct 2026. Ask your host to confirm the exact PHP version.` });
  } else {
    Object.assign(out, { verdict: "no_php_detected", version: null,
      detail: "No PHP signals on the homepage (static site or another stack). Not proof: check any admin, store or API subdomains too." });
  }
  let steps = [];
  if (["vulnerable", "vulnerable_eol", "php_version_hidden"].includes(out.verdict)) {
    steps = ["Upgrade the PHP runtime itself (plugin/theme updates do NOT fix this).",
      "Until patched: put the site behind a WAF with PHP2Shell rules (Cloudflare's free managed ruleset includes them).",
      "Until patched: set session.upload_progress.enabled = 0 in php.ini or the FPM pool (not via ini_set) and restart workers.",
      "After patching: look for new admin users, unknown files in uploads folders and unexpected cron jobs. Exploitation began 17 Oct."];
    if (behindCf) steps.splice(1, 0, "Cloudflare detected: keep its WAF on, but it is a seatbelt, not the fix.");
  }
  out.next_steps = steps;
  return out;
}

async function readCapped(resp, cap) {
  if (!resp.body) return "";
  const reader = resp.body.getReader();
  const chunks = [];
  let got = 0;
  while (got < cap) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    got += value.length;
  }
  try { await reader.cancel(); } catch (e) { /* already closed */ }
  const buf = new Uint8Array(Math.min(got, cap));
  let off = 0;
  for (const c of chunks) {
    const n = Math.min(c.length, buf.length - off);
    buf.set(c.subarray(0, n), off);
    off += n;
    if (off >= buf.length) break;
  }
  return new TextDecoder().decode(buf);
}

export async function onRequestGet({ request }) {
  const host = cleanHost(new URL(request.url).searchParams.get("host"));
  if (!host) return json({ error: "that doesn't look like a public website address" }, 400);
  let url = `https://${host}/`;
  let resp = null;
  try {
    for (let hop = 0; hop <= 3; hop++) {
      resp = await fetch(url, { redirect: "manual", headers: { "user-agent": UA },
        signal: AbortSignal.timeout(8000) });
      if ([301, 302, 303, 307, 308].includes(resp.status)) {
        const loc = resp.headers.get("location");
        if (!loc) break;
        const next = new URL(loc, url);
        if (!/^https?:$/.test(next.protocol) || !cleanHost(next.hostname))
          return json({ host, error: "redirect to a non-public address refused" });
        url = next.toString();
        resp = null;
        continue;
      }
      break;
    }
  } catch (e) {
    return json({ host, error: `could not load https://${host}/ (${String(e && e.message || e).slice(0, 120)})` });
  }
  if (!resp) return json({ host, error: "too many redirects" });
  const body = await readCapped(resp, 256 * 1024);
  const out = report(host, resp.headers, body);
  out.status = resp.status;
  out.final_url = url.slice(0, 200);
  return json(out);
}
