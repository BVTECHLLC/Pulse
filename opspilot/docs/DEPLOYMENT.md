# Deploying BVTech OpsPilot to a Linux VPS

Target: a fresh Ubuntu 24.04 VPS (Linode, Hetzner, DigitalOcean, etc.),
fronted by Cloudflare, reachable at **opspilot.bvtech.org**.

There are two TLS/exposure options. **Option B (Cloudflare Tunnel) is strongly
recommended** for a one-person shop: it exposes *zero* inbound ports.

---

## 1. Create & harden the server

```bash
# As root on the fresh VPS:
adduser pulse && usermod -aG sudo pulse
rsync --archive --chown=pulse:pulse ~/.ssh /home/pulse   # copy your key up first

# SSH hardening — edit /etc/ssh/sshd_config:
#   PermitRootLogin no
#   PasswordAuthentication no
#   PubkeyAuthentication yes
systemctl restart ssh

# Firewall (Option A only needs 80/443; Option B needs neither):
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
# ufw allow 80/tcp && ufw allow 443/tcp   # ONLY for Option A (Caddy)
ufw enable

# Auto security updates
apt update && apt install -y unattended-upgrades && dpkg-reconfigure -plow unattended-upgrades
```

## 2. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
usermod -aG docker pulse
# log out / back in as `pulse` so the group applies
```

## 3. Clone & configure

```bash
git clone https://github.com/BVTECHLLC/Pulse.git
cd Pulse/opspilot          # adjust if you keep the app at repo root

cp .env.example .env
# Generate two distinct secrets:
python3 -c "import secrets; print('SECRET_KEY='+secrets.token_urlsafe(64))"
python3 -c "import secrets; print('AGENT_ENROLL_SECRET='+secrets.token_urlsafe(64))"
# Paste those into .env, set ENV=production, COOKIE_SECURE=true,
# a strong POSTGRES_PASSWORD, and DATABASE_URL to match it.
nano .env
chmod 600 .env
```

## 4. Bring it up

```bash
docker compose up -d --build
docker compose ps
```

## 5. Run database migrations (production uses Alembic, not auto-create)

```bash
docker compose exec api python -m alembic upgrade head
```

The first `api` startup creates the bootstrap OWNER and prints a one-time
temporary password to the logs:

```bash
docker compose logs api | grep -A3 "BOOTSTRAP OWNER"
```

Log in, immediately enable MFA, then rotate that password.

---

## 6a. Option A — Caddy + Cloudflare DNS (ports 80/443 open)

1. In Cloudflare DNS, add an **A record**: `pulse` → your VPS IP, proxied (orange cloud).
2. Set SSL/TLS mode to **Full (strict)**.
3. Caddy (already in the compose file) fetches a cert and serves `opspilot.bvtech.org`.
4. Make sure `ufw allow 80,443` is in place.

## 6b. Option B — Cloudflare Tunnel (recommended; no open ports)

```bash
# Install cloudflared on the VPS
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cf.deb
sudo dpkg -i cf.deb
cloudflared tunnel login
cloudflared tunnel create pulse
# Map hostname -> the api container's internal port:
cloudflared tunnel route dns pulse opspilot.bvtech.org
```

Create `/etc/cloudflared/config.yml`:
```yaml
tunnel: pulse
credentials-file: /root/.cloudflared/<TUNNEL_ID>.json
ingress:
  - hostname: opspilot.bvtech.org
    service: http://localhost:8000
  - service: http_404
```

Then publish the api port to localhost only (edit compose: `api` → `ports: ["127.0.0.1:8000:8000"]`,
drop the `caddy` service), and:
```bash
cloudflared service install
systemctl enable --now cloudflared
```
Now nothing but SSH is reachable from the internet; Cloudflare brokers all web traffic.

---

## 7. Backups

```bash
# Nightly Postgres dump (add to crontab -e):
0 3 * * * docker compose -f /home/pulse/Pulse/opspilot/docker-compose.yml exec -T db \
  pg_dump -U pulse pulse | gzip > /home/pulse/backups/pulse_$(date +\%F).sql.gz

# Keep 14 days:
0 4 * * * find /home/pulse/backups -name 'pulse_*.sql.gz' -mtime +14 -delete
```

**Restore test (do this quarterly):**
```bash
gunzip -c pulse_2026-06-01.sql.gz | docker compose exec -T db psql -U pulse pulse
```
Push backups off-box too (Cloudflare R2, B2, or rclone to another host).

## 8. Updates

```bash
cd ~/Pulse && git pull
cd pulse
docker compose up -d --build
docker compose exec api python -m alembic upgrade head
```
Roll back by checking out the prior git tag and re-running the same two commands;
Alembic `downgrade -1` reverses the last migration if a schema change was involved.
