// bvtech.org Worker entry (v1.97) — published by Pulse (services/tools_page.py).
// bvtech.org is a Cloudflare WORKERS static-assets site (wrangler.jsonc ->
// assets ./dist), so Pages "functions/" are ignored. Static assets are served
// FIRST by default; this Worker only runs for paths that match no file. It
// answers the free-tool API under /tools-api/* and hands everything else back
// to the static assets unchanged, so the rest of the site behaves as before.
import { onRequestGet as php2shellCheck } from "./php2shell-check.js";
import { onRequestPost as toolLead } from "./lead.js";

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    if (pathname === "/tools-api/php2shell-check" && request.method === "GET")
      return php2shellCheck({ request, env });
    if (pathname === "/tools-api/lead" && request.method === "POST")
      return toolLead({ request, env });
    if (pathname.startsWith("/tools-api/"))
      return new Response("Not found", { status: 404 });
    return env.ASSETS.fetch(request);
  },
};
