#!/bin/sh
# Run as root, or as a user that can read the game database and write backups.
# Creates an ONLINE-CONSISTENT snapshot using sqlite3's backup facility.
set -eu
umask 077
DATA_DIR="${DATA_DIR:-/var/lib/signal199x}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/signal199x}"
DATE="$(date -u '+%Y%m%dT%H%M%SZ')"
mkdir -p "$BACKUP_DIR"
sqlite3 "$DATA_DIR/game.sqlite" ".backup '$BACKUP_DIR/signal199x-$DATE.sqlite'"
printf 'Backup completed: %s\n' "$BACKUP_DIR/signal199x-$DATE.sqlite"
# IMPORTANT: replicate backup to an encrypted OFF-SERVER destination.
