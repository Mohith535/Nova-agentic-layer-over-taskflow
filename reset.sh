#!/usr/bin/env bash
# ============================================================
#  Nova — reset to a fresh state (for re-testing the setup)
#  Removes this folder's .venv + .env, the demo board data in
#  ~/.taskflow, and a sibling opportunity-hunter clone.
#  Leaves the Nova source intact — just re-run setup.sh afterwards.
# ============================================================
set -e

echo "This will DELETE:"
echo "   - .venv                   (the virtual environment here)"
echo "   - .env                    (your saved keys here)"
echo "   - ~/.taskflow             (Nova's demo / board data)"
echo "   - ../opportunity-hunter   (only if it exists)"
echo
read -r -p "Type  yes  to confirm: " ok
if [ "$ok" != "yes" ]; then
  echo "Cancelled — nothing was deleted."
  exit 0
fi

rm -rf .venv .env "$HOME/.taskflow" ../opportunity-hunter

echo
echo "Done. Re-run  bash setup.sh  for a fresh install."
echo "(For a 100% clean test, delete this whole 'nova' folder and re-clone.)"
