# Simple PyInstaller build script for the testr dashboard (Windows).
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    Write-Error "PyInstaller is not installed. Install with: pip install pyinstaller"
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $root "..")

$args = @(
    "--name", "testr",
    "--onefile",
    "--clean",
    "--console",
    "--collect-all", "textual",
    "--collect-all", "trogon",
    "testr.py"
)

Write-Host "Building testr with PyInstaller..."
pyinstaller @args
Write-Host "Done. Binaries are in dist\\ (testr.exe)."
