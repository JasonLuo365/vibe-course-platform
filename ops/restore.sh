#!/usr/bin/env bash
# Destructive recovery helper. It restores exactly one archive into the data volume.
set -euo pipefail

if [[ "${1:-}" != "--confirm" || -z "${2:-}" ]]; then
  echo "Usage: $0 --confirm /absolute/path/to/vibe-data-YYYYMMDD-HHMMSSZ.tar.gz" >&2
  exit 2
fi

ARCHIVE="$2"
[[ "$ARCHIVE" = /* && -f "$ARCHIVE" ]] || {
  echo "Use an existing absolute archive path." >&2
  exit 2
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
echo "This removes current application data and restores: $ARCHIVE"
read -r -p "Type RESTORE to continue: " answer
[[ "$answer" == "RESTORE" ]] || { echo "Cancelled."; exit 1; }

docker compose down
docker compose run --rm --no-deps \
  -v "$ARCHIVE:/restore/backup.tar.gz:ro" \
  --entrypoint sh server -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + && tar xzf /restore/backup.tar.gz -C /data'
docker compose up -d
echo "Restore completed. Run ops/preflight.sh and log in before opening the classroom."

