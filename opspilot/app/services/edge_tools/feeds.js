// BVTech Explore - headline aggregator (v1.102), served same-origin at
// bvtech.org/tools-api/feeds?cat=<category>. Published by Pulse
// (services/destination.py).
//
// Headlines ONLY (title, source, time, link out to the publisher) - never the
// article text - so publishers get the click and Google sees no copied content.
// The Explore page renders them client-side. A keyword filter keeps the page
// fun: no politics, no tragedies. Each category is cached at the edge for 15
// minutes, so publishers see at most a few requests per hour per data center.

export const FEEDS = {
  tech: [["The Verge", "https://www.theverge.com/rss/index.xml"],
         ["Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"],
         ["TechCrunch", "https://techcrunch.com/feed/"],
         ["Engadget", "https://www.engadget.com/rss.xml"]],
  tesla: [["Electrek", "https://electrek.co/guides/tesla/feed/"],
          ["Teslarati", "https://www.teslarati.com/feed/"],
          ["Not a Tesla App", "https://www.notateslaapp.com/rss"],
          ["InsideEVs", "https://insideevs.com/rss/news/all/"]],
  space: [["NASA", "https://www.nasa.gov/news-release/feed/"],
          ["Space.com", "https://www.space.com/feeds/news"]],
  ai: [["The Verge", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"],
       ["TechCrunch", "https://techcrunch.com/feed/"],
       ["Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"]],
  science: [["ScienceDaily", "https://www.sciencedaily.com/rss/top/technology.xml"],
            ["Live Science", "https://www.livescience.com/feeds/all"],
            ["Popular Science", "https://www.popsci.com/feed/"]],
  gadgets: [["9to5Mac", "https://9to5mac.com/feed/"],
            ["Android Authority", "https://www.androidauthority.com/feed/"],
            ["Engadget", "https://www.engadget.com/rss.xml"]],
  gaming: [["IGN", "https://feeds.ign.com/ign/all"]],
  security: [["BleepingComputer", "https://www.bleepingcomputer.com/feed/"],
             ["The Hacker News", "https://feeds.feedburner.com/TheHackersNews"]],
  good: [["Good News Network", "https://www.goodnewsnetwork.org/feed/"]],
  hn: [["Hacker News", "https://hnrss.org/frontpage"]],
};

// Keep it fun: politics, violence and disasters stay off the page.
// Whole words, plus a few stems (\w* suffix) - "war" must not block "warning".
const BLOCK_WORDS = ["trump", "biden", "harris", "vance", "obama", "democrats?", "republicans?",
  "gop", "maga", "elections?", "ballots?", "congress", "white house", "partisan",
  "wars?", "warfare", "missiles?", "gaza", "israel", "hamas", "putin", "iran",
  "abortion", "tariffs?", "sanctions?", "kill", "killed", "kills", "killing", "dead",
  "deaths?", "dies", "died", "die", "murders?", "shooting", "shooter", "gunman",
  "stabbing", "suicide", "bombs?", "bombing", "massacre", "hostages?", "fatal",
  "crash", "crashes", "crashed", "lawsuits?", "sued", "sues", "indicted", "arrested",
  "convicted", "prison", "jail", "nazis?", "sexual", "abuse", "porn", "nsfw",
  "layoffs?", "laid off"];
const BLOCK_STEMS = ["senat", "politic", "militar", "ukrain", "russia", "immigra", "deport",
  "terror", "fatalit", "injur", "racis"];
export const BLOCK = new RegExp("\\b(?:(?:" + BLOCK_WORDS.join("|") + ")\\b|(?:"
  + BLOCK_STEMS.join("|") + ")\\w*)", "i");

// Positive tech/science signals for Wikipedia's "on this day" (which is mostly
// grim history otherwise).
export const TECHY = /\b(launch|launched|releases|released|invent|invented|patent|patented|computer|computing|internet|world wide web|software|satellite|rocket|spacecraft|spaceflight|astronaut|cosmonaut|moon landing|mars|orbit|telescope|discover|discovered|microprocessor|microsoft|apple inc|ibm|google|intel|nintendo|sega|atari|video game|console|television|telephone|robot|robotics|tesla|edison|wright brothers|aviation|airplane|nasa|apollo|soyuz|sputnik|hubble|voyager|semiconductor|transistor|email|smartphone|iphone|android|windows (?:xp|95|98|vista|7|10|11)|linux|unix|wikipedia|world record)\b/i;

const UA = "Mozilla/5.0 (compatible; BVTech-Explore/1.0; +https://bvtech.org/explore/)";
const ENT = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ", hellip: "…",
  rsquo: "’", lsquo: "‘", rdquo: "”", ldquo: "“", ndash: "–", mdash: "—" };

