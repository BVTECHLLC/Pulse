// BVTech Explore widgets (v1.102): NASA image of the day, upcoming rocket
// launches, local weather and "on this day in tech", served same-origin under
// /tools-api/explore/*. Every source is free and keyless, and every answer is
// cached at the edge so the upstream APIs see a trickle, not our traffic.
// Images are relayed through /tools-api/explore/img from an allowlist of
// hosts, so the site's CSP never has to open up to third-party images.
import { cached, getText, json, decode, BLOCK, TECHY } from "./feeds.js";

const IMG_HOSTS = ["https://www.nasa.gov/wp-content/uploads/",
                   "https://thespacedevs-prod.nyc3.digitaloceanspaces.com/"];
export const imgUrl = (u) => (IMG_HOSTS.some((h) => (u || "").startsWith(h))
  ? "/tools-api/explore/img?u=" + encodeURIComponent(u) : "");

export async function photos() {
  return cached("explore-v1-photos", 3 * 3600, async () => {
    const xml = await getText("https://www.nasa.gov/feeds/iotd-feed/");
    const items = (xml.match(/<item[\s>][\s\S]*?<\/item>/gi) || []).slice(0, 8).map((b) => ({
      title: decode((b.match(/<title>([\s\S]*?)<\/title>/i) || [])[1]),
      desc: decode((b.match(/<description>([\s\S]*?)<\/description>/i) || [])[1]).slice(0, 260),
      link: decode((b.match(/<link>([\s\S]*?)<\/link>/i) || [])[1]),
      img: imgUrl((b.match(/<enclosure[^>]*url="([^"]+)"/i) || [])[1]),
    })).filter((p) => p.title && p.img);
    return { items };
  });
}

export async function launches() {
  return cached("explore-v1-launches", 3600, async () => {
    const r = JSON.parse(await getText(
      "https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=12&mode=list&hide_recent_previous=true"));
    const now = Date.now() - 3 * 3600 * 1000;
    const items = (r.results || []).filter((l) => Date.parse(l.net) > now).slice(0, 6).map((l) => ({
      name: l.name, net: l.net, provider: l.lsp_name, where: l.location,
      status: (l.status || {}).abbrev || "", mission: l.mission_type || "",
      img: imgUrl(l.image),
    }));
    return { items };
  });
}

const WMO = { 0: ["Clear", "☀️"], 1: ["Mostly clear", "🌤️"], 2: ["Partly cloudy", "⛅"],
  3: ["Cloudy", "☁️"], 45: ["Fog", "🌫️"], 48: ["Fog", "🌫️"], 51: ["Drizzle", "🌦️"],
  53: ["Drizzle", "🌦️"], 55: ["Drizzle", "🌦️"], 61: ["Rain", "🌧️"], 63: ["Rain", "🌧️"],
  65: ["Heavy rain", "🌧️"], 71: ["Snow", "🌨️"], 73: ["Snow", "🌨️"], 75: ["Snow", "❄️"],
  80: ["Showers", "🌦️"], 81: ["Showers", "🌧️"], 82: ["Downpours", "⛈️"], 95: ["Storms", "⛈️"],
  96: ["Storms", "⛈️"], 99: ["Storms", "⛈️"] };
export const sky = (c) => WMO[c] || ["—", "🌡️"];

export async function weather(lat, lon, cf) {
  // Default to the VISITOR'S location (Cloudflare IP geo), not a fixed city, so
  // the forecast matches where the reader actually is. GPS (if allowed) refines it.
  cf = cf || {};
  const dLat = cf.latitude != null ? +cf.latitude : 29.2;
  const dLon = cf.longitude != null ? +cf.longitude : -96.3;
  const place = [cf.city, cf.region].filter(Boolean).join(", ");
  lat = Math.round(Math.max(-60, Math.min(70, +lat || dLat)) * 10) / 10;
  lon = Math.round(Math.max(-180, Math.min(180, +lon || dLon)) * 10) / 10;
  return cached(`explore-v1-wx-${lat}-${lon}`, 900, async () => {
    const r = JSON.parse(await getText("https://api.open-meteo.com/v1/forecast?latitude=" + lat
      + "&longitude=" + lon + "&current=temperature_2m,apparent_temperature,weather_code,"
      + "wind_speed_10m,relative_humidity_2m&daily=weather_code,temperature_2m_max,"
      + "temperature_2m_min,precipitation_probability_max&temperature_unit=fahrenheit"
      + "&wind_speed_unit=mph&timezone=auto&forecast_days=4"));
    const c = r.current || {}, d = r.daily || {};
    return {
      lat, lon, place: place || "", now: { temp: Math.round(c.temperature_2m), feels: Math.round(c.apparent_temperature),
        wind: Math.round(c.wind_speed_10m), humidity: c.relative_humidity_2m,
        sky: sky(c.weather_code) },
      days: (d.time || []).map((t, i) => ({ day: t, hi: Math.round(d.temperature_2m_max[i]),
        lo: Math.round(d.temperature_2m_min[i]), rain: d.precipitation_probability_max[i],
        sky: sky(d.weather_code[i]) })),
    };
  });
}

// "On this day" from Wikipedia, kept to upbeat tech & science moments.
export function techMoments(events) {
  return (events || []).filter((e) => TECHY.test(e.text) && !BLOCK.test(e.text))
    .map((e) => ({ year: e.year, text: e.text,
      link: ((e.pages || [])[0] || {}).content_urls?.desktop?.page || "" }))
    .slice(0, 6);
}

export async function onThisDay(now = new Date()) {
  const ct = new Date(now.toLocaleString("en-US", { timeZone: "America/Chicago" }));
  const mm = String(ct.getMonth() + 1).padStart(2, "0"), dd = String(ct.getDate()).padStart(2, "0");
  return cached(`explore-v1-otd-${mm}${dd}`, 6 * 3600, async () => {
    const r = JSON.parse(await getText(
      `https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/events/${mm}/${dd}`));
    return { date: `${mm}-${dd}`, items: techMoments(r.events) };
  });
}

// Tech markets ticker: a handful of big tech names + crypto. Both feeds are
// free and keyless; Yahoo's chart endpoint needs no crumb, CoinGecko's simple
// price is open. Cached 3 min at the edge so upstreams see a trickle.
const STOCKS = [["AAPL", "Apple"], ["MSFT", "Microsoft"], ["NVDA", "Nvidia"],
  ["GOOGL", "Alphabet"], ["AMZN", "Amazon"], ["TSLA", "Tesla"], ["META", "Meta"],
  ["AMD", "AMD"]];

export async function markets() {
  return cached("explore-v2-markets", 180, async () => {
    const out = [];
    const stk = await Promise.allSettled(STOCKS.map(async ([sym, name]) => {
      const r = JSON.parse(await getText(
        "https://query1.finance.yahoo.com/v8/finance/chart/" + sym + "?range=1d&interval=1d", 7000));
      const m = (((r.chart || {}).result || [])[0] || {}).meta || {};
      const price = m.regularMarketPrice;
      const prev = m.chartPreviousClose != null ? m.chartPreviousClose : m.previousClose;
      if (price == null) throw new Error("no price");
      const chg = prev ? ((price - prev) / prev) * 100 : 0;
      return { sym, name, price, chg, kind: "stock" };
    }));
    for (const s of stk) if (s.status === "fulfilled") out.push(s.value);
    try {
      const cg = JSON.parse(await getText(
        "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana"
        + "&vs_currencies=usd&include_24hr_change=true", 7000));
      for (const [id, sym, name] of [["bitcoin", "BTC", "Bitcoin"],
        ["ethereum", "ETH", "Ethereum"], ["solana", "SOL", "Solana"]]) {
        if (cg[id] && cg[id].usd != null)
          out.push({ sym, name, price: cg[id].usd, chg: cg[id].usd_24h_change || 0, kind: "crypto" });
      }
    } catch (e) { /* crypto is best-effort */ }
    return { items: out, at: Date.now() };
  });
}

// "The BVTech Take" — our OWN original commentary, surfaced from our blog. We
// read our own /blog/ index (a static asset) and return the latest posts, so
// Explore sends readers to our authored takes (sources cited inside each one),
// never to scraped article text.
export async function takes() {
  return cached("explore-v2-takes", 1200, async () => {
    const html = await getText("https://bvtech.org/blog/", 7000);
    const cards = html.match(/<a[^>]*class="blog-card"[\s\S]*?<\/a>/gi) || [];
    const items = cards.map((c) => {
      const href = (c.match(/href="([^"]+)"/i) || [])[1] || "";
      const date = decode((c.match(/class="meta"[^>]*>([\s\S]*?)<\/div>/i) || [])[1] || "");
      const title = decode((c.match(/<h3[^>]*>([\s\S]*?)<\/h3>/i) || [])[1] || "");
      const excerpt = decode((c.match(/<p[^>]*>([\s\S]*?)<\/p>/i) || [])[1] || "");
      return { href, date, title, excerpt, dispatch: /bvtech-dispatch-/i.test(href) };
    }).filter((x) => /^https?:\/\//.test(x.href) && x.title);
    // dispatch ("our take") posts first, then the rest, keeping order within each
    const ordered = items.filter((x) => x.dispatch).concat(items.filter((x) => !x.dispatch));
    return { items: ordered.slice(0, 7), at: Date.now() };
  });
}

async function img(request) {
  const u = new URL(request.url).searchParams.get("u") || "";
  if (!IMG_HOSTS.some((h) => u.startsWith(h)) || u.includes(".."))
    return new Response("not allowed", { status: 403 });
  const r = await fetch(u, { cf: { cacheTtl: 86400, cacheEverything: true },
                             signal: AbortSignal.timeout(8000) });
  const type = r.headers.get("content-type") || "";
  if (!r.ok || !type.startsWith("image/")) return new Response("unavailable", { status: 502 });
  return new Response(r.body, { headers: { "content-type": type,
    "cache-control": "public, max-age=86400", "x-content-type-options": "nosniff" } });
}

export async function onRequestGet({ request }) {
  const url = new URL(request.url);
  const what = url.pathname.split("/").pop();
  try {
    if (what === "img") return await img(request);
    if (what === "photos") return json(await photos(), 200, 1800);
    if (what === "launches") return json(await launches(), 200, 900);
    if (what === "weather")
      return json(await weather(url.searchParams.get("lat"), url.searchParams.get("lon"),
                                request.cf), 200, 600);
    if (what === "onthisday") return json(await onThisDay(), 200, 3600);
    if (what === "markets") return json(await markets(), 200, 120);
    if (what === "takes") return json(await takes(), 200, 600);
  } catch (e) {
    return json({ items: [], error: "temporarily unavailable" }, 200, 60);
  }
  return json({ error: "not found" }, 404, 0);
}
