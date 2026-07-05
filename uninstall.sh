#!/usr/bin/env bash
# ============================================================
#  Nova - uninstaller (macOS / Linux). Removes Nova and/or its
#  companions, and (only if you ask) your data. Data is kept by
#  default; nothing is deleted until you confirm.  bash uninstall.sh
# ============================================================
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  python3 uninstall.py
else
  python uninstall.py
fi
