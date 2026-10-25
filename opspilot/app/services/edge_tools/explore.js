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

export async function weather(lat, lon) {
  lat = Math.round(Math.max(-60, Math.min(70, +lat || 29.2)) * 10) / 10;
  lon = Math.round(Math.max(-180, Math.min(180, +lon || -96.3)) * 10) / 10;
  return cached(`explore-v1-wx-${lat}-${lon}`, 900, async () => {
    const r = JSON.parse(await getText("https://api.open-meteo.com/v1/forecast?latitude=" + lat
      + "&longitude=" + lon + "&current=temperature_2m,apparent_temperature,weather_code,"
      + "wind_speed_10m,relative_humidity_2m&daily=weather_code,temperature_2m_max,"
      + "temperature_2m_min,precipitation_probability_max&temperature_unit=fahrenheit"
      + "&wind_speed_unit=mph&timezone=auto&forecast_days=4"));
    const c = r.current || {}, d = r.daily || {};
    return {
      lat, lon, now: { temp: Math.round(c.temperature_2m), feels: Math.round(c.apparent_temperature),
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
      return json(await weather(url.searchParams.get("lat"), url.searchParams.get("lon")), 200, 600);
    if (what === "onthisday") return json(await onThisDay(), 200, 3600);
  } catch (e) {
    return json({ items: [], error: "temporarily unavailable" }, 200, 60);
  }
  return json({ error: "not found" }, 404, 0);
}
