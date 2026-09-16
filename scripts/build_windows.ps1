$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
python -m pip install --index-url https://pypi.org/simple -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
python -m pip install --index-url https://pypi.org/simple "pyinstaller>=6,<7"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller installation failed." }
python -m PyInstaller --noconfirm --clean --windowed --name SlitlampStudio --paths src --collect-all imageio_ffmpeg --collect-all pydicom --collect-all pynetdicom --hidden-import PySide6.QtMultimediaWidgets --add-data "README.md;." --add-data "docs;docs" scripts/desktop_entry.py
if ($LASTEXITCODE -ne 0) { throw "Windows application packaging failed." }
$compilerCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
$compiler = if ($compilerCommand) { $compilerCommand.Source } else { $null }
if (-not $compiler) {
    $candidate = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path $candidate) { $compiler = $candidate }
}
if ($compiler) {
    & $compiler installer/SlitlampStudio.iss
    if ($LASTEXITCODE -ne 0) { throw "Installer build failed." }
} else {
    Write-Host "Portable app created at dist/SlitlampStudio. Install Inno Setup 6 to create the installer."
}
