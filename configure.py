#!/usr/bin/env python3
"""
Nova — one-command configuration wizard.

Run this once after setup to enter your personal keys. Everything is optional
except the Gemini key (which unlocks the live AI agents); press Enter to skip
anything you don't want yet, and re-run this any time to add or change a key.

    python configure.py

It writes to the right places automatically:
  • Nova live AI            → <nova>/.env                 (GEMINI_API_KEY)
  • Opportunity Hunter      → <hunter>/.env               (ntfy, Groq, Telegram, sync)  [if present]
  • TaskFlow cloud sync     → ~/.taskflow/.env.sync       (sync token)

Nothing is echoed back once entered, and existing values you don't change are preserved.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

NOVA_DIR = Path(__file__).resolve().parent
HOME = Path.home()
TASKFLOW_DIR = HOME / ".taskflow"
HUNTER_REPO = "https://github.com/Mohith535/opportunity-hunter.git"
TASKFLOW_REPO = "https://github.com/Mohith535/TaskFlow.git"


# ── env-file helpers ────────────────────────────────────────────────────────

def ensure_from_example(env_path: Path, example_path: Path) -> None:
    """Create .env from .env.example if absent — keeps the template's helpful comments."""
    if not env_path.exists() and example_path.exists():
        shutil.copy2(example_path, env_path)


# Values shipped in .env.example are placeholders, not real keys — treat them as unset so
# a freshly-copied .env never shows "already set" for something the user hasn't entered.
_PLACEHOLDER_MARKERS = ("your-", "-here", "your_", "set-your-own", "your key", "changeme", "xxxx")


def _is_placeholder(v: str) -> bool:
    lv = (v or "").strip().lower()
    return (not lv) or any(m in lv for m in _PLACEHOLDER_MARKERS)


def read_key(env_path: Path, key: str) -> str:
    """Current REAL value of KEY in a .env file — '' if unset, missing, or a placeholder."""
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith(f"{key}=") and not s.startswith("#"):
            v = s.split("=", 1)[1].strip()
            return "" if _is_placeholder(v) else v
    return ""


def set_key(env_path: Path, key: str, value: str) -> None:
    """Update KEY=value in place (or append), preserving every other line + comment."""
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith(f"{key}=") and not s.startswith("#"):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def find_hunter() -> Path | None:
    """Locate the Opportunity Hunter: NOVA_HUNTER_ROOT env, then common sibling folders."""
    candidates: list[Path] = []
    env = os.environ.get("NOVA_HUNTER_ROOT")
    if env:
        candidates.append(Path(env))
    parent = NOVA_DIR.parent
    for name in ("agent for my self", "opportunity-hunter", "ophunter", "agent", "OPHunter"):
        candidates.append(parent / name)
    for c in candidates:
        try:
            if c.is_dir() and (c / "main.py").exists():
                return c
        except OSError:
            continue
    return None


# ── interactive prompt ──────────────────────────────────────────────────────

def _mask(v: str) -> str:
    """Show just enough of a saved value to recognise it, never enough to leak it."""
    v = (v or "").strip()
    return (v[:5] + "…" + v[-3:]) if len(v) > 10 else "•" * len(v)


def prompt(label: str, where: str, current: str = "", required: bool = False) -> str | None:
    """Ask for one value. Returns the new value, or None to leave unchanged/skip.
    When a value is already saved, show it masked so you know what's there without exposing it."""
    if current:
        status = f"  (current: {_mask(current)} — Enter to keep)"
    elif required:
        status = "  (REQUIRED for live AI)"
    else:
        status = "  (optional — Enter to skip)"
    print(f"\n  {label}{status}")
    print(f"    ↳ {where}")
    try:
        val = input("    > ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  Skipped.")
        return None
    return val or None


def check_gemini(key: str) -> None:
    """Validate a freshly-entered Gemini key live — non-blocking: it always saves, and only
    tells you whether the key actually works so a typo is caught now, not mid-demo."""
    try:
        from nova.config import validate_gemini_key
    except Exception:
        return  # nova not importable yet (shouldn't happen after install) — skip quietly
    print("    Verifying the key…")
    res = validate_gemini_key(key)
    if res is True:
        print("    ✓ Verified — the live AI agents are ready.")
    elif res is False:
        print("    ⚠ That key was rejected — it looks wrong. Saved anyway; re-run to fix it.")
    else:
        print("    (Couldn't reach Google to verify right now — saved. Run `nova doctor` to re-check.)")


