// Cloudflare Pages Function — handles POST /api/order
// Auto-routed by Pages at /api/order. Set WEB3FORMS_KEY in Pages env vars.

export async function onRequestPost(context) {
  const { request, env } = context;
  try {
    const data = await request.json();
    // honeypot — bots fill hidden "company" field; humans don't
    if ((data.company || "").toString().trim() !== "") return json({ ok: true }, 200);

    const name = (data.name || "").toString().slice(0, 120).trim();
    const email = (data.email || "").toString().slice(0, 160).trim();
    const item = (data.item || "").toString().slice(0, 120).trim();
    const city = (data.city || "").toString().slice(0, 120).trim();
    const details = (data.details || "").toString().slice(0, 2000).trim();

    if (!name || !email || !item) return json({ error: "Missing required fields." }, 400);
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return json({ error: "Invalid email." }, 400);

    const labels = { seeds:"Heirloom seed packets", cuttings:"Rooted cuttings & pups", box:"Starter box", mix:"Custom mix", local:"Local El Campo pickup" };
    const itemLabel = labels[item] || item;

    const res = await fetch("https://api.web3forms.com/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        access_key: env.WEB3FORMS_KEY,
        subject: `New Texas Roots order — ${itemLabel} (${name})`,
        from_name: "tx-plants.com",
        name, email,
        message:
          `New order from tx-plants.com\n\n` +
          `Name:    ${name}\n` +
          `Email:   ${email}\n` +
          `Wants:   ${itemLabel}\n` +
          `Ship to: ${city || "—"}\n\n` +
          `Details:\n${details || "—"}\n`,
      }),
    });

    if (!res.ok) return json({ error: "Mail relay failed." }, 502);
    return json({ ok: true }, 200);
  } catch (e) {
    return json({ error: "Bad request." }, 400);
  }
}

function json(obj, status) {
  return new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json" } });
}
