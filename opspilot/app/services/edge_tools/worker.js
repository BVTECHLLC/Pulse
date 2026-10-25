// bvtech.org Worker entry (v1.102) — published by Pulse (services/tools_page.py
// and services/destination.py). bvtech.org is a Cloudflare WORKERS static-assets
// site (wrangler.jsonc -> assets ./dist), so Pages "functions/" are ignored.
// Static assets are served FIRST by default; this Worker only runs for paths
// that match no file. It answers the free-tool + Explore API under /tools-api/*
// and hands everything else back to the static assets unchanged, so the rest of
// the site behaves exactly as before.
import { onRequestGet as php2shellCheck } from "./php2shell-check.js";
import { onRequestPost as toolLead } from "./lead.js";
import { onRequestGet as feedsGet } from "./feeds.js";
import { onRequestGet as exploreGet } from "./explore.js";
import { onRequestGet as netGet, onRequestPost as netPost } from "./netinfo.js";
import { onRequestGet as labGet, onRequestPost as labPost } from "./labs.js";
import { onRequestGet as dailyGet, onRequestPost as dailyPost } from "./daily.js";

const CORS = { "access-control-allow-origin": "https://bvtech.org",
  "access-control-allow-methods": "GET,POST,OPTIONS",
  "access-control-allow-headers": "content-type", "vary": "Origin" };

export default {
  async fetch(request, env, ctx) {
    const { pathname } = new URL(request.url);
    const m = request.method;
    if (pathname.startsWith("/tools-api/")) {
      if (m === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
      const r = { request, env, ctx };
      request.ctx = ctx;
      let resp = null;
      try {
        if (pathname === "/tools-api/php2shell-check" && m === "GET") resp = await php2shellCheck(r);
        else if (pathname === "/tools-api/lead" && m === "POST") resp = await toolLead(r);
        else if (pathname === "/tools-api/feeds" && m === "GET") resp = await feedsGet(r);
        else if (pathname.startsWith("/tools-api/explore/") && m === "GET") resp = await exploreGet(r);
        else if (pathname.startsWith("/tools-api/net/") && m === "GET") resp = await netGet(r);
        else if (pathname === "/tools-api/net/speedtest" && m === "POST") resp = await netPost(r);
        else if (pathname === "/tools-api/lab" && m === "GET") resp = await labGet(r);
        else if (pathname === "/tools-api/lab/grade" && m === "POST") resp = await labPost(r);
        else if (pathname === "/tools-api/daily" && m === "GET") resp = await dailyGet(r);
        else if ((pathname === "/tools-api/daily/grade" || pathname === "/tools-api/notfound")
                 && m === "POST") resp = await dailyPost(r);
      } catch (e) {
        resp = new Response(JSON.stringify({ error: "temporarily unavailable" }),
          { status: 200, headers: { "content-type": "application/json" } });
      }
      if (!resp) return new Response("Not found", { status: 404 });
      const out = new Response(resp.body, resp);
      for (const [k, v] of Object.entries(CORS)) out.headers.set(k, v);
      return out;
    }
    return env.ASSETS.fetch(request);
  },
};
