$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $scriptDir
$projectDir = (Resolve-Path $projectDir).Path
$distro = if ($env:WSL_DISTRO) { $env:WSL_DISTRO } else { "Ubuntu-22.04" }

if ($projectDir -match '^([A-Za-z]):\\(.*)$') {
    $drive = $Matches[1].ToLowerInvariant()
    $rest = $Matches[2] -replace '\\', '/'
    $wslProjectDir = "/mnt/$drive/$rest"
}
else {
    throw "当前辅助脚本只支持 Windows 盘符路径：$projectDir"
}

& wsl.exe -d "$distro" -u root --cd "$wslProjectDir" /root/miniforge3/bin/conda run -n agent python -m agent_edge.web_app
