"""Input validation for every value that crosses into a write.

The threat model is a Concierge agent acting on natural-language input: an LLM (or a
malicious prompt) could try to push oversized payloads, control characters, or values that
don't belong in TaskFlow's enums. Everything here is **fail-closed** — invalid input raises
rather than silently writing junk into the user's behavioral dataset.

Where TaskFlow's own normalizers exist (`normalize_priority`, `normalize_duration`,
`parse_deadline`), we reuse them so Nova and TaskFlow agree on what a valid value is. When
TaskFlow isn't importable (CI), we fall back to local equivalents.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TAG_OK = re.compile(r"^[A-Za-z0-9 _\-]+$")

MAX_TITLE = 500
MAX_NOTES = 5000
MAX_TAGS = 20
MAX_TAG_LEN = 40


class ValidationError(ValueError):
    """Raised when an input fails validation. Message is safe to surface to the user."""


def _strip(s: str) -> str:
    return _CONTROL.sub("", s).strip()


def clean_title(title: str) -> str:
    if not isinstance(title, str):
        raise ValidationError("Title must be text.")
    t = _strip(title)
    if not t:
        raise ValidationError("Title cannot be empty.")
    if len(t) > MAX_TITLE:
        raise ValidationError(f"Title too long (max {MAX_TITLE} characters).")
    return t


def clean_notes(notes: Optional[str]) -> Optional[str]:
    if notes is None:
        return None
    if not isinstance(notes, str):
        raise ValidationError("Notes must be text.")
    n = _strip(notes)
    if len(n) > MAX_NOTES:
        raise ValidationError(f"Notes too long (max {MAX_NOTES} characters).")
    return n or None


def clean_tags(tags) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, str):
        tags = [p for p in re.split(r"[,\s]+", tags) if p]
    if not isinstance(tags, (list, tuple)):
        raise ValidationError("Tags must be a list.")
    out: list[str] = []
    for raw in tags:
        t = _strip(str(raw)).lstrip("#")
        if not t:
            continue
        if len(t) > MAX_TAG_LEN or not _TAG_OK.match(t):
            raise ValidationError(f"Invalid tag: {raw!r} (letters, numbers, space, _ or - only).")
        out.append(t)
        if len(out) >= MAX_TAGS:
            break
    return out


def validate_priority(priority: Optional[str]) -> str:
    """→ Critical / Strategic / Noise / Purge (TaskFlow's behavioral taxonomy)."""
    try:
        from task_manager.commands import normalize_priority  # type: ignore[import-not-found]

        return normalize_priority(priority or "medium")
    except Exception:
        m = {
            "critical": "Critical", "high": "Critical", "c": "Critical", "h": "Critical",
            "strategic": "Strategic", "medium": "Strategic", "s": "Strategic", "m": "Strategic",
            "noise": "Noise", "low": "Noise", "n": "Noise", "l": "Noise",
            "purge": "Purge", "p": "Purge",
        }
        return m.get((priority or "medium").strip().lower(), "Strategic")


def validate_duration(duration: Optional[str]) -> Optional[str]:
    """→ TaskFlow's fixed enum (15m/30m/1h/2h/3h/4h+) or None."""
    if duration is None:
        return None
    try:
        from task_manager.commands import normalize_duration  # type: ignore[import-not-found]

        return normalize_duration(duration)
    except Exception:
        d = str(duration).strip().lower()
        return d if d in {"15m", "30m", "1h", "2h", "3h", "4h+"} else None


def validate_deadline(deadline: Optional[str]) -> Optional[str]:
    """Accept an ISO datetime or natural language ('tomorrow 3pm'); return ISO or None."""
    if not deadline:
        return None
    s = str(deadline).strip()
    low = s.lower()
    if low in ("tomorrow", "tmrw"):
        return (datetime.now() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
    try:
        return datetime.fromisoformat(s).isoformat()
    except ValueError:
        pass
    try:
        from task_manager.commands import parse_deadline  # type: ignore[import-not-found]

        parsed = parse_deadline(s)
        return parsed.isoformat() if parsed else None
    except Exception:
        raise ValidationError(f"Could not understand the deadline: {deadline!r}.")


def validate_date(date: str) -> str:
    """A scheduling date → 'YYYY-MM-DD'. Accepts 'today'/'tomorrow' and natural language."""
    s = str(date).strip().lower()
    if s in ("today", ""):
        return datetime.now().strftime("%Y-%m-%d")
    if s in ("tomorrow", "tmrw"):
        return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        iso = validate_deadline(date)
        if iso:
            return iso[:10]
        raise ValidationError(f"Could not understand the date: {date!r}.")
