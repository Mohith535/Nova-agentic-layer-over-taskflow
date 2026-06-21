"""Nova Memory — a local, consent-gated, transparent record of what Nova learns about you.

Design principles (these are the ethical guardrails, not just code):

- **Local only.** Stored as ``nova_memory.json`` inside the TaskFlow data dir. Never networked.
- **Consent-gated.** Reads and writes are no-ops unless TaskFlow's ``nova_data_enabled`` is on.
  The user owns the switch; turning it off blinds Nova's memory.
- **Transparent.** Everything stored is human-readable and surfaced in the UI's
  "What Nova remembers" panel, with a one-click clear. Memory you can see and erase is trust;
  memory you can't is surveillance.
- **Bounded.** Capped to the most recent ~100 short notes — Nova keeps a working memory of you,
  it does not hoard a dossier (responsible-AI: minimize data to purpose).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

KINDS = {"pattern", "emotion", "preference", "fact"}
_MAX = 100
_MAX_LEN = 300


class MemoryStore:
    FILE = "nova_memory.json"

    def __init__(self, data_dir, enabled: bool = True) -> None:
        self.path = Path(data_dir) / self.FILE
        self.enabled = bool(enabled)

    # ---- io ----
    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, mems: list[dict]) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(mems, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    # ---- api ----
    def all(self) -> list[dict]:
        """Everything stored (for the transparency panel). Independent of consent so the user
        can always inspect/clear what's there."""
        return self._load()

    def recall(self, limit: int = 20) -> list[dict]:
        """What the agents see. Empty when consent is off."""
        if not self.enabled:
            return []
        return self._load()[-limit:]

    def remember(self, note: str, kind: str = "pattern") -> dict | None:
        """Store one short, durable insight. No-op when consent is off. Exact duplicates are
        skipped so memory doesn't bloat with repeats."""
        if not self.enabled:
            return None
        note = (note or "").strip()
        if not note:
            return None
        kind = kind if kind in KINDS else "pattern"
        mems = self._load()
        low = note.lower()
        for m in mems:
            if m.get("text", "").lower() == low:
                return m  # already known
        entry = {
            "id": max((m.get("id", 0) for m in mems), default=0) + 1,
            "timestamp": datetime.now().isoformat(),
            "kind": kind,
            "text": note[:_MAX_LEN],
        }
        mems.append(entry)
        self._save(mems[-_MAX:])
        return entry

    def summary(self, limit: int = 12) -> str:
        """A compact text block the Coach can drop into its reasoning context."""
        mems = self.recall(limit)
        if not mems:
            return "(nothing remembered yet)"
        return "\n".join(f"- [{m.get('kind', 'note')}] {m.get('text', '')}" for m in mems)

    def clear(self) -> int:
        """Erase all memory (the user's right). Returns how many entries were removed."""
        n = len(self._load())
        self._save([])
        return n
