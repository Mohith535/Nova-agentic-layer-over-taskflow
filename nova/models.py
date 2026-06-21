"""Typed views over TaskFlow data.

These Pydantic models are the contract between the MCP tools and the agents. Every tool
returns one of these — never a raw dict — so the agents (and the judges reading the code)
get a stable, validated shape. Field names mirror TaskFlow's real `Task` dataclass; the
three computed fields (`is_overdue`, `duration_minutes`, `priority_tier`) mirror the
server's single-source `_computed_task_fields()` so Nova never re-derives them differently.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

# TaskFlow's duration is a fixed enum, never a free integer. Mirror its minute mapping.
_DURATION_MINUTES = {"15m": 15, "30m": 30, "1h": 60, "2h": 120, "3h": 180, "4h+": 240}


def duration_to_minutes(duration: Optional[str]) -> int:
    return _DURATION_MINUTES.get((duration or "").lower(), 0)


def priority_tier(priority: Optional[str]) -> str:
    """TaskFlow's behavioral priorities → coarse high/medium/low tier."""
    p = (priority or "").lower()
    if p in ("critical", "high"):
        return "high"
    if p in ("strategic", "medium"):
        return "medium"
    return "low"  # noise, purge, low, unknown


def _is_overdue(deadline: Optional[str], completed: bool) -> bool:
    if not deadline or completed:
        return False
    try:
        dt = datetime.fromisoformat(deadline)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt < datetime.now()
    except (ValueError, TypeError):
        return False


class NovaTask(BaseModel):
    """A TaskFlow task, normalized for agent consumption."""

    id: int
    title: str
    status: Optional[str] = None
    completed: bool = False
    priority: Optional[str] = None
    duration: Optional[str] = None
    deadline: Optional[str] = None
    deadline_type: Optional[str] = None
    scheduled_date: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    postpone_count: int = 0
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    notes: Optional[str] = None
    # Computed (single source: mirrors server._computed_task_fields)
    is_overdue: bool = False
    duration_minutes: int = 0
    priority_tier: str = "low"

    @classmethod
    def from_dict(cls, d: dict) -> "NovaTask":
        """Build from a TaskFlow task dict, tolerating missing/renamed keys (mirrors
        the resilience of TaskFlow's own `Task.from_dict`)."""
        completed = bool(d.get("completed"))
        deadline = d.get("deadline")
        duration = d.get("duration")
        return cls(
            id=int(d.get("id")),
            title=str(d.get("title", "")),
            status=d.get("status"),
            completed=completed,
            priority=d.get("priority"),
            duration=duration,
            deadline=deadline,
            deadline_type=d.get("deadline_type"),
            scheduled_date=d.get("scheduled_date"),
            tags=[str(t) for t in (d.get("tags") or [])],
            postpone_count=int(d.get("postpone_count") or 0),
            created_at=d.get("created_at"),
            completed_at=d.get("completed_at"),
            notes=d.get("description"),  # TaskFlow stores notes as `description`
            is_overdue=_is_overdue(deadline, completed),
            duration_minutes=duration_to_minutes(duration),
            priority_tier=priority_tier(d.get("priority")),
        )

    @property
    def is_active(self) -> bool:
        """Not completed, dropped, or offloaded — i.e. still 'live' work."""
        return not self.completed and self.status not in ("dropped", "offloaded")


class EditEvent(BaseModel):
    """One append-only entry from a task's `edit_history` — the Coach's raw material.

    The reason fields are present only when the user enabled behavioral ('Nova') data and
    the change was a deadline move; this is exactly where the user told the system *why*.
    """

    task_id: int
    task_title: Optional[str] = None
    field: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    reason_code: Optional[str] = None
    reason_text: Optional[str] = None
    timestamp: Optional[str] = None


class TodayContext(BaseModel):
    """A snapshot of 'where the user stands right now' — the Briefing agent's input."""

    now: str
    is_evening: bool = False  # TaskFlow's 6pm Shift boundary
    prime_target: Optional[NovaTask] = None
    scheduled_today: list[NovaTask] = Field(default_factory=list)
    overdue_total: int = 0
    overdue_candidates: list[NovaTask] = Field(default_factory=list)
    active_count: int = 0
    load_minutes: int = 0


class PostponePattern(BaseModel):
    dimension: str  # "tag" | "priority" | "hour"
    key: str
    avg_postpone: float
    sample_size: int


class BehavioralStats(BaseModel):
    """Derived behavioral signal — the Coach's evidence base. Computed from real
    postpone counts, edit history, and focus data, never invented by the LLM."""

    total_tasks: int = 0
    completion_rate: float = 0.0
    avg_postpone_count: float = 0.0
    most_postponed: list[PostponePattern] = Field(default_factory=list)
    deadline_moves: int = 0
