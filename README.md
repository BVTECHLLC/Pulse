# BVTech OpsPilot

Self-hosted MSP client portal for BVTech. A **server-rendered FastAPI** app
(Jinja2 templates: login, dashboard, portal) â€” no separate frontend, no
Cloudflare Pages. The application lives in [`opspilot/`](opspilot/); this repo
root holds the control-center docs, CI/CD, and ops tooling.

Public access is via a **Cloudflare Tunnel** â€” zero open inbound ports on the
Linode (only SSH/22). `https://portal.bvtech.org` routes to `api:8000` through
the tunnel.

## Architecture

```
  Phone (Claude) â”€â”€â–º GitHub PR â”€â”€â–º merge to main
                                       â”‚
                                       â–¼
                              GitHub Actions (deploy)
                                       â”‚  ssh deploy@45.33.29.100
                                       â–¼
                         Linode: /opt/bvtech-portal/opspilot
                         git pull --ff-only
                         docker compose run --rm api alembic upgrade head
                         docker compose up -d --build api
                                       â”‚
                                       â–¼
                         Docker Compose:  db (postgres:16)
                                          redis (redis:7)
                                          api (uvicorn :8000)
                                          cloudflared (override.yml)
                                       â–²
                                       â”‚  HTTP, no open ports
                         Cloudflare Tunnel  â—„â”€â”€ portal.bvtech.org
                                       â–²
                                       â”‚
                                     Users
```

Source of truth is GitHub. Changes are driven from a phone via Claude â†’ PR â†’
merge â†’ automatic deploy. See [docs/PHONE_WORKFLOW.md](docs/PHONE_WORKFLOW.md).

## Repo layout

```
.
â”œâ”€â”€ README.md            â† this file
â”œâ”€â”€ CLAUDE.md            â† guidance for Claude
â”œâ”€â”€ docs/                â† roadmap, version log, ops runbooks
â”œâ”€â”€ .github/workflows/   â† CI/CD (deploy on push to main)
â”œâ”€â”€ ops/                 â† server/ops helper files
â””â”€â”€ opspilot/            â† the application
    â”œâ”€â”€ app/             â† FastAPI app (core/config.py holds APP_VERSION)
    â”œâ”€â”€ Dockerfile
    â”œâ”€â”€ docker-compose.yml
    â”œâ”€â”€ alembic/         â† migrations (head: cdef051e7149)
    â”œâ”€â”€ smoke_test.py
    â””â”€â”€ .env             â† NOT committed
```

> Control-center files (this README, `CLAUDE.md`, `docs/*`,
> `.github/workflows/*`, `ops/*`) live at the **repo root**. Application code
> lives under `opspilot/`.

## Quickstart (local dev)

```bash
cd opspilot

# Create a dev .env (SQLite is fine locally; tables auto-create when ENV != production)
cat > .env <<'EOF'
ENV=dev
SECRET_KEY=dev-secret-change-me
AGENT_ENROLL_SECRET=dev-enroll
DATABASE_URL=sqlite+aiosqlite:///./dev.db
COOKIE_SECURE=false
BOOTSTRAP_ADMIN_EMAIL=admin@example.com
BOOTSTRAP_ADMIN_PASSWORD=changeme
EOF

# Install deps + run
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Health check
curl http://localhost:8000/api/health        # -> {"ok":true,...}

# Smoke test
python smoke_test.py
```

Open http://localhost:8000/ for the login page.

## Production overview

Runs via Docker Compose on the Linode (`/opt/bvtech-portal/opspilot`):

| Service       | Image / build           | Notes                                        |
|---------------|-------------------------|----------------------------------------------|
| `db`          | postgres:16-alpine      | persistent volume                            |
| `redis`       | redis:7-alpine          |                                              |
| `api`         | built from `Dockerfile` | uvicorn `:8000`, reads `opspilot/.env`       |
| `caddy`       | present but **unused**  | public access is via the tunnel instead      |
| `cloudflared` | override.yml (server)   | `tunnel --no-autoupdate run`, server-only    |

- **Health:** `GET /api/health` â†’ `{"ok":true,...}`
- **Migrations:** in production (`ENV=production`) tables are **not**
  auto-created. Apply with:
  ```bash
  docker compose run --rm api alembic upgrade head
  ```
- **Secrets:** `opspilot/.env` (chmod 600) holds `SECRET_KEY`,
  `DATABASE_URL` (postgresql+psycopg), `TUNNEL_TOKEN`, bootstrap admin, etc.
  Never commit it. `docker-compose.override.yml` (cloudflared) is server-only
  and persists across `git pull`.

## Versioning

Releases are `0.1`, `0.2`, `0.3`, â€¦ `APP_VERSION` lives in
[`opspilot/app/core/config.py`](opspilot/app/core/config.py). Record each
release in [docs/VERSION_LOG.md](docs/VERSION_LOG.md).

## Docs

- [docs/ROADMAP.md](docs/ROADMAP.md) â€” planned work and milestones
- [docs/VERSION_LOG.md](docs/VERSION_LOG.md) â€” release history
- [docs/CLOUDFLARE.md](docs/CLOUDFLARE.md) â€” tunnel + DNS setup
- [docs/GITHUB_SECRETS.md](docs/GITHUB_SECRETS.md) â€” CI/CD repo secrets
- [docs/PHONE_WORKFLOW.md](docs/PHONE_WORKFLOW.md) â€” drive changes from your phone
- [docs/VERIFY.md](docs/VERIFY.md) â€” post-deploy verification checklist
