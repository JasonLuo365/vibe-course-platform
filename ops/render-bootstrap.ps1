param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^https://')]
    [string]$MarketplaceUrl,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^https://')]
    [string]$ServerUrl,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+([-.][0-9A-Za-z.]+)?$')]
    [string]$Version,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$root = Split-Path -Parent $PSScriptRoot
$templatePath = Join-Path $root 'client\scripts\bootstrap.ps1'
$template = Get-Content -LiteralPath $templatePath -Raw -Encoding utf8

if ($template -notmatch 'https://TODO/course-marketplace' -or
    $template -notmatch 'https://TODO/vibe-submit') {
    throw 'The bootstrap template no longer contains the expected placeholders.'
}

$rendered = $template.Replace('https://TODO/course-marketplace', $MarketplaceUrl).
    Replace('https://TODO/vibe-submit', $ServerUrl).
    Replace('$VIBE_SUBMIT_VERSION    = "0.1.2"', ('$VIBE_SUBMIT_VERSION    = "' + $Version + '"'))

$outDir = Split-Path -Parent $OutputPath
if ($outDir) {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
}
[System.IO.File]::WriteAllText(
    [System.IO.Path]::GetFullPath($OutputPath),
    $rendered,
    [System.Text.UTF8Encoding]::new($false)
)
Write-Host "Generated student bootstrap script: $OutputPath"
