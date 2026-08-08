#Requires -Version 5.1
<#
.SYNOPSIS
  Run a repo script inside WSL via ASCII paths only (no Chinese /mnt paths, no inline bash $).

.EXAMPLE
  powershell -NoProfile -File C:\dev\Android_SMS_Classifier\tools\wsl_run.ps1 -RelPath training\scripts\foo.sh
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$RelPath,

    [string]$Distro = "Ubuntu-22.04",

    [string]$WinRoot = "C:\dev\Android_SMS_Classifier",

    [string]$InnerRel = "tools/wsl_run_inner.sh",

    [string]$WslRoot = "/home/colab/projects/Android_SMS_Classifier"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $WinRoot)) {
    throw "Windows ASCII root missing: $WinRoot (create junction to the real repo first)"
}

$relUnix = (($RelPath -replace "\\", "/").TrimStart("/"))
$winFile = Join-Path $WinRoot ($relUnix -replace "/", "\")
if (-not (Test-Path -LiteralPath $winFile)) {
    throw "Script not found under ASCII Windows root: $winFile"
}

$innerWin = Join-Path $WinRoot ($InnerRel -replace "/", "\")
if (-not (Test-Path -LiteralPath $innerWin)) {
    throw "Inner runner missing: $innerWin"
}
# Ensure LF endings so bash on WSL does not choke on CRLF from Windows editors.
$innerText = [System.IO.File]::ReadAllText($innerWin) -replace "`r`n", "`n" -replace "`r", "`n"
$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($innerWin, $innerText, $utf8)

$innerUnix = "/mnt/c/dev/Android_SMS_Classifier/" + ($InnerRel -replace "\\", "/")
# Intentionally pass paths as argv — do not embed bash variables on this command line.
& wsl -d $Distro -- env "WSL_RUN_ROOT=$WslRoot" bash $innerUnix $relUnix
exit $LASTEXITCODE
