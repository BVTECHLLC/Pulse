// BVTech free-tool lead relay — Cloudflare Pages Function (v1.96).
// Served same-origin at bvtech.org/tools-api/lead (the site CSP only allows
// 'self'), then forwarded server-side to the Pulse portal's /lead endpoint,
// which files the visitor in the CRM. Any failure answers with a plain
// "email us" message so the page never dead-ends.

const PORTAL_LEAD = "https://portal.bvtech.org/api/public-tools/lead";
const FALLBACK = { ok: false, error: "Could not send. Please email help@bvtech.org." };

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
}

export async function onRequestPost({ request }) {
  const body = (await request.text()).slice(0, 4000);
  try {
    JSON.parse(body);
  } catch (e) {
    return json({ ok: false, error: "bad request" }, 400);
  }
  try {
    const r = await fetch(PORTAL_LEAD, {
      method: "POST", body, signal: AbortSignal.timeout(8000),
      headers: { "content-type": "application/json", "origin": "https://bvtech.org" } });
    const text = await r.text();
    try { return json(JSON.parse(text)); } catch (e) { return json(FALLBACK, 502); }
  } catch (e) {
    return json(FALLBACK, 502);
  }
}
