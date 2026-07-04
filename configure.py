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


# ── env-file helpers ────────────────────────────────────────────────────────

def ensure_from_example(env_path: Path, example_path: Path) -> None:
    """Create .env from .env.example if absent — keeps the template's helpful comments."""
    if not env_path.exists() and example_path.exists():
        shutil.copy2(example_path, env_path)


def read_key(env_path: Path, key: str) -> str:
    """Current value of KEY in a .env file, or '' if unset/missing."""
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith(f"{key}=") and not s.startswith("#"):
            return s.split("=", 1)[1].strip()
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

def prompt(label: str, where: str, current: str = "", required: bool = False) -> str | None:
    """Ask for one value. Returns the new value, or None to leave unchanged/skip."""
    status = "  (already set — Enter to keep)" if current else ("  (REQUIRED for live AI)" if required else "  (optional — Enter to skip)")
    print(f"\n  {label}{status}")
    print(f"    ↳ {where}")
    try:
        val = input("    > ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  Skipped.")
        return None
    return val or None


def section(title: str) -> None:
    print("\n" + "─" * 60)
    print(f"  {title}")
    print("─" * 60)


def offer_hunter(wrote: list[str]) -> Path | None:
    """Describe the Opportunity Hunter and, if the user wants it, clone + install + link it
    to Nova. Returns its path (so the caller can configure its keys), or None if declined.
    Optional and personal — most users skip it, so it is never installed without a yes."""
    section("2. OPPORTUNITY HUNTER  ·  optional add-on")
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
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(reqs)])
        except Exception as e:
            print(f"  ! Dependency install hit a snag ({e}); you can run it later. Continuing.")

    # Tell Nova where the Hunter is AND which interpreter can run it (this venv now has its
    # deps, so point NOVA_HUNTER_PYTHON at ourselves — robust across machines).
    set_key(NOVA_DIR / ".env", "NOVA_HUNTER_ROOT", str(target))
    set_key(NOVA_DIR / ".env", "NOVA_HUNTER_PYTHON", sys.executable)
    wrote.append("Opportunity Hunter — cloned, installed, linked to Nova")
    print("  ✓ Opportunity Hunter installed and linked to Nova's Scout agent.")
    return target


def main() -> int:
    print("\n" + "=" * 60)
    print("  NOVA — CONFIGURATION WIZARD")
    print("  Enter your keys once. Skip anything with Enter. Re-runnable.")
    print("=" * 60)

    if not sys.stdin.isatty():
        print("\n  Not an interactive terminal — nothing to prompt. Edit the .env files by hand,")
        print("  or run `python configure.py` in a real terminal.")
        return 0

    wrote: list[str] = []

    # 1) NOVA — the one that matters
    section("1. NOVA  ·  live AI agents (Gemini)")
    nova_env = NOVA_DIR / ".env"
    ensure_from_example(nova_env, NOVA_DIR / ".env.example")
    cur = read_key(nova_env, "GEMINI_API_KEY")
    cur = "" if cur in ("", "your-key-here") else cur
    v = prompt("Gemini API key", "Free, 1500 req/day: https://aistudio.google.com/apikey", cur, required=True)
    if v:
        set_key(nova_env, "GEMINI_API_KEY", v)
        wrote.append("Nova .env — Gemini key")

    # 2) OPPORTUNITY HUNTER — detect it, or OFFER to install it (optional & personal)
    hunter = find_hunter()
    if not hunter:
        hunter = offer_hunter(wrote)
    if hunter:
        section(f"2. OPPORTUNITY HUNTER  ·  {hunter.name}")
        h_env = hunter / ".env"
        ensure_from_example(h_env, hunter / ".env.example")

        v = prompt("ntfy topic (phone alerts)", "Any secret string; subscribe to it in the free ntfy app", read_key(h_env, "NTFY_TOPIC"))
        if v:
            set_key(h_env, "NTFY_TOPIC", v); wrote.append("Hunter .env — ntfy topic")

        v = prompt("Groq API key (opportunity scoring)", "Free, no card: https://console.groq.com", read_key(h_env, "GROQ_API_KEY"))
        if v:
            set_key(h_env, "GROQ_API_KEY", v); wrote.append("Hunter .env — Groq key")

        v = prompt("Telegram bot token (tap-to-act control)", "@BotFather → /newbot → paste the token", read_key(h_env, "TELEGRAM_BOT_TOKEN"))
        if v:
            set_key(h_env, "TELEGRAM_BOT_TOKEN", v); wrote.append("Hunter .env — Telegram token")
        v = prompt("Telegram chat id", "Message your bot /start after running: python telegram_listener.py", read_key(h_env, "TELEGRAM_CHAT_ID"))
        if v:
            set_key(h_env, "TELEGRAM_CHAT_ID", v); wrote.append("Hunter .env — Telegram chat id")

        # Prove it works on the spot — a DRY RUN: scrapes + scores, but sends no phone
        # push and adds no tasks. The fastest way to confirm the install is healthy.
        try:
            go = input("\n  Run a quick TEST hunt now to confirm it works? (y/N): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            go = "n"
        if go in ("y", "yes"):
            print("  Dry-run hunt (no phone push, no tasks added) — this can take a minute…\n")
            try:
                subprocess.run([sys.executable, "main.py", "--test"], cwd=str(hunter))
                print("\n  ✓ If you saw a brief above with scanned/relevant counts, the Hunter works.")
            except Exception as e:
                print(f"  ! Test hunt couldn't run ({e}). Try it directly: cd {hunter} && python main.py --test")

    # 3) TASKFLOW CLOUD SYNC — write both the sync token (TaskFlow) and repo (Hunter, if present)
    section("3. TASKFLOW CLOUD SYNC  ·  optional (phone ↔ cloud)")
    repo = prompt("Sync repo (owner/name)", "A PRIVATE GitHub repo, e.g. yourname/taskflow-sync", "")
    token = prompt("GitHub token (repo scope)", "https://github.com/settings/tokens/new  → check 'repo'", "")
    if token:
        set_key(TASKFLOW_DIR / ".env.sync", "TASKFLOW_SYNC_TOKEN", token)
        wrote.append("TaskFlow ~/.taskflow/.env.sync — sync token")
        if hunter:
            set_key(hunter / ".env", "TASKFLOW_SYNC_TOKEN", token)
    if repo and hunter:
        set_key(hunter / ".env", "TASKFLOW_SYNC_REPO", repo)
        wrote.append("Hunter .env — sync repo")

    # summary — never echo the secrets themselves
    print("\n" + "=" * 60)
    if wrote:
        print("  ✓ Saved:")
        for w in wrote:
            print(f"      · {w}")
    else:
        print("  Nothing changed — every field was skipped.")
    print("\n  Done. Launch Nova with:  nova web")
    print("  (Re-run `python configure.py` any time to add or change a key.)")
    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
