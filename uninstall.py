#!/usr/bin/env python3
"""
Nova — uninstaller.

Cleanly removes Nova and/or its companion apps (TaskFlow CLI, Opportunity Hunter) and the
global command shortcuts from this computer. Your data (tasks, history, behavioral profile) is
handled SEPARATELY and KEPT by default — nothing is deleted until you explicitly confirm.

    python uninstall.py          (or double-click uninstall.bat / run: bash uninstall.sh)

Design: safe-by-default. The uninstaller never runs from inside the environment it removes, so
it can delete the venv cleanly; it warns if Nova is still running; and it makes you type a word
before it touches any data. Anything you decline is left exactly as it was.
"""

from __future__ import annotations

import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

NOVA_DIR = Path(__file__).resolve().parent
HOME = Path.home()
TASKFLOW_DIR = HOME / ".taskflow"


# ── discovery helpers ───────────────────────────────────────────────────────

def _shim_paths(name: str) -> list[Path]:
    """Every location the setup wizard may have dropped a global launcher for `name`."""
    if os.name == "nt":
        la = Path(os.environ.get("LOCALAPPDATA", str(HOME / "AppData" / "Local")))
        return [la / "Microsoft" / "WindowsApps" / f"{name}.cmd",
                HOME / ".nova" / "bin" / f"{name}.cmd"]
    return [HOME / ".local" / "bin" / name]


def _nova_running() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 8765), timeout=0.5):
            return True
    except OSError:
        return False


def _rm(p: Path) -> bool:
    """Remove a file or folder. Returns True once it's actually gone.

    Crucially, this clears the read-only bit first: git clones (opportunity-hunter, taskflow)
    leave read-only files under .git, and on Windows a normal delete REFUSES those — which is
    exactly why an uninstall could 'do nothing' and leave the folders behind. We make everything
    writable, then delete. Works the same on Windows, macOS and Linux."""
    if not p.exists() and not p.is_symlink():
        return False
    try:
        if p.is_dir() and not p.is_symlink():
            for root, dirs, files in os.walk(p):
                for name in dirs + files:
                    try:
                        os.chmod(os.path.join(root, name), stat.S_IWRITE)
                    except OSError:
                        pass
            shutil.rmtree(p, ignore_errors=True)
        else:
            try:
                p.unlink()
            except PermissionError:
                os.chmod(p, stat.S_IWRITE)
                p.unlink()
        return not p.exists()
    except Exception as e:
        print(f"      ! Couldn't fully remove {p}\n        ({e})")
        return not p.exists()


