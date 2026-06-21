"""Append-only audit trail for every write Nova performs.

A Concierge agent that can mutate the user's data must be accountable for it. Every write
tool records a line here *before* the user trusts the result — what changed, when, by which
tool. Append-only JSONL, local file, never networked. This mirrors TaskFlow's own
append-only `edit_history` philosophy: the record of what the system did must be tamper-
evident to be trustworthy.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()


class AuditLog:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def record(self, action: str, details: dict[str, Any] | None = None) -> None:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details or {},
        }
        line = json.dumps(entry, ensure_ascii=False)
        with _LOCK:
            try:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                # Auditing must never crash the operation it audits; failure is swallowed
                # (the operation itself still went through TaskFlow's atomic write).
                pass
