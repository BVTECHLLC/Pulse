# BVTech.org — Live Auto-Publishing Setup

This wires up: **Cloudflare Pages ← GitHub (`bvtech-website-new`)** for auto-deploy,
**Claude Code on your Linode box** to write a fresh security advisory daily in
your voice, and a **cron job** that publishes it live — every day, hands-off.

```
 cron (Linode)
    │  runs automation/daily_blog.sh
    ▼
 Claude Code (headless) ──web search──► today's real cyber story
    │  writes the post in Jordan's voice → automation/out/today.json
    ▼
 scripts/publish_post.py
    │  clones newest /blog post for pixel-perfect template
    │  writes blog/<slug>.html + updates sitemap.xml
    │  git commit && git push  →  bvtech-website-new (main)
    ▼
 Cloudflare Pages  ──auto-deploy──►  https://bvtech.org/blog/<slug>.html  (LIVE)
```

---

## Part 1 — Connect `bvtech-website-new` to Cloudflare Pages (auto-deploy)

Do this once, in the **Cloudflare dashboard** (I can't click here for you):

1. First, get your current site into the new repo. On the Linode box (or your
   laptop), with the website files (the V107 zip contents) in a folder:
   ```bash
   cd /path/to/bvtech-website
   git init -b main
   git remote add origin git@github.com:BVTECHLLC/bvtech-website-new.git
   git add -A && git commit -m "Import BVTech.org V107"
   git push -u origin main
   ```
2. Cloudflare dashboard → **Workers & Pages → Create → Pages → Connect to Git**.
3. Pick **BVTECHLLC/bvtech-website-new**, branch **main**.
4. Build settings: **Framework preset = None**, **Build command = (blank)**,
   **Build output directory = `/`** (the site is static — no build step).
5. Deploy. You'll get a `*.pages.dev` URL — confirm it looks right.
6. **Custom domain:** Pages project → **Custom domains → Set up a custom domain
   → `bvtech.org`** (and `www`). Cloudflare adds the DNS records automatically
   since your domain is already on Cloudflare. Remove/replace the old direct-
   upload Pages project's domain binding so `bvtech.org` points at this one.
7. Keep your `_headers` and `_redirects` files in the repo root — Pages honors
   them automatically (your security headers + caching carry over).

✅ From now on, **every `git push` to `main` auto-deploys** to bvtech.org.

---

## Part 2 — Give the Linode box push access to the repo

The publishing happens from the **Linode box's** git credentials (not my
session — my access is scoped to `bvtechllc/pulse` only). Use a **deploy key**:

```bash
# On the Linode box:
ssh-keygen -t ed25519 -C "linode-bvtech-publisher" -f ~/.ssh/bvtech_deploy -N ""
cat ~/.ssh/bvtech_deploy.pub
```
- GitHub → **BVTECHLLC/bvtech-website-new → Settings → Deploy keys → Add deploy
  key** → paste the `.pub` → **Allow write access** ✅.
- Tell the box to use that key for this repo:
  ```bash
  cat >> ~/.ssh/config <<'EOF'
  Host github-bvtech
    HostName github.com
    User git
    IdentityFile ~/.ssh/bvtech_deploy
    IdentitiesOnly yes
  EOF
  git clone github-bvtech:BVTECHLLC/bvtech-website-new.git /srv/bvtech-website-new
  git -C /srv/bvtech-website-new config user.name  "BVTech Publisher"
  git -C /srv/bvtech-website-new config user.email "publisher@bvtech.org"
  ```

> If you'd rather I manage the repo directly via GitHub too, add me/your token —
> but note this **session** is policy-locked to `bvtechllc/pulse`, so the live
> daily publishing must run from the box regardless. The box is the publisher.

---

## Part 3 — Install Claude Code on the Linode box

```bash
# Node 18+ required
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt-get install -y nodejs
sudo npm install -g @anthropic-ai/claude-code

# Auth: an API key for headless/cron use (create at console.anthropic.com).
sudo mkdir -p /etc/ && sudo tee /etc/bvtech-daily.env >/dev/null <<'EOF'
export ANTHROPIC_API_KEY="sk-ant-...your key..."
export PULSE_REPO="/srv/pulse/opspilot"
export BV_WEBSITE_REPO="/srv/bvtech-website-new"
EOF
sudo chmod 600 /etc/bvtech-daily.env

# Make sure the pulse repo is on the box too (it runs portal.bvtech.org already):
#   /srv/pulse  ← this repo (has automation/ + scripts/publish_post.py)
claude --version    # confirm the CLI works
```

If your `claude` CLI version uses different flags than
`automation/daily_blog.sh` (`--print --permission-mode acceptEdits
--allowedTools ...`), run `claude --help` and adjust those two lines. The intent:
**non-interactive, allowed to web-search + write files + run the publish script.**

---

## Part 4 — Schedule the daily job

```bash
chmod +x /srv/pulse/opspilot/automation/daily_blog.sh
# Test it once by hand first (writes a real post + pushes — or add --dry-run in
# the script's publish call while testing):
/srv/pulse/opspilot/automation/daily_blog.sh ; tail -n 40 /var/log/bvtech/daily-*.log

# Then schedule it. 12:30 UTC = 07:30 America/Chicago (CDT):
( crontab -l 2>/dev/null; echo "30 12 * * * /srv/pulse/opspilot/automation/daily_blog.sh" ) | crontab -
```

That's it. Each morning the box writes a fresh, fact-checked advisory in your
voice and it goes live on bvtech.org automatically.

---

## Operating it

- **Preview/compose by hand anytime:** the portal's **Content Studio** tab
  (portal.bvtech.org) renders posts exactly as they publish; "Stage" shows the
  publish path.
- **Logs:** `/var/log/bvtech/daily-YYYY-MM-DD.log`.
- **Switch to a review gate** (instead of fully automatic): in
  `automation/daily_blog.sh`, change the persona/prompt to write
  `automation/out/today.json` **without** the `--git` flag on the publish call,
  and review/commit yourself — or have it open a PR instead of pushing to main.
- **Roll back a bad post:** `git -C /srv/bvtech-website-new revert <commit>` and
  push; Cloudflare redeploys in ~30s.

## Safety rails already built in
- The post template is **cloned from your real site** → identical chrome/SEO.
- **No tenant/client data** can leak — the generator only takes a title + body.
- The persona forbids fabricating CVEs/versions/dates and requires multi-source
  verification.
- `flock` prevents overlapping runs; the post is archived after publish so it
  never double-posts.
