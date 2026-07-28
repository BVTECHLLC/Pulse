// Cloudflare Pages Function — community board at /api/community
// GET  -> returns array of posts (newest first, capped)
// POST -> saves a post
// Requires a KV namespace bound as COMMUNITY in the Pages project settings.
// If no KV is bound, GET returns [] and POST returns ok (board falls back to in-session).

const MAX_POSTS = 200;

export async function onRequestGet(context) {
  const { env } = context;
  if (!env.COMMUNITY) return json([], 200);
  try {
    const raw = await env.COMMUNITY.get("threads");
    const posts = raw ? JSON.parse(raw) : [];
    return json(posts, 200);
  } catch (e) {
    return json([], 200);
  }
}

export async function onRequestPost(context) {
  const { request, env } = context;
  try {
    const p = await request.json();
    // basic validation + sanitation
    const clean = {
      id: String(p.id || "u" + Date.now()).slice(0, 40),
      name: String(p.name || "Anonymous").slice(0, 40),
      cat: ["starting", "help", "swap", "showoff"].includes(p.cat) ? p.cat : "starting",
      title: String(p.title || "").slice(0, 90),
      body: String(p.body || "").slice(0, 600),
      ts: Number(p.ts) || Date.now(),
      replies: Array.isArray(p.replies)
        ? p.replies.slice(0, 50).map(r => ({
            name: String(r.name || "Anonymous").slice(0, 40),
            body: String(r.body || "").slice(0, 300),
          }))
        : [],
    };
    if (!clean.title || !clean.body) return json({ error: "Missing title/body" }, 400);
    if (!env.COMMUNITY) return json({ ok: true, stored: false }, 200);

    const raw = await env.COMMUNITY.get("threads");
    let posts = raw ? JSON.parse(raw) : [];
    // upsert by id (so reply updates replace the post)
    posts = posts.filter(x => x.id !== clean.id);
    posts.unshift(clean);
    posts = posts.slice(0, MAX_POSTS);
    await env.COMMUNITY.put("threads", JSON.stringify(posts));
    return json({ ok: true, stored: true }, 200);
  } catch (e) {
    return json({ error: "Bad request" }, 400);
  }
}

function json(obj, status) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}
