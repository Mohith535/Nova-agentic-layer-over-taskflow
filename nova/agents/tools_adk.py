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

    def get_opportunities(min_score: int = 0, limit: int = 10, source: Optional[str] = None) -> list:
        """Real opportunities the Opportunity Hunter agent already found and scored for THIS user —
        hackathons, internships, fellowships, research, coding contests (each with a 1-10 score,
        deadline, and summary). Use when the user asks what's worth their time, mentions applying /
        competing / a deadline, or wants to plan toward an opportunity. Ground answers in these —
        don't invent opportunities. min_score filters (7+ = act this week); source filters by site."""
        return t.get_opportunities(min_score, limit, source)

    def get_user_profile() -> dict:
        """Who this person actually IS — their name, their own words for their 90-day purpose,
        how they work (step-by-step vs big-leaps), what drives them, how they want to be coached,
        and the direction the Opportunity Hunter is chasing on their behalf. This is the DEEPEST
        thing Nova knows about them. Call it FIRST for 'what do you know about me', to greet them
        by name, or any time knowing the person (not just their tasks) makes the answer better."""
        prof = t.read_user_profile()
        basics = prof.get("basics", {})
        nova = prof.get("nova", {})
        # Also surface the *shape* of what the Hunter is chasing — that is knowledge about the
        # person (their ambitions), sourced from a different system than TaskFlow.
        chasing = []
        try:
            for o in t.get_opportunities(min_score=7, limit=4):
                chasing.append({"title": o.get("title"), "score": o.get("score")})
        except Exception:
            pass
        return {
            "name": basics.get("name"),
            "life_context": basics.get("life_context"),
            "peak_hours": basics.get("peak_hours"),
            "purpose_90d": nova.get("purpose_90d"),
            "work_style": nova.get("work_style"),
            "drive_type": nova.get("drive_type"),
            "coaching_style": nova.get("coaching_style"),
            "accountability": nova.get("accountability"),
            "energy_state": nova.get("energy_state"),
            "currently_chasing": chasing,
        }

    return [get_today_context, get_tasks, get_behavioral_stats, get_edit_history,
            recall_memory, get_opportunities, get_user_profile]


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


def operator_tools(t: NovaTools) -> list:
    """The Operator agent's kit: reads to resolve tasks + the full board-management verbs.
    The only agent allowed to complete, postpone, or drop — and drop requires the user's
    explicit confirmation in conversation before the call."""

    def get_today_context() -> dict:
        """The user's situation right now: prime target, tasks scheduled today, overdue count
        and candidates, planned load. Call this to resolve 'today' references."""
        return t.get_today_context().model_dump()

    def get_tasks(status: str = "active", priority: Optional[str] = None,
                  tag: Optional[str] = None) -> list:
        """List tasks to resolve which one the user means. status: active/completed/overdue/all.
        Always resolve the task id BEFORE mutating anything."""
        return [x.model_dump() for x in t.get_tasks(status, priority, tag)]

    def complete_task(task_id: int) -> bool:
        """Mark a task complete."""
        return t.complete_task(task_id)

    def schedule_task(task_id: int, date: str) -> Optional[dict]:
        """Schedule an existing task for a date ('YYYY-MM-DD', 'today', or 'tomorrow')."""
        r = t.schedule_task(task_id, date)
        return r.model_dump() if r else None

    def set_prime_target(task_id: int) -> bool:
        """Set today's single most important task — the Prime Target (one per day)."""
        return t.set_prime_target(task_id)

    def postpone_task(task_id: int, new_deadline: Optional[str] = None) -> Optional[dict]:
        """Postpone a task, optionally to a new deadline (ISO or natural language like
        'Friday 3pm'). Updates the honest postpone record; report the new count neutrally."""
        r = t.postpone_task(task_id, new_deadline)
        return r.model_dump() if r else None

    def drop_task(task_id: int, reason: str = "") -> bool:
        """Soft-drop a task — the record is preserved (dropped_at + reason), never deleted.
        ONLY call after the user has explicitly confirmed the drop in this conversation."""
        return t.drop_task(task_id, reason)

    def get_sync_status() -> dict:
        """TaskFlow's cloud-sync state: enabled?, repo, last push/pull times. Read-only.
        Call this FIRST when the user asks about sync; use sync_taskflow to actually sync."""
        return t.get_sync_status()

    def sync_taskflow(direction: str = "push") -> dict:
        """Actually run TaskFlow's cloud sync. direction: 'push' (board → cloud backup) or
        'pull' (ingest new tasks from the cloud inbox). Takes a few seconds; report the result
        plainly. Use when the user says 'back up my board', 'push to cloud', 'check the inbox'."""
        return t.sync_taskflow(direction)

    return [get_today_context, get_tasks, complete_task, schedule_task, set_prime_target,
            postpone_task, drop_task, get_sync_status, sync_taskflow]


def scout_tools(t: NovaTools) -> list:
    """The Scout agent's kit: the opportunity feed, Hunter health, launching hunts, and the
    single write it needs — turning a chosen opportunity into a TaskFlow task."""

    def get_opportunities(min_score: int = 0, limit: int = 10, source: Optional[str] = None) -> list:
        """Scored opportunities the Hunter already found for THIS user (hackathons, internships,
        fellowships, research, contests; 1-10 score, deadline, summary, url). min_score 7+ =
        act this week. Ground every recommendation in these — never invent one."""
        return t.get_opportunities(min_score, limit, source)

    def get_hunter_status() -> dict:
        """Opportunity Hunter pipeline health: connected?, last run time, items found,
        high-priority count, per-source breakdown. Use for 'is it working / when did it run'."""
        return t.get_hunter_status()

    def run_opportunity_hunt(test: bool = False, sources: Optional[str] = None) -> dict:
        """Launch a fresh hunt in the background (returns immediately; scraping + scoring
        takes minutes). test=True is a dry run (no notifications, no task dumps). sources
        restricts the run, e.g. 'arxiv,github'. Launch only when the user asks for fresh finds."""
        return t.run_opportunity_hunt(test, sources)

    def create_task(title: str, priority: str = "strategic", tags: Optional[list] = None,
                    deadline: Optional[str] = None, duration: Optional[str] = None,
                    notes: Optional[str] = None) -> dict:
        """Turn a chosen opportunity into a TaskFlow task ('Apply: <name>'), carrying its
        deadline and #opportunity tag. priority: critical (score 9-10) / strategic."""
        return t.create_task(title, priority, tags, deadline, duration, notes).model_dump()

    return [get_opportunities, get_hunter_status, run_opportunity_hunt, create_task]
