// BVTech Explore -> Answers widget feed (v1.103). Same-origin at
// /tools-api/answers; proxies the portal's public, read-only trending endpoint
// and caches it at the edge so the portal sees a trickle. Read-only — all
// posting happens on the portal where the session lives.
import { cached, getText, json } from "./feeds.js";

const PORTAL = "https://portal.bvtech.org/api/public-tools/answers-trending";

export async function onRequestGet() {
  try {
    const data = await cached("answers-trending-v1", 120, async () =>
      JSON.parse(await getText(PORTAL, 8000)));
    return json(data, 200, 120);
  } catch (e) {
    return json({ items: [], ask_url: "https://portal.bvtech.org/answers", total: 0 }, 200, 60);
  }
}
