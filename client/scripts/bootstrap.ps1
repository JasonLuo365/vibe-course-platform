# vibe-submit bootstrap entry script for the course README.
# Course maintainer: replace the placeholders below before distributing.
$COURSE_MARKETPLACE_URL = "https://TODO/course-marketplace"
$COURSE_SERVER_URL      = "https://TODO/vibe-submit"
$VIBE_SUBMIT_VERSION    = "0.1.0"   # pin to the release you want students to use

# Ensure uv is available so we can run the client via uvx.
if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
    if (-not $env:UV_INDEX_URL) {
        $env:UV_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"
    }
    # Mirror is injected into the installer environment only; no global pip/uv config is touched.
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

    # The installer updates the user PATH, but this process needs the binary dir now.
    $localBin = Join-Path $env:USERPROFILE ".local\bin"
    if ($env:PATH -notlike "*$localBin*") {
        $env:PATH = "$localBin;$env:PATH"
    }
}

# Launch the bootstrap subcommand with course defaults; extra args are forwarded.
uvx --from "vibe-submit==$VIBE_SUBMIT_VERSION" vibe-submit bootstrap `
    --marketplace-url $COURSE_MARKETPLACE_URL `
    --server $COURSE_SERVER_URL `
    @args
