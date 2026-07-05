#!/usr/bin/env bash
# ============================================================
#  Nova — launch the console (after setup.sh has installed it)
#  Run  bash run.sh  any time to open Nova.
# ============================================================
set -e

if [ ! -f ".venv/bin/activate" ]; then
  echo "No environment found here. Run  bash setup.sh  first."
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
nova web
