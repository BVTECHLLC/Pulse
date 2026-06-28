# Driving BVTech OpsPilot From Your Phone

This is the day-to-day workflow for shipping changes to OpsPilot when all you
have is your phone. The rules:

- **GitHub is the source of truth.** Every change lands as a Pull Request to
  `main`.
- **Claude never deploys.** Claude only creates branches, commits, and opens
  PRs. You are the reviewer and the only one who clicks **Merge**.
- **Merging to `main` deploys.** The `deploy-linode.yml` GitHub Action SSHes to
  the Linode and rolls out the new build. You do nothing on the server.

```
  Phone (Claude) â”€â”€branch+commit+PRâ”€â”€â–¶ GitHub PR
        â”‚                                  â”‚
        â”‚                            you review diff
        â”‚                                  â”‚
        â”‚                            you tap "Merge"
        â”‚                                  â–¼
        â”‚                       deploy-linode.yml runs
        â”‚                                  â”‚
        â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¶ Linode (45.33.29.100)
                                           â”‚
                                     portal.bvtech.org
                                     (Cloudflare Tunnel)
```

---

## 1. What you use on the phone

Any one of these works; pick whatever is in front of you:

- **Claude Code on web/mobile** (claude.ai) connected to the `BVTECHLLC/Pulse`
  repo.
- **The Claude GitHub app** â€” comment or chat to get a branch + PR opened.
- **GitHub mobile app** â€” for reviewing the diff and merging.

You do **not** need a terminal, an SSH client, or the Linode password on your
phone. The deploy is fully automated by CI once the PR merges.

---

## 2. The loop (every change)

1. **Ask Claude** to build the change as a PR (see the prompt template below).
2. **Claude opens a PR** against `main` on a new branch
   (e.g. `feat/0.5-client-dashboard`). It bumps `APP_VERSION`, updates the
   version log, commits, and pushes.
3. **CI runs on the PR** â€” build + smoke test (see Section 4). Wait for the
   green check.
4. **You review the diff** in the GitHub mobile app: Files changed â†’ read it â†’
   make sure it's only what you asked for.
5. **You merge** (Squash & merge is fine). Delete the branch.
6. **`deploy-linode.yml` fires on `main`** and deploys to the Linode:
   `git pull --ff-only` â†’ `alembic upgrade head` â†’ `up -d --build api` â†’
   `image prune`.
7. **Verify live:** open `https://portal.bvtech.org` and check the footer/version
   or `https://portal.bvtech.org/api/health` returns `{"ok":true,...}`.

---

## 3. Copy-paste prompt template (for the phone)

Paste this into Claude Code / the Claude GitHub app and fill in the brackets.
It encodes all the house rules so you don't have to repeat them.

```
Repo: BVTECHLLC/Pulse (default branch main). App lives in opspilot/.

Build version [0.5]: [describe the change, e.g. "add a client login
dashboard that lists the signed-in client's tickets"].

Requirements:
- Create a new branch named feat/[0.5]-[short-slug] off main. Do NOT push to
  main and do NOT deploy.
- Make the code change under opspilot/ (server-rendered FastAPI + Jinja2
  templates; no separate static frontend).
- Bump APP_VERSION in opspilot/app/core/config.py to [0.5.0].
- Add a VERSION_LOG entry summarizing this change.
- If the change needs a schema change, add an Alembic migration (do not enable
  auto-create; production applies migrations manually via CI).
- Commit with a clear message and OPEN A PULL REQUEST against main.
- In the PR description: what changed, why, the new version, and whether a DB
  migration is included.
- Stop after the PR is open. I will review and merge.
```

Shorter version once you're comfortable:

```
BVTECHLLC/Pulse: Build version 0.5 â€” [change]. New branch off main, bump
APP_VERSION to 0.5.0, update VERSION_LOG, open a PR against main, do not
deploy.
```

---

## 4. There is no per-PR preview URL (and what to do instead)

Be aware: OpsPilot is **server-rendered** (FastAPI serving Jinja2 templates),
not a static site. There is **no Cloudflare Pages**, so there is **no automatic
preview URL for each PR** the way a static front-end would get one. Don't go
looking for a "Visit preview" link â€” there isn't one.

How to gain confidence before merging, in order of effort:

1. **Review the diff + trust the CI smoke test (recommended default).**
   Read the Files-changed tab on your phone, and wait for the PR's CI check to
   go green. The smoke test in CI builds the API image and hits
   `GET /api/health` (expecting `{"ok":true,...}`) so you know the app at least
   boots and serves before you merge.

2. **Verify immediately after deploy.** Right after merging, open
   `https://portal.bvtech.org` and the new feature, plus
   `https://portal.bvtech.org/api/health`. If something's wrong, ask Claude to
   open a follow-up "revert version 0.5 / fix X" PR â€” never hand-edit on the
   server.

3. **(Optional, later) Stand up a real staging environment** if you want true
   previews. Because previews need a running server, the path is a small
   staging compose stack behind its own Cloudflare Tunnel hostname
   (e.g. `staging.portal.bvtech.org`) that deploys from a `staging` branch.
   This is a future enhancement, not required for the normal flow â€” note it and
   move on unless you specifically need click-through previews.

---

## 5. Guardrails (what must never happen)

- **Claude must never push to `main`** or run any deploy command. PRs only.
- **Never put real secret values** in any committed file (no `SECRET_KEY`,
  `TUNNEL_TOKEN`, DB passwords, admin password, SSH keys). Secrets live only in
  `opspilot/.env` on the server (chmod 600) and in GitHub repo Secrets.
- **You are the only approver.** A human (you) reviews and merges every PR.
- **Migrations are deliberate.** In production the app does not auto-create
  tables; CI applies `alembic upgrade head` on deploy. If a PR adds a model
  change with no migration, send it back.

---

## 6. Quick reference

| Thing | Where |
| --- | --- |
| Repo | `github.com/BVTECHLLC/Pulse`, branch `main` |
| App code | `opspilot/` |
| Version constant | `opspilot/app/core/config.py` (`APP_VERSION`) |
| Live URL | `https://portal.bvtech.org` |
| Health check | `https://portal.bvtech.org/api/health` |
| Deploy trigger | merge to `main` â†’ `.github/workflows/deploy-linode.yml` |
| Server | `deploy@45.33.29.100`, app at `/opt/bvtech-portal` |

You should rarely, if ever, need to touch the server directly. Phone â†’
Claude â†’ PR â†’ review â†’ merge â†’ automatic deploy.
