#!/usr/bin/env bash
# Read-only production readiness checks for the classroom operator.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

test -f server/.env || { echo "Missing server/.env" >&2; exit 1; }
grep -q '^VIBE_ENVIRONMENT=production$' server/.env || { echo "VIBE_ENVIRONMENT must be production" >&2; exit 1; }
grep -q '^VIBE_SESSION_HTTPS_ONLY=true$' server/.env || { echo "VIBE_SESSION_HTTPS_ONLY must be true" >&2; exit 1; }
! grep -q 'replace-with\|vibe.example.com' server/.env || { echo "Replace every placeholder in server/.env" >&2; exit 1; }

docker compose ps
curl --fail --silent --show-error -H 'Host: localhost' http://127.0.0.1:8000/health
echo
echo "Local service health check passed. Verify the public HTTPS URL from a separate network next."

