#!/usr/bin/env bash
# Simple PyInstaller build script for the testr dashboard.
set -euo pipefail

if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "PyInstaller is not installed. Install with: pip install pyinstaller" >&2
  exit 1
fi

TARGET_OS="${1:-$(uname -s | tr '[:upper:]' '[:lower:]')}"
if [[ "$TARGET_OS" == *mingw* || "$TARGET_OS" == *msys* || "$TARGET_OS" == *cygwin* ]]; then
  TARGET_OS="windows"
elif [[ "$TARGET_OS" == "darwin" ]]; then
  TARGET_OS="macos"
elif [[ "$TARGET_OS" == "linux" ]]; then
  TARGET_OS="linux"
fi

if [[ "$TARGET_OS" == "windows" ]]; then
  echo "Note: PyInstaller cannot cross-compile Windows binaries from Linux/macOS. Run this script on Windows for a .exe." >&2
elif [[ "$TARGET_OS" == "macos" ]]; then
  echo "macOS is not targeted here; run on Linux or Windows." >&2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

COMMON_OPTS=(
  --name testr
  --onefile
  --clean
  --console
  --collect-all textual
  --collect-all trogon
)

echo "Building testr with PyInstaller..."
pyinstaller "${COMMON_OPTS[@]}" testr.py
echo "Done. Binaries are in dist/ (testr or testr.exe)."