def section(title: str) -> None:
    print("\n" + "─" * 60)
    print(f"  {title}")
    print("─" * 60)


def offer_taskflow(wrote: list[str]) -> None:
    """Offer to install the TaskFlow CLI — the behavioral task manager Nova is built on.
    Optional: Nova runs on demo data without it; install it to manage a real board and
    get the 'taskflow' command. Installs into the current venv (deps are light, no conflict)."""
    section("2. TASKFLOW CLI  ·  optional add-on")
    print("  TaskFlow is the behavioral task manager Nova is built on — a command-line app")
    print("  (plus a local dashboard) for capturing and running your tasks. Nova reads its")
    print("  data to coach you. Install it to manage a REAL board instead of the bundled demo.")
    print("  Optional — Nova works great on demo data without it.")
    try:
        ans = input("\n  Install the TaskFlow CLI now? (y/N): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if ans not in ("y", "yes"):
        print("  Skipped. You can add it later by re-running  python configure.py.")
        return

    if not shutil.which("git"):
        print("  ! git isn't on PATH — install Git, then re-run `python configure.py`. Skipping.")
        return

    target = NOVA_DIR.parent / "taskflow"
    if target.exists() and (target / "pyproject.toml").exists():
        print(f"  Using existing folder: {target}")
    else:
        print(f"  Cloning into {target} …")
        try:
            rc = subprocess.run(["git", "clone", "--depth", "1", TASKFLOW_REPO, str(target)]).returncode
        except Exception as e:
            print(f"  ! Clone failed ({e}). Skipping — you can clone it manually later."); return
        if rc != 0 or not (target / "pyproject.toml").exists():
            print("  ! Clone did not complete. Skipping."); return

    print("  Installing TaskFlow — this gives you the 'taskflow' command …")
    try:
        subprocess.run([_venv_python(), "-m", "pip", "install", "-q", "-e", str(target)])
    except Exception as e:
        print(f"  ! Install hit a snag ({e}); you can run it later. Continuing.")
        return
    wrote.append("TaskFlow CLI — cloned + installed ('taskflow' command)")
    print("  ✓ TaskFlow installed. Try:  taskflow today   or   taskflow dump \"a task #inbox\"")


def offer_hunter(wrote: list[str]) -> Path | None:
    """Describe the Opportunity Hunter and, if the user wants it, clone + install + link it
    to Nova. Returns its path (so the caller can configure its keys), or None if declined.
    Optional and personal — most users skip it, so it is never installed without a yes."""
    section("3. OPPORTUNITY HUNTER  ·  optional add-on")
    print("  A separate agent that scans ~11 sources every day (Devpost, MLH, GitHub, arXiv,")
    print("  coding contests, Reddit…) for hackathons, internships, fellowships and research —")
    print("  scores each 1-10 against your profile and pushes the best to your phone and your")
    print("  task board. Nova's Scout agent commands it from chat.")
    print("  It's optional and personal — most people can safely skip it.")
    try:
        ans = input("\n  Set up the Opportunity Hunter now? (y/N): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return None
    if ans not in ("y", "yes"):
        print("  Skipped. Re-run `python configure.py` any time to add it.")
        return None

    if not shutil.which("git"):
        print("  ! git isn't on PATH — install Git, then re-run `python configure.py`. Skipping.")
        return None

    target = NOVA_DIR.parent / "opportunity-hunter"
    if target.exists() and (target / "main.py").exists():
        print(f"  Using existing folder: {target}")
    else:
        print(f"  Cloning into {target} …")
        try:
            rc = subprocess.run(["git", "clone", "--depth", "1", HUNTER_REPO, str(target)]).returncode
        except Exception as e:
            print(f"  ! Clone failed ({e}). Skipping — you can clone it manually later."); return None
        if rc != 0 or not (target / "main.py").exists():
            print("  ! Clone did not complete. Skipping."); return None

    reqs = target / "requirements.txt"
    if reqs.exists():
        print("  Installing the Hunter's dependencies (this can take a minute) …")
        try:
            subprocess.run([_venv_python(), "-m", "pip", "install", "-q", "-r", str(reqs)])
        except Exception as e:
            print(f"  ! Dependency install hit a snag ({e}); you can run it later. Continuing.")

    # Tell Nova where the Hunter is AND which interpreter can run it (this venv now has its
    # deps, so point NOVA_HUNTER_PYTHON at ourselves — robust across machines).
    set_key(NOVA_DIR / ".env", "NOVA_HUNTER_ROOT", str(target))
    set_key(NOVA_DIR / ".env", "NOVA_HUNTER_PYTHON", _venv_python())
    wrote.append("Opportunity Hunter — cloned, installed, linked to Nova")
    print("  ✓ Opportunity Hunter installed and linked to Nova's Scout agent.")
    return target


# ── isolated-vs-global commands ─────────────────────────────────────────────

def _venv_python() -> str:
    """The interpreter that actually has the deps — prefer THIS repo's venv over whatever
    python happens to be running us. Then installs and helper scripts always hit the right
    environment, even when configure.py is re-run from a plain (non-activated) terminal."""
    cand = NOVA_DIR / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return str(cand) if cand.exists() else sys.executable


def _installed_commands() -> list[str]:
    """Console commands that actually exist in the venv (nova always; taskflow if installed)."""
    scripts = Path(_venv_python()).parent
    found = []
    for name in ("nova", "taskflow"):
        exe = scripts / (f"{name}.exe" if os.name == "nt" else name)
        if exe.exists():
            found.append(name)
    return found


def _install_global_shims(cmds: list[str]) -> bool:
    """Drop a thin launcher for each command onto the user's PATH so it works in any terminal.
    The launcher just calls the real command inside the isolated venv — nothing is copied or
    installed system-wide, so this stays clean and fully reversible (delete the shim to undo)."""
    scripts = Path(_venv_python()).parent
    made: list[str] = []
    if os.name == "nt":
        # WindowsApps is already on the default user PATH — dropping a .cmd there needs no PATH
        # surgery (setx truncates PATH; a corrupted PATH before a demo is unforgivable). Fall
        # back to a private bin dir only if WindowsApps somehow isn't present.
        appdir = Path(os.environ.get("LOCALAPPDATA", str(HOME / "AppData" / "Local")))
        target = appdir / "Microsoft" / "WindowsApps"
        if not target.is_dir():
            target = HOME / ".nova" / "bin"
            target.mkdir(parents=True, exist_ok=True)
        for name in cmds:
            try:
                # Use \n and let write_text translate to the platform newline once — writing
                # \r\n here would get re-translated to \r\r\n (a stray CR in the .cmd).
                (target / f"{name}.cmd").write_text(
                    f'@echo off\n"{scripts / (name + ".exe")}" %*\n', encoding="utf-8")
                made.append(name)
            except OSError as e:
                print(f"  ! Couldn't add the {name} shortcut ({e}).")
    else:
        target = HOME / ".local" / "bin"
        target.mkdir(parents=True, exist_ok=True)
        for name in cmds:
            try:
                shim = target / name
                shim.write_text(f'#!/bin/sh\nexec "{scripts / name}" "$@"\n', encoding="utf-8")
                shim.chmod(0o755)
                made.append(name)
            except OSError as e:
                print(f"  ! Couldn't add the {name} shortcut ({e}).")
    if not made:
        return False
    on_path = str(target).lower() in os.environ.get("PATH", "").lower()
    print(f"  ✓ Done — open a NEW terminal and type  {'  or  '.join(made)}  from anywhere.")
    if not on_path:
        if os.name == "nt":
            print(f"    If it isn't found, add this one folder to your PATH:  {target}")
        else:
            print("    Add this line to ~/.bashrc or ~/.zshrc, then reopen the terminal:")
            print(f'        export PATH="{target}:$PATH"')
    return True


def offer_global_commands() -> bool:
    """Let the user choose how to reach the commands: keep them ISOLATED (zero system footprint —
    the safe pick for anyone evaluating) or make them SYSTEM-WIDE (convenient for daily use).
    Returns True if made global. Isolated is the default because 'undo = delete the folder' is
    the least-scary promise you can make to someone installing a stranger's software."""
    cmds = _installed_commands()
    if not cmds:
        return False
    names = "  /  ".join(cmds)
    section("5. RUNNING THE COMMANDS  ·  isolated or system-wide")
    print("  Nova installed into a private environment inside this folder — that's exactly what")
    print("  keeps the rest of your computer untouched. One choice left: how do you want to")
    print(f"  reach the  {names}  command(s)?")
    print()
    print("     [Enter]  Isolated   —   best for trying Nova out")
    print("              The commands live only inside this folder. Nothing is added to your")
    print("              system; to remove Nova completely you just delete the folder.")
    print("              Re-open the console anytime with  run.bat  /  bash run.sh.")
    print()
    print("     g        System-wide   —   best for everyday use")
    print(f"              Type  {names}  in ANY terminal, anywhere. The program still lives")
    print("              safely in its isolated environment — we only place a tiny shortcut on")
    print("              your PATH that points to it. Fully reversible.")
    try:
        ans = input("\n  Enter for isolated, or 'g' for system-wide: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if ans not in ("g", "global", "s", "system", "y", "yes"):
        print("  Keeping it isolated — zero footprint. Launch with  run.bat  /  bash run.sh.")
        return False
    return _install_global_shims(cmds)


def main() -> int:
    print("\n" + "=" * 62)
    print("   ✦  N O V A  —  S E T U P   W I Z A R D")
    print("=" * 62)

    if not sys.stdin.isatty():
        print("\n  Not an interactive terminal — nothing to prompt. Edit the .env files by hand,")
        print("  or run `python configure.py` in a real terminal.")
        return 0

    # What you'll need — set expectations up front so nothing feels like a surprise.
    print("""
  Here's everything Nova can use — all free, and only the first is essential:

     Gemini API key     Nova's live AI agents           ·  essential
     Groq API key       sharper opportunity scoring     ·  optional
     ntfy topic         push alerts to your phone       ·  optional
     Telegram bot       act on tasks from your phone    ·  optional
     GitHub token       phone <-> cloud task sync        ·  optional

  You'll also be offered two optional companion apps to install:
     TaskFlow CLI       manage a real task board (the 'taskflow' command)
     Opportunity Hunter scans 11 sources daily for hackathons/internships

  Have any handy? Enter them below. Don't have one yet? Press Enter to skip it
  and add it later, any time, by running:   python configure.py
""")

    wrote: list[str] = []

    # 1) NOVA — the one that matters
    section("1. NOVA  ·  live AI agents (Gemini)")
    nova_env = NOVA_DIR / ".env"
    ensure_from_example(nova_env, NOVA_DIR / ".env.example")
    v = prompt("Gemini API key",
               "Get one free (30 sec): aistudio.google.com/apikey -> Create API key -> copy",
               read_key(nova_env, "GEMINI_API_KEY"), required=True)
    if v:
        set_key(nova_env, "GEMINI_API_KEY", v)
        wrote.append("Nova .env — Gemini key")
        check_gemini(v)

    # 2) TASKFLOW CLI — optional install (the board Nova reads)
    offer_taskflow(wrote)

    # 3) OPPORTUNITY HUNTER — detect it, or OFFER to install it (optional & personal)
    hunter = find_hunter()
    if not hunter:
        hunter = offer_hunter(wrote)
    if hunter:
        section(f"3. OPPORTUNITY HUNTER  ·  {hunter.name}")
        h_env = hunter / ".env"
        ensure_from_example(h_env, hunter / ".env.example")

        v = prompt("ntfy topic (free phone alerts)",
                   "Install the 'ntfy' app (Android: Play Store · iPhone: App Store), open it, "
                   "tap + to Subscribe, invent any secret word (e.g. mohith-hunt-7k2), and paste "
                   "that same word here.",
                   read_key(h_env, "NTFY_TOPIC"))
        if v:
            set_key(h_env, "NTFY_TOPIC", v); wrote.append("Hunter .env — ntfy topic")

        v = prompt("Groq API key (sharper AI scoring)",
                   "Free, no card: console.groq.com -> API Keys -> Create -> copy",
                   read_key(h_env, "GROQ_API_KEY"))
        if v:
            set_key(h_env, "GROQ_API_KEY", v); wrote.append("Hunter .env — Groq key")

        v = prompt("Telegram bot token (act from your phone)",
                   "In Telegram, open t.me/BotFather -> send /newbot -> follow prompts -> copy the token",
                   read_key(h_env, "TELEGRAM_BOT_TOKEN"))
        if v:
            set_key(h_env, "TELEGRAM_BOT_TOKEN", v); wrote.append("Hunter .env — Telegram token")
        v = prompt("Telegram chat id",
                   'Send /start to your bot, then paste-and-run this ONE line (it prints your\n'
                   '      id — press Ctrl+C after it appears). Use the full path shown — it points at\n'
                   "      Nova's environment, which has the Hunter's dependencies installed:\n"
                   f'          "{_venv_python()}" "{hunter / "telegram_listener.py"}"',
                   read_key(h_env, "TELEGRAM_CHAT_ID"))
        if v:
            set_key(h_env, "TELEGRAM_CHAT_ID", v); wrote.append("Hunter .env — Telegram chat id")

        # A confirmation run is only meaningful once there's a scoring key or a delivery
        # channel to exercise. With nothing configured, we say so plainly and skip it —
        # rather than run a heavy live scrape that can't notify or score with intelligence.
        has_hunter_key = any(read_key(h_env, k) for k in
                             ("GROQ_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY",
                              "NTFY_TOPIC", "TELEGRAM_BOT_TOKEN"))
        if not has_hunter_key:
            print("\n  The Hunter is installed and linked to Nova — but you haven't added a scoring")
            print("  key (Groq) or an alert channel (ntfy/Telegram) yet, so there's nothing to")
            print("  meaningfully confirm right now. Skipping the test run.")
            print("  Add a free Groq key later with `python configure.py`, then it's fully live.")
        else:
            try:
                go = input("\n  Run a quick confirmation hunt now? (dry run — scrapes & scores real\n"
                           "  sources, sends no alerts, adds no tasks)  (y/N): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                go = "n"
            if go in ("y", "yes"):
                print("\n  Confirmation run in progress — this can take a minute…\n")
                try:
                    subprocess.run([_venv_python(), "main.py", "--test"], cwd=str(hunter))
                    print("\n  ✓ A brief with 'scanned / relevant / new' counts above means the Hunter works.")
                except Exception as e:
                    print(f'  ! Couldn\'t run it here ({e}). Try directly:\n'
                          f'        cd "{hunter}"\n'
                          f'        "{_venv_python()}" main.py --test')

    # 3) TASKFLOW CLOUD SYNC — write both the sync token (TaskFlow) and repo (Hunter, if present)
    section("4. TASKFLOW CLOUD SYNC  ·  optional (phone ↔ cloud)")
    repo = prompt("Sync repo",
                  "Just  owner/name  (e.g. yourname/taskflow-sync). A full github.com URL is fine too — "
                  "I'll trim it.", "")
    if repo:
        # Accept a pasted URL and reduce it to owner/name.
        repo = repo.strip().rstrip("/")
        for pfx in ("https://github.com/", "http://github.com/", "git@github.com:", "github.com/"):
            if repo.lower().startswith(pfx):
                repo = repo[len(pfx):]
                break
        if repo.endswith(".git"):
            repo = repo[:-4]
    token = prompt("GitHub token (repo scope)", "https://github.com/settings/tokens/new  → check 'repo'", "")
    if token:
        set_key(TASKFLOW_DIR / ".env.sync", "TASKFLOW_SYNC_TOKEN", token)
        wrote.append("TaskFlow ~/.taskflow/.env.sync — sync token")
        if hunter:
            set_key(hunter / ".env", "TASKFLOW_SYNC_TOKEN", token)
    if repo and hunter:
        set_key(hunter / ".env", "TASKFLOW_SYNC_REPO", repo)
        wrote.append("Hunter .env — sync repo")

    # 5) HOW TO RUN — isolated (evaluator-safe, zero footprint) vs system-wide (daily use)
    went_global = offer_global_commands()

    # summary — never echo the secrets themselves
    print("\n" + "=" * 62)
    print("   ✦  SETUP COMPLETE")
    print("=" * 62)
    if wrote:
        print("\n  Saved:")
        for w in wrote:
            print(f"      · {w}")
    else:
        print("\n  No keys entered — that's fine. Nova runs fully on demo data.")

    gemini_ready = bool(read_key(nova_env, "GEMINI_API_KEY"))
    print("\n  WHAT'S NEXT")
    print("      1. Nova is about to open at  http://127.0.0.1:8765")
    if gemini_ready:
        print("      2. The live AI agents are ON — try 'Ask', 'Coach', or 'Operator'.")
    else:
        print("      2. No Gemini key yet, so explore on demo data. Add one any time to")
        print("         switch the live AI on:  python configure.py")
    taskflow_installed = any("TaskFlow CLI" in w for w in wrote)
    if taskflow_installed:
        print("      3. TaskFlow is installed — run  taskflow today  or  taskflow dump \"a task\".")
    if hunter:
        print(f"      {4 if taskflow_installed else 3}. The Opportunity Hunter is linked — ask Nova's 'Scout' to find or run a hunt.")
    print("\n  Change or add any key later, any time:   python configure.py")
    if went_global:
        print("  Commands are system-wide — in any NEW terminal you can run:")
        print("      nova web        open the console       ·   nova doctor   health check")
        if taskflow_installed:
            print("      taskflow today  your task board")
    else:
        print("  Open Nova again after closing it:         run.bat   (Windows)  ·  bash run.sh")
    print("=" * 62 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
