// BVTech network tools at the edge (v1.102), under /tools-api/net/*.
//   whoami   - what the visitor's browser reveals (IP, city, ISP, device),
//              read from Cloudflare's own request metadata - no tracking, no
//              storage, shown back to the visitor so they see what sites see.
//   isdown   - is a public website up? one HEAD/GET from the edge, with timing.
// Both are read-only, rate-limited by Cloudflare, and never touch a database.
import { json } from "./feeds.js";

const HOST_RE = /^[a-z0-9.-]{3,253}$/;

export function cleanHost(h) {
  h = (h || "").trim().toLowerCase().replace(/^[a-z]+:\/\//, "").split("/")[0].split(":")[0];
  if (!HOST_RE.test(h) || h.includes("..") || !h.includes(".")) return null;
  if (/^[0-9.]+$/.test(h)) return null;                       // no IP literals (SSRF)
  if (h === "localhost" || /\.(local|internal|lan|home|corp|localhost)$/.test(h)) return null;
  return h;
}

export function whoami(request) {
  const cf = request.cf || {};
  const h = request.headers;
  const ua = h.get("user-agent") || "";
  const dev = /mobile|iphone|android/i.test(ua) ? "Phone/tablet"
    : /ipad|tablet/i.test(ua) ? "Tablet" : "Desktop/laptop";
  const os = /windows nt 10|windows nt 11/i.test(ua) ? "Windows"
    : /mac os x/i.test(ua) ? "macOS" : /android/i.test(ua) ? "Android"
    : /iphone|ipad|ios/i.test(ua) ? "iOS" : /linux/i.test(ua) ? "Linux" : "Unknown";
  const br = /edg\//i.test(ua) ? "Edge" : /chrome|crios/i.test(ua) ? "Chrome"
    : /firefox|fxios/i.test(ua) ? "Firefox" : /safari/i.test(ua) ? "Safari" : "Unknown";
  return {
    ip: h.get("cf-connecting-ip") || "",
    city: cf.city || "", region: cf.region || "", country: cf.country || "",
    postal: cf.postalCode || "", timezone: cf.timezone || "",
    isp: cf.asOrganization || "", asn: cf.asn ? "AS" + cf.asn : "",
    device: dev, os, browser: br,
    http: cf.httpProtocol || "", tls: cf.tlsVersion || "",
    lat: cf.latitude || "", lon: cf.longitude || "",
    ua: ua.slice(0, 180), dnt: h.get("dnt") === "1",
    lang: (h.get("accept-language") || "").split(",")[0],
  };
}

export async function isDown(host) {
  const clean = cleanHost(host);
  if (!clean) return { error: "Enter a website like example.com" };
  const url = "https://" + clean + "/";
  const t0 = Date.now();
  async function probe(method) {
    const r = await fetch(url, { method, redirect: "manual",
      headers: { "user-agent": "Mozilla/5.0 (compatible; BVTech-IsItDown/1.0; +https://bvtech.org/tools/)" },
      signal: AbortSignal.timeout(9000), cf: { cacheTtl: 0 } });
    return r;
  }
  try {
    let r;
    try { r = await probe("HEAD"); } catch (e) { r = await probe("GET"); }
    const ms = Date.now() - t0;
    const code = r.status;
    const up = code < 500 || code === 503 ? code < 500 : false;
    const redirect = code >= 300 && code < 400 ? r.headers.get("location") || "" : "";
    return {
      host: clean, up: code > 0 && code < 500, code, ms,
      server: r.headers.get("server") || "", redirect,
      verdict: code === 0 ? "No response" : code < 400 ? "Up and reachable"
        : code < 500 ? "Reachable (returns " + code + ")" : "Down or erroring (" + code + ")",
      note: "Checked from Cloudflare's network, not your location. If it loads for the "
        + "world but not you, it's likely your network, DNS, or ISP.",
    };
  } catch (e) {
    const ms = Date.now() - t0;
    return { host: clean, up: false, code: 0, ms,
      verdict: "No response in 9 seconds",
      note: "The site didn't answer from Cloudflare's network - it may be down for "
        + "everyone, blocking automated requests, or very slow." };
  }
}

// Same-origin speed test: GET returns N random-ish bytes (download); POST
// absorbs the body (upload). No third party, no CSP change. Capped at 25 MB.
const MAXB = 25 * 1024 * 1024;
function downloadBytes(n) {
  n = Math.max(0, Math.min(MAXB, parseInt(n, 10) || 0));
  const chunk = new Uint8Array(65536);
  for (let i = 0; i < chunk.length; i++) chunk[i] = (i * 31 + 7) & 255;
  let left = n;
  const stream = new ReadableStream({
    pull(c) {
      if (left <= 0) { c.close(); return; }
      const size = Math.min(chunk.length, left);
      c.enqueue(size === chunk.length ? chunk : chunk.subarray(0, size));
      left -= size;
    },
  });
  return new Response(stream, { headers: { "content-type": "application/octet-stream",
    "content-length": String(n), "cache-control": "no-store, no-transform",
    "x-content-type-options": "nosniff" } });
}

export async function onRequestGet({ request }) {
  const url = new URL(request.url);
  const what = url.pathname.split("/").pop();
  if (what === "whoami") return json(whoami(request), 200, 0);
  if (what === "isdown") return json(await isDown(url.searchParams.get("host")), 200, 0);
  if (what === "speedtest") return downloadBytes(url.searchParams.get("bytes"));
  return json({ error: "not found" }, 404, 0);
}

export async function onRequestPost({ request }) {
  // upload test: read and discard the body, report how many bytes arrived.
  let total = 0;
  const reader = request.body && request.body.getReader();
  if (reader) {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.length;
      if (total > MAXB) break;
    }
  }
  return json({ bytes: total }, 200, 0);
}
