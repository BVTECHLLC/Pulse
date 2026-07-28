// Cloudflare Pages Function — GET /api/weather?lat=..&lon=..
// Proxies Open-Meteo (free, no API key, no rate cap for this use).
// Returns current conditions + 7-day daily forecast, normalized for the client.
// Edge-cached 15 min so repeat visits are instant and Open-Meteo is never hammered.

export async function onRequestGet(context) {
  const { request } = context;
  const url = new URL(request.url);

  // Validate + clamp coordinates; default to El Campo, TX (the greenhouse).
  let lat = parseFloat(url.searchParams.get("lat"));
  let lon = parseFloat(url.searchParams.get("lon"));
  if (!isFinite(lat) || !isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
    lat = 29.1966; lon = -96.2697; // El Campo, TX
  }
  lat = Math.round(lat * 10000) / 10000;
  lon = Math.round(lon * 10000) / 10000;

  const cacheKey = new Request(`https://cache.tx-plants.com/weather?lat=${lat}&lon=${lon}`, request);
  const cache = caches.default;
  let cached = await cache.match(cacheKey);
  if (cached) return cached;

  const params = new URLSearchParams({
    latitude: lat,
    longitude: lon,
    current: "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,wind_speed_10m,wind_direction_10m",
    daily: "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_speed_10m_max,sunrise,sunset",
    temperature_unit: "fahrenheit",
    wind_speed_unit: "mph",
    precipitation_unit: "inch",
    timezone: "auto",
    forecast_days: "7",
  });

  let upstream;
  try {
    upstream = await fetch(`https://api.open-meteo.com/v1/forecast?${params}`, {
      cf: { cacheTtl: 900, cacheEverything: true },
    });
  } catch (e) {
    return json({ error: "weather_unavailable" }, 502);
  }
  if (!upstream || !upstream.ok) {
    return json({ error: "weather_unavailable" }, 502);
  }

  let raw;
  try { raw = await upstream.json(); }
  catch (e) { return json({ error: "weather_unavailable" }, 502); }

  const out = normalize(raw, lat, lon);
  const res = json(out, 200, { "Cache-Control": "public, max-age=900, s-maxage=900" });
  context.waitUntil(cache.put(cacheKey, res.clone()));
  return res;
}

function normalize(d, lat, lon) {
  const c = d.current || {};
  const dy = d.daily || {};
  const days = (dy.time || []).map((t, i) => ({
    date: t,
    code: dy.weather_code?.[i],
    hi: round(dy.temperature_2m_max?.[i]),
    lo: round(dy.temperature_2m_min?.[i]),
    pop: dy.precipitation_probability_max?.[i] ?? null,
    precip: dy.precipitation_sum?.[i] ?? null,
    wind: round(dy.wind_speed_10m_max?.[i]),
    sunrise: dy.sunrise?.[i] || null,
    sunset: dy.sunset?.[i] || null,
  }));
  return {
    ok: true,
    lat, lon,
    timezone: d.timezone || "auto",
    elevation: d.elevation ?? null,
    current: {
      temp: round(c.temperature_2m),
      feels: round(c.apparent_temperature),
      humidity: c.relative_humidity_2m ?? null,
      precip: c.precipitation ?? null,
      code: c.weather_code,
      wind: round(c.wind_speed_10m),
      windDir: c.wind_direction_10m ?? null,
      isDay: c.is_day === 1,
      time: c.time || null,
    },
    days,
    fetched: new Date().toISOString(),
  };
}

function round(n) { return (n === null || n === undefined || !isFinite(n)) ? null : Math.round(n); }

function json(obj, status, extra) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*", ...(extra || {}) },
  });
}
