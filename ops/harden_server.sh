#!/usr/bin/env bash
#
# harden_server.sh â€” Harden SSH + firewall on the BVTech OpsPilot Linode.
#
# Target:  Ubuntu 24.04, run AS ROOT.
# Effect:  - Disable root SSH login + password auth (key-only).
#          - UFW: deny incoming, allow outgoing, allow OpenSSH (22) ONLY.
#            (NO 80/443 â€” public access is via outbound Cloudflare Tunnel.)
#          - Enable unattended-upgrades (non-interactive).
#
# LOCKOUT-SAFE: aborts unless the 'deploy' user already has a populated
# authorized_keys file, so you can never lock yourself out with this script.
#
# Usage (as root on the server):
#   bash ops/harden_server.sh
#
set -euo pipefail

echo "HARDEN_START"

# --- Config -----------------------------------------------------------------
DEPLOY_USER="deploy"
SSHD_DROPIN="/etc/ssh/sshd_config.d/99-hardening.conf"

# --- Preconditions ----------------------------------------------------------
if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: this script must be run as root." >&2
  exit 1
fi

# --- Lockout guard: deploy user must have keys -------------------------------
if ! id -u "${DEPLOY_USER}" >/dev/null 2>&1; then
  echo "ERROR: user '${DEPLOY_USER}' does not exist. Aborting (would lock you out)." >&2
  exit 1
fi

DEPLOY_HOME="$(getent passwd "${DEPLOY_USER}" | cut -d: -f6)"
AUTH_KEYS="${DEPLOY_HOME}/.ssh/authorized_keys"

if [[ ! -s "${AUTH_KEYS}" ]]; then
  echo "ERROR: ${AUTH_KEYS} is missing or empty." >&2
  echo "       Add the deploy public key BEFORE hardening, e.g.:" >&2
  echo "         install -d -m 700 -o ${DEPLOY_USER} -g ${DEPLOY_USER} ${DEPLOY_HOME}/.ssh" >&2
  echo "         echo 'ssh-ed25519 AAAA... deploy' >> ${AUTH_KEYS}" >&2
  echo "         chmod 600 ${AUTH_KEYS}; chown ${DEPLOY_USER}:${DEPLOY_USER} ${AUTH_KEYS}" >&2
  echo "       Aborting to avoid lockout." >&2
  exit 1
fi

# Require at least one non-comment, non-empty key line.
if ! grep -Eq '^[[:space:]]*(ssh-|ecdsa-|sk-)' "${AUTH_KEYS}"; then
  echo "ERROR: ${AUTH_KEYS} contains no valid SSH public key lines. Aborting." >&2
  exit 1
fi

echo "OK: ${DEPLOY_USER} has a populated authorized_keys -> safe to harden SSH."

# --- SSH hardening drop-in --------------------------------------------------
echo ">> Writing sshd drop-in: ${SSHD_DROPIN}"
install -d -m 755 /etc/ssh/sshd_config.d
cat > "${SSHD_DROPIN}" <<'EOF'
# Managed by ops/harden_server.sh â€” do not edit by hand.
# Key-only SSH, no root login. Restored by re-running the hardening script.
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
KbdInteractiveAuthentication no
EOF
chmod 644 "${SSHD_DROPIN}"

# --- Neutralize conflicting drop-ins (e.g. cloud-init) ----------------------
# sshd uses the FIRST value seen for each keyword, and /etc/ssh/sshd_config.d/*.conf
# is Included in alphabetical order. Ubuntu 24.04 cloud images (Linode included)
# commonly ship 50-cloud-init.conf containing 'PasswordAuthentication yes', which
# sorts BEFORE 99-hardening.conf and would SILENTLY override our settings.
# Comment out conflicting auth directives in every OTHER drop-in so ours win.
shopt -s nullglob
for f in /etc/ssh/sshd_config.d/*.conf; do
  [[ "${f}" == "${SSHD_DROPIN}" ]] && continue
  if grep -Eiq '^[[:space:]]*(PermitRootLogin|PasswordAuthentication|KbdInteractiveAuthentication|ChallengeResponseAuthentication)\b' "${f}"; then
    echo ">> Neutralizing conflicting SSH auth directives in ${f}"
    cp -a "${f}" "${f}.harden.bak.$(date +%s)"
    sed -ri 's/^([[:space:]]*(PermitRootLogin|PasswordAuthentication|KbdInteractiveAuthentication|ChallengeResponseAuthentication)\b.*)$/# disabled by harden_server.sh: \1/I' "${f}"
  fi
done
shopt -u nullglob

echo ">> Validating sshd configuration (sshd -t)"
if ! sshd -t; then
  echo "ERROR: 'sshd -t' failed; refusing to reload SSH. Drop-in left in place for inspection." >&2
  exit 1
fi

echo ">> Reloading SSH service (config reload, existing sessions kept alive)"
# Ubuntu 24.04 uses the 'ssh' unit (socket-activated 'ssh.socket' may also exist).
if systemctl list-unit-files | grep -q '^ssh\.service'; then
  systemctl reload ssh
elif systemctl list-unit-files | grep -q '^sshd\.service'; then
  systemctl reload sshd
else
  echo "WARN: could not find ssh/sshd service unit; attempting 'systemctl reload ssh'." >&2
  systemctl reload ssh
fi

# --- Firewall (UFW) ---------------------------------------------------------
echo ">> Configuring UFW firewall"
export DEBIAN_FRONTEND=noninteractive
if ! command -v ufw >/dev/null 2>&1; then
  echo ">> Installing ufw"
  apt-get update -y
  apt-get install -y ufw
fi

ufw default deny incoming
ufw default allow outgoing
# SSH (22) is the ONLY inbound port. No 80/443 â€” Cloudflare Tunnel is outbound.
ufw allow OpenSSH
ufw --force enable
ufw status verbose || true

# --- Unattended upgrades ----------------------------------------------------
echo ">> Installing + enabling unattended-upgrades"
apt-get update -y
apt-get install -y unattended-upgrades
# Non-interactive equivalent of 'dpkg-reconfigure unattended-upgrades':
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
systemctl enable --now unattended-upgrades || true

# --- Final reminders --------------------------------------------------------
cat <<EOF

============================================================================
 SSH and firewall hardening applied.

 *** DO NOT CLOSE THIS ROOT SESSION YET ***

 1) From a SECOND terminal, confirm key-only deploy login still works:
        ssh ${DEPLOY_USER}@45.33.29.100
    Only close this session once that succeeds. If it fails, you can revert
    by removing ${SSHD_DROPIN} and running 'systemctl reload ssh' here.

 2) Rotate the (previously exposed) root password now:
        passwd
    Root SSH login is already disabled, but rotate it anyway.

 Notes:
   - Inbound firewall now allows ONLY SSH (22). No 80/443 by design;
     public access is the outbound Cloudflare Tunnel (cloudflared).
   - Root SSH login: DISABLED.  Password auth: DISABLED (key-only).
   - Conflicting auth directives in other sshd_config.d drop-ins (e.g.
     50-cloud-init.conf) were commented out; *.harden.bak.* backups kept.
   - Automatic security updates: ENABLED (unattended-upgrades).
============================================================================
EOF

echo "HARDEN_DONE"
