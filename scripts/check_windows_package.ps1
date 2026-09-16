$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$report = Join-Path $PWD "test-results/package-check.json"
New-Item -ItemType Directory -Force (Split-Path $report) | Out-Null
$process = Start-Process -FilePath "dist/SlitlampStudio/SlitlampStudio.exe" -ArgumentList @("--package-check", ('"' + $report + '"')) -PassThru
if (-not $process.WaitForExit(60000)) {
    Stop-Process -Id $process.Id -Force
    throw "The packaged application did not finish its demo check within 60 seconds."
}
if ($process.ExitCode -ne 0 -or -not (Test-Path $report)) {
    if (Test-Path $report) { Get-Content $report }
    throw "The packaged application failed to launch or complete its demo check."
}
$result = Get-Content $report -Raw | ConvertFrom-Json
if (-not $result.success) { throw $result.error }
Get-Content $report
