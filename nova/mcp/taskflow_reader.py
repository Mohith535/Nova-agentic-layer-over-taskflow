"""Safe, read-only access to a TaskFlow data directory (``~/.taskflow/``).

Two sourcing strategies, in order of preference:

1. **Reuse the installed ``task_manager`` package** (true single source of truth) when the
   reader is pointed at the real home directory. This gives Nova TaskFlow's own
   corrupt-recovery, schema handling, and computed fields for free.
2. **Self-contained, schema-tolerant JSON parse** as a fallback — so Nova also runs on a CI
   runner that only has the synced JSON files and no TaskFlow install.

Security posture (this is a Concierge / security-judged track — it is documented because it
is enforced):

- **Containment.** Every file read is resolved and verified to live *inside* the data dir
  (``realpath`` + ``commonpath``), so a tampered config or a crafted name cannot traverse out.
- **Read-only.** This module never writes and never opens a network socket.
- **No path leakage in the happy path.** Errors are typed; callers decide what to surface.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ..models import EditEvent, NovaTask


class TaskFlowReaderError(RuntimeError):
    """Raised when the data directory is missing/invalid or a read is refused."""


def resolve_data_dir(explicit: Optional[str] = None) -> Path:
    """Resolve the TaskFlow data directory.

    Precedence: explicit arg → ``TASKFLOW_DATA_PATH`` env → ``~/.taskflow``.
    Must exist and be a directory, or a clear error is raised.
    """
    raw = explicit or os.environ.get("TASKFLOW_DATA_PATH") or str(Path.home() / ".taskflow")
    p = Path(raw).expanduser()
    try:
        p = p.resolve(strict=True)
    except FileNotFoundError as e:
        raise TaskFlowReaderError(f"TaskFlow data directory not found: {raw}") from e
    if not p.is_dir():
        raise TaskFlowReaderError(f"TaskFlow data path is not a directory: {raw}")
    return p


class TaskFlowReader:
    """Read-only window onto one TaskFlow data directory."""

    def __init__(self, data_dir: Optional[str] = None) -> None:
        self.data_dir = resolve_data_dir(data_dir)

    # ---- safe file access -------------------------------------------------
    def _safe_path(self, name: str) -> Path:
        """Resolve ``name`` inside the data dir, refusing anything that escapes it."""
        candidate = (self.data_dir / name).resolve()
        try:
            common = os.path.commonpath([str(self.data_dir), str(candidate)])
        except ValueError as e:  # different drives on Windows, etc.
            raise TaskFlowReaderError("Refusing to read outside the data directory") from e
        if common != str(self.data_dir):
            raise TaskFlowReaderError(f"Path traversal blocked for: {name!r}")
        return candidate

    def _read_json(self, name: str, default):
        path = self._safe_path(name)
        if not path.is_file():
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return default

    # ---- raw tasks (with optional single-source reuse) --------------------
    def _raw_tasks(self) -> list[dict]:
        viamgr = self._raw_tasks_via_taskmanager()
        if viamgr is not None:
            return viamgr
        data = self._read_json("tasks.json", [])
        return data if isinstance(data, list) else []

    def _raw_tasks_via_taskmanager(self) -> Optional[list[dict]]:
        """Use TaskFlow's own loader when we're pointed at the real home directory.

        ``task_manager.storage`` hard-codes ``~/.taskflow``, so this is only valid (and only
        the single source of truth) when our data dir *is* that directory. Otherwise we fall
        back to the portable JSON path, which is what the CI runner uses.
        """
        try:
            if self.data_dir != (Path.home() / ".taskflow").resolve():
                return None
            from task_manager import storage  # type: ignore[import-not-found]

            return [t.to_dict() for t in storage.load_tasks()]
        except Exception:
            return None

    # ---- typed reads ------------------------------------------------------
    def load_tasks(self) -> list[NovaTask]:
        out: list[NovaTask] = []
        for item in self._raw_tasks():
            try:
                out.append(NovaTask.from_dict(item))
            except Exception:
                continue  # one malformed task never sinks the whole read
        return out

    def active_tasks(self) -> list[NovaTask]:
        return [t for t in self.load_tasks() if t.is_active]

    def load_edit_history(self, days: int = 7, task_id: Optional[int] = None) -> list[EditEvent]:
        """Flatten every task's append-only ``edit_history`` into typed events.

        Filtered to the last ``days`` (0 = no limit) and optionally one task. This is the
        behavioral substrate the Coach agent reasons over.
        """
        cutoff = None if not days else datetime.now() - timedelta(days=days)
        events: list[EditEvent] = []
        for raw in self._raw_tasks():
            tid = raw.get("id")
            if task_id is not None and tid != task_id:
                continue
            for entry in (raw.get("edit_history") or []):
                ts = entry.get("timestamp")
                if cutoff is not None and ts:
                    try:
                        if datetime.fromisoformat(ts) < cutoff:
                            continue
                    except (ValueError, TypeError):
                        pass
                events.append(
                    EditEvent(
                        task_id=int(tid) if tid is not None else -1,
                        task_title=raw.get("title"),
                        field=str(entry.get("field", "")),
                        old_value=_as_str(entry.get("old_value")),
                        new_value=_as_str(entry.get("new_value")),
                        reason_code=entry.get("reason_code"),
                        reason_text=entry.get("reason_text"),
                        timestamp=ts,
                    )
                )
        events.sort(key=lambda e: e.timestamp or "", reverse=True)
        return events

    def load_config(self) -> dict:
        cfg = self._read_json("config.json", {})
        return cfg if isinstance(cfg, dict) else {}

    def load_timeline(self) -> dict:
        tl = self._read_json("timeline.json", {})
        return tl if isinstance(tl, dict) else {}

    def prime_target_id(self) -> Optional[int]:
        """Today's single Prime Target, read from TaskFlow's timeline mapping
        (``{task_id: "YYYY-MM-DD_prime"}``)."""
        today = datetime.now().strftime("%Y-%m-%d")
        for tid, val in self.load_timeline().items():
            if isinstance(val, str) and val == f"{today}_prime":
                try:
                    return int(tid)
                except (ValueError, TypeError):
                    return None
        return None

    def nova_data_enabled(self) -> bool:
        """The global behavioral-data consent gate. Default ON, matching TaskFlow."""
        return self.load_config().get("nova_data_enabled", True) is not False


def _as_str(v) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v)
    return str(v)