export function decode(s) {
  return String(s || "")
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/<[^>]+>/g, "")
    .replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCodePoint(parseInt(h, 16)))
    .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(+d))
    .replace(/&([a-z]+);/gi, (m, n) => ENT[n.toLowerCase()] ?? m)
    .replace(/\s+/g, " ").trim();
}

function tag(block, name) {
  const m = block.match(new RegExp(`<${name}(?:\\s[^>]*)?>([\\s\\S]*?)</${name}>`, "i"));
  return m ? m[1] : "";
}

// RSS 2.0 and Atom, by regex: Workers have no DOMParser.
export function parseFeed(xml, source) {
  const out = [];
  const blocks = xml.match(/<item[\s>][\s\S]*?<\/item>/gi)
    || xml.match(/<entry[\s>][\s\S]*?<\/entry>/gi) || [];
  for (const b of blocks.slice(0, 40)) {
    const title = decode(tag(b, "title"));
    let link = decode(tag(b, "link"));
    if (!/^https?:\/\//i.test(link)) {
      const alt = b.match(/<link[^>]*rel=["']alternate["'][^>]*href=["']([^"']+)/i)
        || b.match(/<link[^>]*href=["']([^"']+)/i);
      link = alt ? alt[1] : "";
    }
    if (!/^https:\/\//i.test(link) && /^http:\/\//i.test(link)) link = link.replace(/^http:/i, "https:");
    const when = decode(tag(b, "pubDate") || tag(b, "published") || tag(b, "updated")
      || tag(b, "dc:date"));
    const t = Date.parse(when);
    const img = (b.match(/<enclosure[^>]*url=["']([^"']+)["'][^>]*type=["']image/i)
      || b.match(/<media:(?:content|thumbnail)[^>]*url=["']([^"']+)/i) || [])[1] || "";
    if (title && /^https:\/\//i.test(link))
      out.push({ title, link, source, t: isNaN(t) ? 0 : t, img,
                 desc: decode(tag(b, "description")).slice(0, 220) });
  }
  return out;
}

export function friendly(items) {
  const seen = new Set();
  return items.filter((it) => {
    if (BLOCK.test(it.title)) return false;
    const key = it.title.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().slice(0, 60);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// Edge cache helper: one synthetic URL per key, stored with an s-maxage.
export async function cached(key, ttl, make) {
  const cache = typeof caches !== "undefined" ? caches.default : null;
  const ck = new Request(`https://bvtech.org/__edge-cache/${key}`);
  if (cache) {
    const hit = await cache.match(ck);
    if (hit) return hit.json();
  }
  const data = await make();
  if (cache && data && !data.error) {
    await cache.put(ck, new Response(JSON.stringify(data), {
      headers: { "content-type": "application/json", "cache-control": `public, s-maxage=${ttl}` } }));
  }
  return data;
}

export async function getText(url, ms = 6000) {
  const r = await fetch(url, { headers: { "user-agent": UA, accept: "*/*" },
                               signal: AbortSignal.timeout(ms), redirect: "follow" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.text();
}

export function json(obj, status = 200, maxAge = 300) {
  return new Response(JSON.stringify(obj), { status, headers: {
    "content-type": "application/json; charset=utf-8",
    "cache-control": maxAge ? `public, max-age=${maxAge}` : "no-store",
    "x-content-type-options": "nosniff" } });
}

export async function category(cat, limit = 12) {
  const list = FEEDS[cat];
  if (!list) return { error: "unknown category" };
  return cached(`feeds-v1-${cat}`, 900, async () => {
    const got = await Promise.allSettled(list.map(([name, url]) =>
      getText(url).then((x) => parseFeed(x, name))));
    let items = [];
    for (const g of got) if (g.status === "fulfilled") items = items.concat(g.value);
    if (cat === "ai") items = items.filter((i) => /\b(ai|a\.i\.|openai|chatgpt|gpt|llm|gemini|claude|anthropic|copilot|machine learning|neural|robot|model)\b/i.test(i.title));
    items = friendly(items).sort((a, b) => b.t - a.t).slice(0, limit)
      .map(({ title, link, source, t }) => ({ title, link, source, t }));
    return { cat, items, at: Date.now() };
  });
}

export async function onRequestGet({ request }) {
  const cat = new URL(request.url).searchParams.get("cat") || "tech";
  try {
    const data = await category(cat);
    return json(data, data.error ? 400 : 200);
  } catch (e) {
    return json({ cat, items: [], error: "feeds unavailable" }, 200, 60);
  }
}
