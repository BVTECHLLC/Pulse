// BVTech Explore - Daily Byte game + tech tip + 404 telemetry (v1.102).
//   /tools-api/daily        -> today's trivia question (no answer) + tip
//   /tools-api/daily/grade  -> grade an answer (POST), answer stays server-side
//   /tools-api/notfound     -> the site 404 page reports the missing path here
//                              (fire-and-forget to the portal; feeds the scanner)
import { json } from "./feeds.js";

// Everyone gets the SAME question each day (so people can compare), rotating
// through the pool by day number. Answers live here, never in the page.
export const TRIVIA = [
  { q: "What does the 'S' in HTTPS stand for?", o: ["Secure", "Server", "Standard", "Simple"], a: 0,
    why: "HTTPS = HTTP Secure: the padlock means traffic is encrypted in transit." },
  { q: "A 'phishing' email tries to do what?", o: ["Trick you into giving up info or clicking a bad link", "Catch actual fish", "Speed up your PC", "Back up your files"], a: 0,
    why: "Phishing baits you into revealing passwords or installing malware. Slow down and verify." },
  { q: "Which is the STRONGEST passphrase?", o: ["correct-horse-battery-staple-2026", "P@ss1", "qwerty", "your pet's name"], a: 0,
    why: "Length beats complexity. Four random words are far harder to crack than 'P@ss1'." },
  { q: "What's the safest way to store many passwords?", o: ["A reputable password manager", "A sticky note on the monitor", "The same password everywhere", "A text file named passwords.txt"], a: 0,
    why: "A password manager makes every login long, unique and remembered for you." },
  { q: "MFA (multi-factor authentication) protects you by...", o: ["Requiring a second proof beyond your password", "Making your password longer", "Hiding your IP address", "Blocking all email"], a: 0,
    why: "Even if your password leaks, the attacker still can't pass the second factor." },
  { q: "Roughly how many miles above Earth does the ISS orbit?", o: ["~250 miles", "~25 miles", "~2,500 miles", "~25,000 miles"], a: 0,
    why: "The International Space Station orbits in 'low Earth orbit', about 250 miles up." },
  { q: "What company makes the 'Cybertruck'?", o: ["Tesla", "Ford", "Rivian", "Toyota"], a: 0,
    why: "Tesla's stainless-steel Cybertruck is one of the most recognizable EVs on the road." },
  { q: "'The cloud' really means...", o: ["Someone else's computers you access over the internet", "Water vapor", "Your local hard drive", "A type of Wi-Fi"], a: 0,
    why: "Cloud services run on data-center servers you reach over the internet." },
  { q: "A VPN mainly does what?", o: ["Encrypts your connection and hides your IP from sites", "Makes internet faster everywhere", "Removes all viruses", "Gives free Wi-Fi"], a: 0,
    why: "A VPN tunnels your traffic through an encrypted link - good on public Wi-Fi." },
  { q: "Ransomware is malware that...", o: ["Locks your files and demands payment", "Speeds up your PC", "Blocks spam", "Backs up your data"], a: 0,
    why: "Ransomware encrypts your data and extorts you. Offline backups are the cure." },
  { q: "What does 'open source' software mean?", o: ["Its code is public and anyone can inspect it", "It's always free of bugs", "It only runs on Linux", "It has no license"], a: 0,
    why: "Open-source code can be read and audited by anyone - Linux and Firefox are examples." },
  { q: "Which planet is NASA's Perseverance rover exploring?", o: ["Mars", "Venus", "The Moon", "Jupiter"], a: 0,
    why: "Perseverance has been hunting for ancient life in Mars' Jezero Crater since 2021." },
  { q: "A 'zero-day' vulnerability is one that...", o: ["Is exploited before a fix exists", "Takes zero days to fix", "Only affects old PCs", "Can't be exploited"], a: 0,
    why: "Defenders have had 'zero days' to patch it - which is why fast updates matter." },
  { q: "What makes a website address trustworthy?", o: ["Carefully reading the exact domain name", "A padlock icon alone", "It looks professional", "It loads fast"], a: 0,
    why: "The padlock only means encryption - scammers have it too. Read the domain letter by letter." },
  { q: "Who should you call first if your business is hit by a cyberattack?", o: ["Your IT/security provider", "The software vendor's sales line", "A random forum", "Nobody - wait it out"], a: 0,
    why: "Speed limits the damage. Have your IT partner's number before you ever need it." },
];

export const TIPS = [
  "Turn on automatic updates. Most breaches exploit bugs that were already patched.",
  "Back up the 3-2-1 way: 3 copies, 2 kinds of media, 1 kept offline or off-site.",
  "Use a password manager. One strong unique password per site, remembered for you.",
  "Turn on MFA for email and banking first - those unlock everything else.",
  "Hover over links before clicking. The real destination shows in the corner.",
  "On public Wi-Fi, use a VPN or your phone's hotspot for anything sensitive.",
  "Lock your screen when you step away. Windows+L on a PC, Control+Command+Q on a Mac.",
  "Verify payment-change requests by phone, using a number you already had - not the email.",
  "Keep one email just for logins, and never post it publicly.",
  "If an offer or a warning rushes you, slow down - urgency is the scammer's favorite tool.",
];

function dayNumber(now = new Date()) {
  const ct = new Date(now.toLocaleString("en-US", { timeZone: "America/Chicago" }));
  return Math.floor(Date.UTC(ct.getFullYear(), ct.getMonth(), ct.getDate()) / 86400000);
}

export function today(now = new Date()) {
  const n = dayNumber(now);
  const q = TRIVIA[n % TRIVIA.length];
  return {
    day: n,
    date: new Date(now.toLocaleString("en-US", { timeZone: "America/Chicago" }))
      .toISOString().slice(0, 10),
    tip: TIPS[n % TIPS.length],
    question: { q: q.q, options: q.o },
    total: TRIVIA.length,
  };
}

export function gradeToday(choice, now = new Date()) {
  const q = TRIVIA[dayNumber(now) % TRIVIA.length];
  const correct = Number(choice) === q.a;
  return { correct, answer: q.a, why: q.why };
}

// The site's 404 page pings this with the path it couldn't find. We forward it
// to the portal so Pulse can see which links are broken and auto-fix them. Best
// effort: a visitor never waits on it, and it never reveals anything.
const PORTAL_404 = "https://portal.bvtech.org/api/public-tools/notfound";

async function report404(request) {
  try {
    const body = (await request.text()).slice(0, 1000);
    request.ctx && request.ctx.waitUntil && request.ctx.waitUntil(
      fetch(PORTAL_404, { method: "POST", body,
        headers: { "content-type": "application/json", origin: "https://bvtech.org" },
        signal: AbortSignal.timeout(4000) }).catch(() => {}));
  } catch (e) { /* ignore */ }
  return json({ ok: true }, 200, 0);
}

export function onRequestGet({ request }) {
  const what = new URL(request.url).pathname.split("/").pop();
  if (what === "daily") return json(today(), 200, 300);
  return json({ error: "not found" }, 404, 0);
}

export async function onRequestPost({ request }) {
  const path = new URL(request.url).pathname;
  if (path.endsWith("/notfound")) return report404(request);
  let body;
  try { body = JSON.parse((await request.text()).slice(0, 500)); }
  catch (e) { return json({ error: "bad request" }, 400, 0); }
  return json(gradeToday(body.choice), 200, 0);
}
