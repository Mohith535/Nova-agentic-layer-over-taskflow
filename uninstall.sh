#!/usr/bin/env bash
# ============================================================
#  Nova - uninstaller (macOS / Linux). Removes Nova and/or its
#  companions, and (only if you ask) your data. Data is kept by
#  default; nothing is deleted until you confirm.  bash uninstall.sh
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Step out of the Nova folder so it can be fully removed if you uninstall Nova.
cd "$HOME" 2>/dev/null || cd /
if command -v python3 >/dev/null 2>&1; then
  python3 "$SCRIPT_DIR/uninstall.py"
else
  python "$SCRIPT_DIR/uninstall.py"
fi
