# BVTech.org — Live Auto-Publishing Setup

This wires up: **GitLab Pages** auto-deploy for the website repo,
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
    │  git commit && git push  →  GitLab repo (main)
    ▼
 GitLab Pages CI  ──auto-deploy──►  https://bvtech.org/blog/<slug>.html  (LIVE)
```

---

## Part 1 — GitLab Pages auto-deploy (chosen path)

We're using **GitLab Pages** (self-contained — avoids the Cloudflare↔Git
integration that was failing). When creating the GitLab project, pick the
**Pages/Plain HTML** template (your site is static HTML — no build framework).

1. **Seed the repo with your site.** On the Linode box (or your laptop), with
   the V107 site files in a folder:
   ```bash
   cd /path/to/bvtech-website
   git init -b main
   git remote add origin git@gitlab.com:BVTECHLLC-group/BVTECHLLC-website.git
   git add -A && git commit -m "Import BVTech.org V107"
   git push -u origin main
   ```
2. **Add the deploy config.** Copy `automation/gitlab-ci.yml` from this repo into
   the website repo **root** as `.gitlab-ci.yml` (it replaces the template's
   one). It mirrors your root files into `public/` on every push to `main`, so
   you don't have to restructure the site. Commit + push it.
3. GitLab → your project → **Build → Pipelines** — watch the `pages` job go
   green. Then **Deploy → Pages** shows your live `*.gitlab.io` URL. Confirm it
   looks right.
4. **Custom domain:** **Deploy → Pages → New Domain → `bvtech.org`**. GitLab
   gives you a `TXT` verification record and a target (`A`/`CNAME`). Add those in
   your **Cloudflare DNS** tab. Tip: set the records to **DNS only (grey cloud)**
   first so GitLab can verify + issue its Let's Encrypt cert; you can re-enable
   the orange proxy afterward.
5. Headers: GitLab Pages (16.6+) honors a root **`_headers`** file like yours, so
   your security headers carry over. If your version doesn't, re-add them in the
   `.gitlab-ci.yml` or Pages settings (ask me and I'll wire it).

✅ From now on, **every `git push` to `main` auto-deploys** to bvtech.org.

> Prefer Cloudflare after all? Cloudflare Pages can connect to **GitLab** too
> (Workers & Pages → Create → Pages → Connect to Git → GitLab), or publish via
> `wrangler pages deploy public` from the box. Either works — say the word.

---

## Part 2 — Give the Linode box push access to the GitLab repo

Publishing runs from the **Linode box's** git credentials (this session's access
is scoped to `bvtechllc/pulse`, so the box is the publisher — the secure design
for unattended deploys). Use a **GitLab deploy key with write access**:

```bash
# On the Linode box:
ssh-keygen -t ed25519 -C "linode-bvtech-publisher" -f ~/.ssh/bvtech_deploy -N ""
cat ~/.ssh/bvtech_deploy.pub
```
- GitLab → **project → Settings → Repository → Deploy keys → Add key** → paste
  the `.pub` → tick **Grant write permissions** ✅.
- Point the box at it and clone:
  ```bash
  cat >> ~/.ssh/config <<'EOF'
  Host gitlab-bvtech
    HostName gitlab.com
    User git
    IdentityFile ~/.ssh/bvtech_deploy
    IdentitiesOnly yes
  EOF
  git clone gitlab-bvtech:BVTECHLLC-group/BVTECHLLC-website.git /srv/bvtech-website-new
  git -C /srv/bvtech-website-new config user.name  "BVTech Publisher"
  git -C /srv/bvtech-website-new config user.email "publisher@bvtech.org"
  ```
- `daily_blog.sh` pushes to `origin main` — no script change needed; it's
  git-host-agnostic. Just keep `BV_WEBSITE_REPO=/srv/bvtech-website-new`.

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
