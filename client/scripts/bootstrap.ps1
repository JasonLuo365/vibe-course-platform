# Vibe-submit bootstrap script for a classroom release.
# The course maintainer replaces the placeholders before distributing this file.
$COURSE_MARKETPLACE_URL = "https://TODO/course-marketplace.git"
$COURSE_SERVER_URL      = "https://TODO/vibe-submit"
$VIBE_SUBMIT_VERSION    = "0.1.5"
$COURSE_CLIENT_SOURCE   = "git+https://github.com/JasonLuo365/vibe-course-marketplace.git@v$VIBE_SUBMIT_VERSION#subdirectory=packages/vibe-submit"

# Ensure uv is available so we can run the client through its reviewed GitHub tag.
if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
    if (-not $env:UV_INDEX_URL) {
        $env:UV_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"
    }
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

    $localBin = Join-Path $env:USERPROFILE ".local\bin"
    if ($env:PATH -notlike "*$localBin*") {
        $env:PATH = "$localBin;$env:PATH"
    }
}

uvx --from $COURSE_CLIENT_SOURCE vibe-submit bootstrap `
    --marketplace-url $COURSE_MARKETPLACE_URL `
    --server $COURSE_SERVER_URL `
    @args
