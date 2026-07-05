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

# Nova needs Python 3.11+ — fail with a clear message instead of a cryptic pip error later.
if ! python3 -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 11) else 1)"; then
  echo "Nova needs Python 3.11 or newer. You currently have:"
  python3 --version
  echo "Please install Python 3.11+ from https://python.org, then re-run: bash setup.sh"
  exit 1
fi

echo "[1/4] Creating virtual environment (.venv)..."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "[2/4] Installing Nova and dependencies..."
python -m pip install --upgrade pip >/dev/null
pip install -e .

echo "[3/4] Configuring your keys (interactive — press Enter to skip any)..."
echo
python configure.py

echo "[4/4] Launching the Nova console..."
echo
echo "  The browser will open at http://127.0.0.1:8765"
echo "  Demo data is loaded automatically — no API key required to explore."
echo "  (Re-run 'python configure.py' any time to add or change a key.)"
echo
nova web
