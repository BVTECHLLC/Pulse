// BVTech Explore - Daily Byte game + tech tip + 404 telemetry (v1.102).
//   /tools-api/daily        -> today's trivia question (no answer) + tip
//   /tools-api/daily/grade  -> grade an answer (POST), answer stays server-side
//   /tools-api/notfound     -> the site 404 page reports the missing path here
//                              (fire-and-forget to the portal; feeds the scanner)
import { json } from "./feeds.js";

// Everyone gets the SAME question each day (so people can compare), rotating
// through the pool by day number. Answers live here, never in the page.
export const TRIVIA = [
  // category: sec | tech | space | ev | history | net | ai ; diff: Easy|Med|Hard
  { c: "sec", d: "Easy", q: "What does the 'S' in HTTPS stand for?", o: ["Secure", "Server", "Standard", "System"], a: 0,
    why: "HTTPS = HTTP Secure: the padlock means the connection is encrypted in transit." },
  { c: "sec", d: "Easy", q: "Which of these is the STRONGEST passphrase?", o: ["correct-horse-battery-staple", "P@ssw0rd!", "Summer2026", "qwerty123"], a: 0,
    why: "Length beats complexity. Four random words crush a short 'complex' password." },
  { c: "sec", d: "Med", q: "A 'zero-day' vulnerability is one that is...", o: ["Exploited before a fix exists", "Older than a day", "Impossible to exploit", "Only in old software"], a: 0,
    why: "Defenders have had zero days to patch it - which is why fast updates matter." },
  { c: "sec", d: "Med", q: "What does MFA protect against even if your password leaks?", o: ["Account takeover", "Slow internet", "Viruses on your PC", "Spam email"], a: 0,
    why: "A stolen password alone isn't enough - the attacker still can't pass the second factor." },
  { c: "sec", d: "Hard", q: "In an 'AiTM' phishing attack, what does the attacker actually steal?", o: ["Your logged-in session token", "Your monitor", "Your Wi-Fi password", "Your CPU"], a: 0,
    why: "Adversary-in-the-Middle proxies the real login and steals the session cookie - sailing past MFA." },
  { c: "sec", d: "Hard", q: "What is 'salting' a password hash for?", o: ["So identical passwords hash differently", "To make it taste better", "To speed up logins", "To shorten the hash"], a: 0,
    why: "A unique salt per user means two people with the same password get different hashes, defeating rainbow tables." },
  { c: "sec", d: "Med", q: "Ransomware's single best countermeasure is...", o: ["Tested offline backups", "A faster CPU", "More RAM", "A louder alarm"], a: 0,
    why: "If you can restore clean data, the extortion loses its leverage. Backups must be offline and tested." },
  { c: "tech", d: "Easy", q: "'The cloud' really means...", o: ["Someone else's computers you reach over the internet", "Water vapor", "Your hard drive", "A kind of Wi-Fi"], a: 0,
    why: "Cloud services run on data-center servers you access over the internet." },
  { c: "tech", d: "Med", q: "What does a CPU's 'core' let it do?", o: ["Work on multiple tasks at once", "Store files permanently", "Connect to Wi-Fi", "Cool itself down"], a: 0,
    why: "Each core is an independent worker; more cores = more true multitasking." },
  { c: "tech", d: "Med", q: "RAM is different from storage (SSD/HDD) because RAM...", o: ["Is cleared when power is off", "Holds files forever", "Is where the OS is installed", "Is slower"], a: 0,
    why: "RAM is fast, temporary working memory; storage keeps your files when the power's off." },
  { c: "tech", d: "Hard", q: "What does 'open source' software guarantee?", o: ["Anyone can read and audit the code", "It's bug-free", "It's always free of charge", "It only runs on Linux"], a: 0,
    why: "Open source means the source code is public and inspectable - not that it's free or flawless." },
  { c: "net", d: "Easy", q: "What does a router mainly do at home?", o: ["Shares one internet line among your devices", "Stores your photos", "Charges your phone", "Blocks all ads"], a: 0,
    why: "A router directs traffic between your devices and the internet (and usually serves your Wi-Fi)." },
  { c: "net", d: "Med", q: "What is an IP address?", o: ["A device's address on a network", "A password", "A type of cable", "A website's logo"], a: 0,
    why: "Every device on a network has an IP address so data knows where to go." },
  { c: "net", d: "Hard", q: "Why was IPv6 created?", o: ["The world ran out of IPv4 addresses", "To make Wi-Fi faster", "To replace HTTPS", "To block hackers"], a: 0,
    why: "IPv4's ~4.3 billion addresses weren't enough for a connected planet; IPv6 is vastly larger." },
  { c: "net", d: "Med", q: "What does DNS do?", o: ["Turns a domain name into an IP address", "Encrypts your email", "Speeds up downloads", "Stores passwords"], a: 0,
    why: "DNS is the internet's phone book: it resolves names like bvtech.org to the server's IP." },
  { c: "space", d: "Easy", q: "Roughly how high does the ISS orbit?", o: ["~250 miles up", "~25 miles up", "~2,500 miles up", "~25,000 miles up"], a: 0,
    why: "The International Space Station orbits in low Earth orbit, about 250 miles (400 km) up." },
  { c: "space", d: "Med", q: "Which rover is hunting for ancient life on Mars in Jezero Crater?", o: ["Perseverance", "Curiosity", "Opportunity", "Sojourner"], a: 0,
    why: "Perseverance landed in Jezero - a dried-up river delta - in 2021 to cache samples for return." },
  { c: "space", d: "Hard", q: "What makes SpaceX's Falcon 9 booster special?", o: ["It lands and is reused", "It's the biggest ever", "It uses no fuel", "It's single-use"], a: 0,
    why: "Falcon 9 first stages fly back and land, then launch again - slashing the cost to orbit." },
  { c: "space", d: "Hard", q: "The James Webb telescope mainly observes in which light?", o: ["Infrared", "X-ray", "Visible only", "Radio"], a: 0,
    why: "Webb's infrared eyes peer through dust and see the earliest, most distant galaxies." },
  { c: "ev", d: "Easy", q: "Which company makes the Cybertruck?", o: ["Tesla", "Ford", "Rivian", "Toyota"], a: 0,
    why: "Tesla's stainless-steel Cybertruck is one of the most recognizable EVs on the road." },
  { c: "ev", d: "Med", q: "An EV's range is mostly set by the size of its...", o: ["Battery pack (kWh)", "Touchscreen", "Wheels", "Trunk"], a: 0,
    why: "More kilowatt-hours of battery = more miles, roughly 3-4 miles per kWh for most EVs." },
  { c: "ev", d: "Hard", q: "What does 'regenerative braking' do in an EV?", o: ["Recovers energy back into the battery", "Makes brakes louder", "Heats the cabin", "Cleans the air"], a: 0,
    why: "Slowing down turns the motor into a generator, feeding energy back and extending range." },
  { c: "ai", d: "Easy", q: "What is a 'prompt' when using an AI chatbot?", o: ["The instruction you give it", "Its error message", "Its logo", "Its price"], a: 0,
    why: "A prompt is the text you give the model; clearer prompts get better answers." },
  { c: "ai", d: "Med", q: "Why can AI chatbots sometimes 'hallucinate'?", o: ["They predict plausible text, not verified facts", "They get tired", "They run out of memory", "They're offline"], a: 0,
    why: "LLMs generate likely-sounding words; without grounding they can state false things confidently. Verify." },
  { c: "ai", d: "Hard", q: "What is 'prompt injection' in AI security?", o: ["User input that overrides the app's instructions", "Typing too fast", "A hardware fault", "A kind of virus scan"], a: 0,
    why: "Attackers smuggle instructions into input the model treats as commands - #1 on the OWASP LLM Top 10." },
  { c: "history", d: "Med", q: "What year did Microsoft release Windows XP?", o: ["2001", "1995", "2007", "2010"], a: 0,
    why: "Windows XP shipped October 25, 2001 - one of the longest-lived, most popular Windows versions." },
  { c: "history", d: "Hard", q: "What was ARPANET, launched in 1969?", o: ["The ancestor of the internet", "The first smartphone", "An early video game", "A NASA rocket"], a: 0,
    why: "ARPANET first linked a handful of university computers - the network that grew into the internet." },
  { c: "history", d: "Hard", q: "Who is credited with inventing the World Wide Web in 1989?", o: ["Tim Berners-Lee", "Bill Gates", "Steve Jobs", "Elon Musk"], a: 0,
    why: "Tim Berners-Lee proposed the Web - URLs, HTTP and HTML - while at CERN in 1989." },
  { c: "history", d: "Med", q: "What does the 'www' you see in web addresses stand for?", o: ["World Wide Web", "World Web Works", "Wide World Web", "Web Within Web"], a: 0,
    why: "It's the World Wide Web - the system of linked pages Tim Berners-Lee created." },
  { c: "tech", d: "Easy", q: "What's the safest place to keep many passwords?", o: ["A reputable password manager", "A sticky note", "One password everywhere", "passwords.txt on your desktop"], a: 0,
    why: "A password manager makes every login long, unique and remembered for you." },
  { c: "sec", d: "Med", q: "A website shows a padlock. Is it automatically safe?", o: ["No - the padlock only means encrypted, read the domain", "Yes, always", "Only on phones", "Only for banks"], a: 0,
    why: "Scammers use HTTPS too. The padlock means private, not trustworthy - check the exact domain name." },
  { c: "tech", d: "Hard", q: "What does a 'firewall' actually do?", o: ["Filters network traffic by rules", "Puts out server fires", "Speeds up Wi-Fi", "Backs up files"], a: 0,
    why: "A firewall allows or blocks traffic based on rules - one layer of defense, not the whole plan." },
  { c: "net", d: "Med", q: "Public Wi-Fi is risky mainly because...", o: ["Others on it may snoop unencrypted traffic", "It's always slow", "It drains your battery", "It costs money"], a: 0,
    why: "On open Wi-Fi, use HTTPS sites and a VPN so nobody on the same network can read your traffic." },
  { c: "ai", d: "Med", q: "A 'deepfake' is...", o: ["AI-generated fake audio or video of a real person", "A deep-sea camera", "A password type", "A kind of backup"], a: 0,
    why: "Deepfakes clone voices and faces - verify unusual requests by a trusted second channel." },
  { c: "space", d: "Easy", q: "What is a light-year a measure of?", o: ["Distance", "Time", "Brightness", "Temperature"], a: 0,
    why: "A light-year is how far light travels in a year - about 5.9 trillion miles." },
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


// Deterministic daily shuffle of a question's options, so the correct answer
// moves around but everyone sees the same order on the same day. Returns the
// shuffled options and where the correct answer landed.
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function shuffleFor(q, seed) {
  const idx = q.o.map((_, i) => i);
  const rnd = mulberry32((seed * 2654435761) >>> 0);
  for (let i = idx.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    const t = idx[i]; idx[i] = idx[j]; idx[j] = t;
  }
  return { options: idx.map((i) => q.o[i]), correct: idx.indexOf(q.a) };
}

function dayNumber(now = new Date()) {
  const ct = new Date(now.toLocaleString("en-US", { timeZone: "America/Chicago" }));
  return Math.floor(Date.UTC(ct.getFullYear(), ct.getMonth(), ct.getDate()) / 86400000);
}

const CATS = { sec: "🛡️ Security", tech: "💻 Tech", space: "🚀 Space", ev: "⚡ EVs",
  history: "📜 Tech History", net: "🌐 Networking", ai: "🤖 AI" };

export function today(now = new Date()) {
  const n = dayNumber(now);
  const q = TRIVIA[n % TRIVIA.length];
  const sh = shuffleFor(q, n + 1);
  return {
    day: n,
    date: new Date(now.toLocaleString("en-US", { timeZone: "America/Chicago" }))
      .toISOString().slice(0, 10),
    tip: TIPS[n % TIPS.length],
    category: CATS[q.c] || "💡 Tech", difficulty: q.d || "Med",
    question: { q: q.q, options: sh.options },
    index: (n % TRIVIA.length) + 1, total: TRIVIA.length,
  };
}

export function gradeToday(choice, now = new Date()) {
  const n = dayNumber(now);
  const q = TRIVIA[n % TRIVIA.length];
  const sh = shuffleFor(q, n + 1);
  const correct = Number(choice) === sh.correct;
  return { correct, answer: sh.correct, why: q.why };
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