def _schedule_self_delete(folder: Path) -> None:
    """Delete the Nova SOURCE folder too — the one thing a running program can't remove itself.
    We hand it to a tiny detached helper that waits a moment for this process to exit, then
    deletes the folder and itself. Cross-platform (a .bat on Windows, a shell script elsewhere)."""
    try:
        if os.name == "nt":
            script = Path(tempfile.gettempdir()) / "nova_cleanup.bat"
            # ping = a portable ~3s sleep; rmdir /s /q force-removes read-only git files too.
            script.write_text(
                "@echo off\r\n"
                "ping 127.0.0.1 -n 4 >nul\r\n"
                f'rmdir /s /q "{folder}"\r\n'
                'del "%~f0" >nul 2>&1\r\n',
                encoding="utf-8")
            subprocess.Popen(["cmd", "/c", str(script)],
                             creationflags=0x00000008 | 0x08000000,  # DETACHED_PROCESS | CREATE_NO_WINDOW
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            script = Path(tempfile.gettempdir()) / "nova_cleanup.sh"
            script.write_text(f'#!/bin/sh\nsleep 3\nrm -rf "{folder}"\nrm -f "$0"\n', encoding="utf-8")
            script.chmod(0o755)
            subprocess.Popen(["/bin/sh", str(script)], start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"      ✓ The Nova folder will be removed a few seconds after this window closes:\n"
              f"        {folder}")
    except Exception as e:
        print(f"      · Couldn't auto-remove the Nova folder ({e}). Delete it by hand:\n        {folder}")


# ── removal actions ─────────────────────────────────────────────────────────

def remove_global_shims() -> None:
    removed = []
    for name in ("nova", "taskflow"):
        for p in _shim_paths(name):
            if p.exists() and _rm(p):
                removed.append(name)
    if removed:
        print(f"      ✓ Global shortcuts removed ({', '.join(sorted(set(removed)))}). "
              "The apps themselves are untouched.")
    else:
        print("      · No global shortcuts were installed — nothing to remove there.")


def remove_taskflow_shim() -> None:
    for p in _shim_paths("taskflow"):
        if p.exists():
            _rm(p)


def remove_companion(folder: str, label: str) -> None:
    target = NOVA_DIR.parent / folder
    if target.exists():
        if _rm(target):
            print(f"      ✓ {label} removed  ({target}).")
    else:
        print(f"      · {label} not found next to Nova — skipping.")


def remove_nova_env() -> None:
    venv = NOVA_DIR / ".venv"
    if venv.exists():
        if _rm(venv):
            print(f"      ✓ Nova's environment removed  ({venv}).")
    else:
        print("      · No environment (.venv) found — already gone.")
    # The 'Open Nova' launch descriptor is meaningless once Nova's env is gone.
    _rm(TASKFLOW_DIR / "nova_launch.json")
    for name in ("nova", "taskflow"):
        for p in _shim_paths(name):
            if p.exists():
                _rm(p)


def remove_data() -> None:
    if TASKFLOW_DIR.exists():
        if _rm(TASKFLOW_DIR):
            print(f"      ✓ Local data deleted  ({TASKFLOW_DIR}).")
    else:
        print("      · No local data folder found.")


# ── interactive flow ────────────────────────────────────────────────────────

def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _menu() -> str:
    print("""
  What would you like to remove?

     [1]  Global shortcuts only
          The  nova / taskflow  commands stop working from any terminal. The apps
          themselves stay installed — you can still open Nova with  run.bat.

     [2]  Opportunity Hunter
          Removes the opportunity-hunter folder next to Nova.

     [3]  TaskFlow CLI
          Removes the taskflow folder and the 'taskflow' command.

     [4]  Nova  (and its environment)
          Removes the .venv (Nova and everything installed into it) plus the
          shortcuts. The nova source folder you can delete by hand afterwards.

     [5]  Everything
          Nova + TaskFlow CLI + Opportunity Hunter + shortcuts.

     [0]  Cancel — change nothing.
""")
    while True:
        c = _ask("  Your choice [0-5]: ")
        if c in ("0", "1", "2", "3", "4", "5"):
            return c
        print("  Please type a number from 0 to 5.")


def _ask_about_data() -> bool:
    """Return True only if the user makes a deliberate, typed choice to DELETE local data."""
    print("""
  ──  YOUR DATA  ──────────────────────────────────────────────────────────
  Your tasks, history and behavioral profile live in:
      {tf}

  This data is stored in TWO places for safety: locally on this computer, and —
  if you turned on cloud sync — in your own private GitHub repo. Deleting the
  local copy is permanent, so if it isn't already synced to the cloud, sync it
  first (open Nova/TaskFlow and run a sync) or you'll lose it for good.
  """.format(tf=TASKFLOW_DIR))
    print("  Keep your data for a future reinstall, or delete it?")
    print("      [K]  Keep it   (default, recommended)")
    print("      [D]  Delete it (permanent)")
    ans = _ask("  Keep or delete? [K/d]: ").lower()
    if ans not in ("d", "delete"):
        print("      · Keeping your data. It stays exactly where it is.")
        return False
    print("\n  This permanently deletes your local data. If it isn't synced to the cloud,")
    print("  it cannot be recovered.")
    confirm = _ask("  Type  DELETE  (in capitals) to confirm, or Enter to keep: ")
    if confirm == "DELETE":
        return True
    print("      · Not deleted — keeping your data.")
    return False


def main() -> int:
    print("\n" + "=" * 62)
    print("   ✦  N O V A  —  U N I N S T A L L E R")
    print("=" * 62)
    print("\n  Removes Nova and/or its companions from this computer. Your data is kept")
    print("  by default, and nothing is deleted until you confirm.")

    if not sys.stdin.isatty():
        print("\n  Not an interactive terminal — run  python uninstall.py  in a real terminal.")
        return 0

    choice = _menu()
    if choice == "0":
        print("\n  Cancelled. Nothing was changed.\n")
        return 0

    # Map the choice to a concrete plan.
    plan = {
        "1": {"shims"},
        "2": {"hunter"},
        "3": {"taskflow"},
        "4": {"nova"},
        "5": {"nova", "hunter", "taskflow", "shims"},
    }[choice]

    # Warn if Nova is still running and we're about to remove its environment.
    if "nova" in plan and _nova_running():
        print("\n  ⚠ Nova appears to be RUNNING right now. Close it first (Ctrl+C in its")
        print("    window / close the console) so its files aren't locked, then re-run this.")
        if _ask("    Continue anyway? (y/N): ").lower() not in ("y", "yes"):
            print("\n  Stopped. Nothing was changed.\n")
            return 0

    # Data is only relevant when an app (not just shortcuts) is being removed.
    delete_data = _ask_about_data() if plan & {"nova", "hunter", "taskflow"} else False

    # Final plain-English confirmation of everything that will happen.
    print("\n  ──  ABOUT TO REMOVE  ───────────────────────────────────────────────────")
    if "nova" in plan:
        print("      · Nova's environment (.venv) and all global shortcuts")
    if "hunter" in plan:
        print("      · Opportunity Hunter (folder)")
    if "taskflow" in plan:
        print("      · TaskFlow CLI (folder + command)")
    if plan == {"shims"}:
        print("      · Global shortcuts only (apps stay installed)")
    print("      · Your data: " + ("DELETE permanently" if delete_data else "KEEP (untouched)"))
    if _ask("\n  Proceed? Type 'yes' to confirm: ").lower() != "yes":
        print("\n  Cancelled. Nothing was changed.\n")
        return 0

    print("\n  Working…")
    if "hunter" in plan:
        remove_companion("opportunity-hunter", "Opportunity Hunter")
    if "taskflow" in plan:
        remove_companion("taskflow", "TaskFlow CLI")
        remove_taskflow_shim()
    if "nova" in plan:
        remove_nova_env()
    if plan == {"shims"}:
        remove_global_shims()
    if delete_data:
        remove_data()

    # Closing guidance — including the one thing an uninstaller can't do to itself.
    print("\n" + "=" * 62)
    print("   ✦  DONE")
    print("=" * 62)
    if "nova" in plan:
        _schedule_self_delete(NOVA_DIR)
    if not delete_data and (plan & {"nova", "hunter", "taskflow"}):
        print(f"\n  Your data was kept at  {TASKFLOW_DIR}  — reinstalling later picks up right")
        print("  where you left off.")
    print("\n  Thanks for trying Nova.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
