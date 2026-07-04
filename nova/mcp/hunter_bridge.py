"""HunterBridge — Nova's control surface over the Opportunity Hunter.

The coupling is deliberately **data + process, never code**: Nova reads the Hunter's output
file (see ``NovaTools.get_opportunities``) and — new with this bridge — can *launch* a hunt as
a detached subprocess and report the Hunter's health. It never imports the Hunter's modules,
so either project can be refactored freely.

Root resolution (first hit wins):
  1. ``NOVA_HUNTER_ROOT`` env var — explicit override.
  2. Derived from ``NOVA_OPPORTUNITIES_PATH`` (…/data/history.json → the project root).
  3. None — every method then degrades gracefully (status says "not connected", start
     refuses politely). Judges without the Hunter installed lose nothing.

Launch semantics: ``start_hunt`` fires ``<python> main.py --now`` detached (Popen, no wait) —
a real hunt does network scraping + LLM scoring and can take minutes, so blocking a chat turn
on it would be wrong. The caller gets {"started": True} immediately and can poll
``status()``, whose ``last_run`` timestamp moves when the hunt lands.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def _hunter_python() -> list[str]:
    """The interpreter that has the Hunter's deps (feedparser/rich/plyer).

    Nova's own venv does NOT have them, so ``sys.executable`` would crash the hunt.
    ``NOVA_HUNTER_PYTHON`` overrides; default is the Windows launcher ``py -3.12``
    (verified to carry the Hunter's requirements on this machine), else ``python3``.
    """
    override = os.environ.get("NOVA_HUNTER_PYTHON")
    if override:
        return override.split()
    if sys.platform == "win32":
        return ["py", "-3.12"]
    return ["python3"]


class HunterBridge:
    def __init__(self, root: Optional[str] = None) -> None:
        self.root = self._resolve_root(root)

    @staticmethod
    def _resolve_root(explicit: Optional[str]) -> Optional[Path]:
        candidates = []
        if explicit:
            candidates.append(Path(explicit))
        env_root = os.environ.get("NOVA_HUNTER_ROOT")
        if env_root:
            candidates.append(Path(env_root))
        env_opps = os.environ.get("NOVA_OPPORTUNITIES_PATH")
        if env_opps:
            # …/data/history.json → project root two levels up
            candidates.append(Path(env_opps).parent.parent)
        for c in candidates:
            try:
                if c.is_dir() and (c / "main.py").exists():
                    return c
            except OSError:
                continue
        return None

    @property
    def connected(self) -> bool:
        return self.root is not None

    # ---- STATUS (read-only) ----------------------------------------------

    def status(self) -> dict:
        """Hunter health: connected?, last run time, items found, top sources.

        Everything is derived from the Hunter's own output files — no Hunter code runs.
        """
        if not self.connected:
            return {
                "connected": False,
                "detail": "Opportunity Hunter not found on this machine "
                          "(set NOVA_HUNTER_ROOT or NOVA_OPPORTUNITIES_PATH).",
            }
        history = self.root / "data" / "history.json"
        out: dict = {"connected": True, "root": str(self.root)}
        try:
            data = json.loads(history.read_text(encoding="utf-8"))
            runs = data.get("runs", []) if isinstance(data, dict) else []
            out["total_runs"] = len(runs)
            if runs:
                last = runs[-1]
                out["last_run"] = last.get("timestamp") or last.get("date")
                items = last.get("items", []) or []
                out["last_run_items"] = len(items)
                scored = [i for i in items if isinstance(i, dict)
                          and int(i.get("ai_score") or i.get("score") or 0) >= 7]
                out["last_run_high_priority"] = len(scored)
                sources: dict[str, int] = {}
                for i in items:
                    if isinstance(i, dict):
                        s = i.get("source") or "?"
                        sources[s] = sources.get(s, 0) + 1
                out["last_run_sources"] = sources
        except FileNotFoundError:
            out["total_runs"] = 0
            out["detail"] = "No hunts recorded yet — run one to populate the Scout feed."
        except Exception as e:
            out["detail"] = f"History unreadable: {e}"
        return out

    # ---- CONTROL (launch, detached) ----------------------------------------

    def start_hunt(self, test: bool = False, sources: Optional[str] = None) -> dict:
        """Launch a hunt as a detached subprocess. Returns immediately.

        test=True → the Hunter's dry-run mode (no task dumps, no phone push) — safe for demos.
        sources   → comma-separated source names to restrict the run (e.g. "arxiv,github").
        """
        if not self.connected:
            return {"started": False,
                    "detail": "Opportunity Hunter not found — cannot start a hunt."}
        cmd = _hunter_python() + ["main.py", "--now"]
        if test:
            cmd.append("--test")
        if sources:
            cmd += ["--sources", sources]
        try:
            flags = 0
            if sys.platform == "win32":
                # Detach fully so the hunt survives Nova's process and never blocks it.
                flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0)
            subprocess.Popen(
                cmd,
                cwd=str(self.root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=flags,
            )
            return {
                "started": True,
                "mode": "test (dry run)" if test else "live",
                "detail": "Hunt launched in the background — scraping + scoring takes a few "
                          "minutes. Fresh finds will appear in the Scout feed; check "
                          "get_hunter_status for the new run.",
                "launched_at": datetime.now().isoformat(),
            }
        except (OSError, subprocess.SubprocessError) as e:
            return {"started": False, "detail": f"Could not launch the hunt: {e}"}
