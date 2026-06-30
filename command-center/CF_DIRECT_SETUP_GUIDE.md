# BVTech MSP Command Center v25 — Cloudflare Direct Setup Guide

**No GitHub. No OAuth loops. Direct upload to Cloudflare Pages.**

This guide walks you through getting the credentials you need to plug into
Settings → BVTech.org section, so the tool can auto-publish blog posts and
news articles directly to bvtech.org without touching GitHub at all.

Total time: **about 3 minutes.**

---

## What you need

Three things:
1. **Cloudflare API Token** (scoped to Pages)
2. **Cloudflare Account ID**
3. **Pages project name** (you already have this — it's `bvtech-site`)

---

## Step 1 — Get your Cloudflare Account ID (10 seconds)

1. Go to https://dash.cloudflare.com/
2. Log in with the same account that hosts bvtech.org
3. Click on any site (e.g. `bvtech.org`) in your account
4. Look at the right sidebar — you'll see **Account ID** with a copy button
5. Click the copy button. That's your Account ID.

It looks like this: `a1b2c3d4e5f6789012345678abcdef12` (32 hex characters)

**Paste it into: Settings → BVTech.org → CF Account ID**

---

## Step 2 — Create a Cloudflare API Token (2 minutes)

1. Go to https://dash.cloudflare.com/profile/api-tokens
2. Click **Create Token**
3. Find the **"Edit Cloudflare Workers"** template → click **Use Template**
   - (This template already has the Pages permissions we need — it covers both
     Workers and Pages in one token.)
4. Under **Account Resources**, select your account from the dropdown
5. Under **Zone Resources**, leave as "All zones from account" or select
   `bvtech.org` specifically
6. Click **Continue to summary** at the bottom
7. Click **Create Token**
8. **IMPORTANT:** Copy the token NOW. Cloudflare will only show it once.
   It looks like: `xYz123_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789`

**Paste it into: Settings → BVTech.org → CF API Token**

---

## Step 3 — Confirm the Pages project name

You already have a Cloudflare Pages project called `bvtech-site` (that's
where your current site lives). Double-check:

1. In the Cloudflare dashboard, click **Workers & Pages** in the left sidebar
2. You should see `bvtech-site` listed
3. The name shown is exactly what goes in the "CF Project Name" field

**Paste it into: Settings → BVTech.org → CF Project Name** (usually
`bvtech-site` — it's pre-filled by default).

If your project has a different name, use that exact name.

---

## Step 4 — Clear the old GitHub fields (important!)

If the GitHub Token or GitHub Repo fields have any leftover values from
previous attempts, **wipe them clean**. Leave them empty.

The v25 fix makes the tool prefer Cloudflare Direct when both CF and GH
credentials are present, but clearing the GH fields removes any ambiguity
and makes the mode detection unambiguous.

---

## Step 5 — Save & Test

1. Click **Save** at the bottom of Settings
2. Scroll back up to the Cloudflare section
3. Click **🧪 Test Cloudflare**

You should see a green success message like:

```
✅ Connected
Mode: cloudflare_direct
Project: bvtech-site
Site: https://bvtech.org
Subdomain: bvtech-site.pages.dev
```

If you see that — **you're live**. The tool can now push blog posts and news
articles directly to bvtech.org with no GitHub involvement.

---

## Step 6 — Test a real post

1. Go to the **📰 NEWS** tab in the Command Center
2. Click **Test Scrapers** to confirm the CVE feeds work
3. Click **Generate Now** to create one test article
4. Wait ~30 seconds while Claude writes the article
5. You should see: `✅ Deployed to Cloudflare Pages!` in the log
6. Open https://bvtech.org/news/ in a new tab to confirm the article is live

---

## Step 7 — Enable autopilot

Once the test post succeeds:

1. In the NEWS tab, find the **Auto-Post Scheduler**
2. Set time to **06:00 CST**
3. Click **Enable Autopilot**

The tool will now automatically scrape CISA KEV + NVD, generate an article
with Claude, and publish it to bvtech.org/news/ every morning at 6:00 AM —
as long as the Command Center is running on your PC.

**Tip:** to keep the Command Center running even after reboot, create a
Windows Task Scheduler entry that runs `Start-BVTech.bat` on login. That way
the tool survives restarts and just works in the background forever.

---

## Troubleshooting

### "CF API 401: Unauthorized"
Your API token is wrong or got regenerated. Create a new one (Step 2) and
paste it in again.

### "CF API 404: Project not found"
Your Pages project name doesn't match. Check Workers & Pages in the
Cloudflare dashboard — use the exact name shown there.

### "CF API 403: Forbidden"
Your token is missing the Pages:Edit permission. Delete it and create a new
one using the **"Edit Cloudflare Workers"** template (not a custom token).

### "Failed to connect — check your internet"
That's not a credential issue. Check your internet, VPN, or firewall.

### The tool still says GitHub mode after saving
Restart the Command Center (`Start-BVTech.bat`). Config is loaded at
startup in some code paths. After restart, watch the console log — it will
print `[v25] BVTech publisher → Cloudflare Direct Upload mode` when it picks
the right mode.

---

## About JordanPolasek.com

JordanPolasek.com is still on WordPress/SiteGround right now. The firewall
error you're seeing in the ORM Beast tab (`403 Blocked by firewall`) is your
WordPress security plugin (likely Wordfence or Sucuri) blocking the REST
API. **Don't try to fix the WordPress side** — the path forward is to
migrate JP to Cloudflare Pages the same way BVTech works now, and configure
the **JP CF fields** (jp_cf_api_token, jp_cf_account_id, jp_cf_project_name)
in Settings with a second Cloudflare project called `jordanpolasek-site`.

We'll do that migration in a dedicated session. For today, BVTech.org
auto-posting is the win.

---

**You're done. Enjoy the quiet.** 🎉
