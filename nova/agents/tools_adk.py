"""Expose NovaTools as ADK function tools.

ADK builds each tool's schema from the function signature + docstring, so these thin wrappers
carry clear docstrings (the model reads them to decide when/how to call). They close over one
shared ``NovaTools`` instance — so the agents call the *exact same* validated, audited
implementation that the MCP server exposes. One implementation, two front doors.

Permission boundaries are enforced here by *which* list each agent receives:
- ``read_tools`` — Briefing and Coach (least privilege; they never mutate data).
- ``write_tools`` — Planning only (the single writer).
"""

from __future__ import annotations

from typing import Optional

from ..mcp.tools import NovaTools


def read_tools(t: NovaTools) -> list:
    def get_today_context() -> dict:
        """The user's situation right now: prime target, tasks scheduled today, overdue count
        and the best candidates to tackle, current planned load in minutes, and whether it is
        past TaskFlow's 6pm wind-down boundary. Call this first for any 'what now / today' ask."""
        return t.get_today_context().model_dump()

    def get_tasks(status: str = "active", priority: Optional[str] = None,
                  tag: Optional[str] = None) -> list:
        """List the user's tasks. status is one of: active, completed, overdue, all.
        Optionally filter by priority (critical/strategic/noise) or by a tag."""
        return [x.model_dump() for x in t.get_tasks(status, priority, tag)]

    def get_behavioral_stats() -> dict:
        """Real behavioral signal computed from the user's own history: completion rate,
        average postpone count, the tags that get postponed the most, and how many deadlines
        have been moved. Use this as evidence — never invent a pattern that isn't here."""
        return t.get_behavioral_stats().model_dump()

    def get_edit_history(task_id: Optional[int] = None, days: int = 14) -> list:
        """The append-only edit history: status changes, postpones, and the *reasons* the user
        gave when moving deadlines (e.g. 'I haven't been able to start it yet'). The richest,
        most honest source of behavioral insight."""
        return [e.model_dump() for e in t.get_edit_history(task_id, days)]

    def recall_memory() -> list:
        """Recall what Nova has learned about THIS user across past sessions — durable patterns,
        emotional signals, and preferences. Call this FIRST so your response is personalized and
        continuous, not generic. Returns [] if the user has memory turned off."""
        return t.recall_memory()

    return [get_today_context, get_tasks, get_behavioral_stats, get_edit_history, recall_memory]


def memory_write_tools(t: NovaTools) -> list:
    def remember(note: str, kind: str = "pattern") -> dict:
        """Store ONE short, specific, durable insight about the user for future sessions.
        kind is one of: pattern | emotion | preference | fact. Examples:
        'Forgets tasks that have no scheduled time' (pattern);
        'Feels overwhelmed by #study tasks late at night' (emotion);
        'Responds well to a 15-minute first step' (preference).
        Only store something genuinely durable and useful — not the day's small talk."""
        return t.remember(note, kind)

    return [remember]


def write_tools(t: NovaTools) -> list:
    def create_task(title: str, priority: str = "strategic", tags: Optional[list] = None,
                    deadline: Optional[str] = None, duration: Optional[str] = None,
                    notes: Optional[str] = None) -> dict:
        """Create a new task in TaskFlow. priority: critical/strategic/noise.
        duration: one of 15m/30m/1h/2h/3h/4h+. deadline: ISO date or natural language like
        'tomorrow 3pm'. Returns the created task with its new id."""
        return t.create_task(title, priority, tags, deadline, duration, notes).model_dump()

    def schedule_task(task_id: int, date: str) -> Optional[dict]:
        """Schedule an existing task for a date ('YYYY-MM-DD', 'today', or 'tomorrow')."""
        r = t.schedule_task(task_id, date)
        return r.model_dump() if r else None

    def set_prime_target(task_id: int) -> bool:
        """Set today's single most important task — the Prime Target (one per day)."""
        return t.set_prime_target(task_id)

    return [create_task, schedule_task, set_prime_target]
