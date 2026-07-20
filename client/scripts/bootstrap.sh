#!/usr/bin/env bash
# Vibe-submit bootstrap script for a classroom release on macOS/Linux.
# The course maintainer replaces the placeholders before distributing this file.
set -euo pipefail

COURSE_MARKETPLACE_URL="https://TODO/course-marketplace.git"
COURSE_SERVER_URL="https://TODO/vibe-submit"
VIBE_SUBMIT_VERSION="0.1.2"
COURSE_CLIENT_SOURCE="git+https://github.com/JasonLuo365/vibe-course-marketplace.git@v${VIBE_SUBMIT_VERSION}#subdirectory=packages/vibe-submit"

# uv installs into the current user's home directory; administrator privileges are not needed.
if ! command -v uvx >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

uvx --from "$COURSE_CLIENT_SOURCE" vibe-submit bootstrap \
    --marketplace-url "$COURSE_MARKETPLACE_URL" \
    --server "$COURSE_SERVER_URL" \
    "$@"
