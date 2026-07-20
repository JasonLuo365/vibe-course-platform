#!/usr/bin/env bash
# Render the macOS/Linux student bootstrap script for one classroom release.
set -euo pipefail

usage() {
    echo "Usage: $0 --marketplace-url URL --server-url URL --version VERSION --output PATH" >&2
    exit 2
}

marketplace_url=""
server_url=""
version=""
output_path=""

while (($#)); do
    case "$1" in
        --marketplace-url) marketplace_url="${2:-}"; shift 2 ;;
        --server-url) server_url="${2:-}"; shift 2 ;;
        --version) version="${2:-}"; shift 2 ;;
        --output) output_path="${2:-}"; shift 2 ;;
        *) usage ;;
    esac
done

[[ "$marketplace_url" == https://* && "$server_url" == https://* && -n "$version" && -n "$output_path" ]] || usage

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
template_path="$root/client/scripts/bootstrap.sh"

escape_sed() {
    printf '%s' "$1" | sed 's/[&|]/\\&/g'
}

mkdir -p "$(dirname "$output_path")"
sed \
    -e "s|https://TODO/course-marketplace|$(escape_sed "$marketplace_url")|g" \
    -e "s|https://TODO/vibe-submit|$(escape_sed "$server_url")|g" \
    -e "s|VIBE_SUBMIT_VERSION=\"0.1.2\"|VIBE_SUBMIT_VERSION=\"$(escape_sed "$version")\"|g" \
    "$template_path" > "$output_path"
chmod 700 "$output_path"
echo "Generated macOS/Linux student bootstrap script: $output_path"
