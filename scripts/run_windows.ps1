param([switch]$Demo, [string]$DataDir = "")
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Install 64-bit Python 3.12 from python.org, then run this script again." }
    & .\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple -r requirements.lock
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
}
$env:PYTHONPATH = Join-Path (Get-Location) "src"
$launchArgs = @("-m", "slitlamp")
if ($Demo) { $launchArgs += "--demo" }
if ($DataDir) { $launchArgs += @("--data-dir", $DataDir) }
& .\.venv\Scripts\python.exe @launchArgs
exit $LASTEXITCODE
