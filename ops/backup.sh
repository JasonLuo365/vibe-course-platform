#!/usr/bin/env bash
# Create a consistent archive of the Docker data volume while the app is running.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
STAMP="$(date -u +%Y%m%d-%H%M%SZ)"
ARCHIVE="$BACKUP_DIR/vibe-data-$STAMP.tar.gz"
TMP_ARCHIVE="$ARCHIVE.partial"

mkdir -p "$BACKUP_DIR"
cd "$ROOT_DIR"
docker compose ps --status running --services | grep -qx server || {
  echo "The server container is not running; start it before backing up." >&2
  exit 1
}

umask 077
docker compose exec -T server tar czf - -C /data . > "$TMP_ARCHIVE"
test -s "$TMP_ARCHIVE"
mv "$TMP_ARCHIVE" "$ARCHIVE"
sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"
echo "Backup created: $ARCHIVE"

