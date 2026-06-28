# GitHub Repo Secrets â€” `deploy-linode.yml`

These are the **repository Secrets** the CI/CD workflow (`.github/workflows/deploy-linode.yml`)
needs to SSH into the Linode and deploy OpsPilot. Create them once in the
`BVTECHLLC/Pulse` repo.

> The application's own runtime secrets (SECRET_KEY, DATABASE_URL, TUNNEL_TOKEN, etc.)
> live **only** in the server-side file `/opt/bvtech-portal/opspilot/.env` (chmod 600).
> They are **NOT** GitHub Secrets â€” see [App env](#app-env-not-in-github) below.

---

## Secrets to create

| Secret name      | Value                                                            |
| ---------------- | --------------------------------------------------------------- |
| `LINODE_HOST`    | `45.33.29.100`                                                  |
| `LINODE_USER`    | `deploy`                                                        |
| `LINODE_APP_DIR` | `/opt/bvtech-portal`                                            |
| `LINODE_SSH_KEY` | **Full contents** of the ed25519 PRIVATE key (see below)        |

### `LINODE_SSH_KEY` â€” the private key

Paste the **entire file** `C:\Users\bvtec\.ssh\opspilot_linode`, including the
`-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----`
lines and the trailing newline. Do **not** wrap, trim, or re-indent it.

- The matching **public** key (`opspilot_linode.pub`) is already installed in
  `deploy`'s `~/.ssh/authorized_keys` on the server, so no server change is needed.
- `deploy` is a **key-only** login and is in the `docker` group, so the workflow
  runs `docker compose` with **no sudo**.

> [!WARNING]
> **Never commit the private key.** It belongs only in this GitHub Secret and in
> `C:\Users\bvtec\.ssh\` on your machine. It must never appear in the repo, in
> `opspilot/.env`, in logs, or in any file under version control. If it is ever
> exposed, generate a new keypair, replace `authorized_keys` on the server, and
> update `LINODE_SSH_KEY`.

---

## Option A â€” GitHub web UI

1. Go to the repo: **github.com/BVTECHLLC/Pulse**
2. **Settings** > **Secrets and variables** > **Actions**
3. **New repository secret** (do this once per secret):
   - **Name:** `LINODE_HOST`  -> **Secret:** `45.33.29.100` -> **Add secret**
   - **Name:** `LINODE_USER`  -> **Secret:** `deploy` -> **Add secret**
   - **Name:** `LINODE_APP_DIR` -> **Secret:** `/opt/bvtech-portal` -> **Add secret**
   - **Name:** `LINODE_SSH_KEY` -> **Secret:** paste the full private-key file -> **Add secret**

You can edit/replace a secret later, but GitHub never shows the stored value again
after saving.

---

## Option B â€” `gh` CLI

Run from your machine with the GitHub CLI authenticated (`gh auth login`).
These set **repository** secrets on `BVTECHLLC/Pulse`:

```powershell
$repo = "BVTECHLLC/Pulse"

gh secret set LINODE_HOST    --repo $repo --body "45.33.29.100"
gh secret set LINODE_USER    --repo $repo --body "deploy"
gh secret set LINODE_APP_DIR --repo $repo --body "/opt/bvtech-portal"

# Read the private key straight from the file â€” never paste it into the terminal:
gh secret set LINODE_SSH_KEY --repo $repo < "$env:USERPROFILE\.ssh\opspilot_linode"
```

> Using `< file` (stdin) for `LINODE_SSH_KEY` keeps the key out of your shell
> history and preserves the exact bytes/newlines of the file.

Verify the names landed (values are never displayed):

```powershell
gh secret list --repo BVTECHLLC/Pulse
```

---

## How the workflow uses these

The deploy job loads the key, SSHes in as `deploy`, and runs:

```bash
cd $LINODE_APP_DIR                 # /opt/bvtech-portal
git pull --ff-only
cd opspilot
docker compose run --rm api alembic upgrade head   # migrations (prod does NOT auto-create tables)
docker compose up -d --build api
docker image prune -f
```

`docker-compose.override.yml` (the `cloudflared` tunnel, server-only and not
committed) stays in place across `git pull` and is not touched by the workflow.

---

## App env (NOT in GitHub)

The API reads **all** of its runtime config from `/opt/bvtech-portal/opspilot/.env`
on the server. Do **not** add these to GitHub Secrets:

- `ENV=production`, `SECRET_KEY`, `AGENT_ENROLL_SECRET`
- `DATABASE_URL`, `REDIS_URL`, `COOKIE_SECURE`
- `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`
- `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`
- `TUNNEL_TOKEN` (Cloudflare Tunnel)

GitHub only needs enough to **reach the server and run the deploy** â€” the four
`LINODE_*` secrets above. App secrets are managed by editing `.env` on the Linode
directly.
