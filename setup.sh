#!/usr/bin/env bash
# ============================================================
#  Nova — one-command setup (macOS / Linux)
#  Creates an isolated environment, installs Nova, and opens
#  the console with demo data. No API key needed to explore.
# ============================================================
set -e

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not on PATH. Install Python 3.11+ from https://python.org and re-run."
  exit 1
fi

echo "[1/3] Creating virtual environment (.venv)..."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "[2/3] Installing Nova and dependencies..."
python -m pip install --upgrade pip >/dev/null
pip install -e .

echo "[3/3] Launching the Nova console..."
echo
echo "  The browser will open at http://127.0.0.1:8765"
echo "  Demo data is loaded automatically — no API key required to explore."
echo "  For live AI: copy .env.example to .env and add a free Gemini key"
echo "  (https://aistudio.google.com/apikey), then restart."
echo
nova web
