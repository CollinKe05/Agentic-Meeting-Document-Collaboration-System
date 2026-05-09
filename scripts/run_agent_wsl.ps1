param(
    [switch] $Mock,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Prompt
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $scriptDir
$projectDir = (Resolve-Path $projectDir).Path
$promptText = ($Prompt -join " ").Trim()

if (-not $promptText) {
    $promptText = "Please read demo_input.txt and count the length of my input."
}

if ($Mock) {
    $backend = "mock"
}
else {
    $backend = "ollama"
}

if ($projectDir -match '^([A-Za-z]):\\(.*)$') {
    $drive = $Matches[1].ToLowerInvariant()
    $rest = $Matches[2] -replace '\\', '/'
    $wslProjectDir = "/mnt/$drive/$rest"
}
else {
    throw "Only Windows drive paths are supported by this helper: $projectDir"
}

& wsl.exe -u root --cd "$wslProjectDir" env "AGENT_LLM_BACKEND=$backend" bash scripts/run_wsl.sh "$promptText"
