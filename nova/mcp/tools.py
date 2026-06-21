"""NovaTools — the capability surface.

These are plain Python methods that return typed Pydantic models. ``server.py`` wraps them as
MCP tools; the agents can also call them in-process. Keeping the *logic* here (and the
*transport* in server.py) means there's one tested implementation, callable either way — and
it's where validation, auditing, and the behavioral derivations live.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional

from ..models import (
    BehavioralStats,
    EditEvent,
    NovaTask,
    PostponePattern,
    TodayContext,
)
from ..memory.store import MemoryStore
from ..security import input_validator as iv
from ..security.audit import AuditLog
from .taskflow_reader import TaskFlowReader
from .taskflow_writer import TaskFlowWriter


class NovaTools:
    def __init__(self, data_dir: Optional[str] = None) -> None:
        self.reader = TaskFlowReader(data_dir)
        self.writer = TaskFlowWriter(data_dir)
        self.audit = AuditLog(self.reader.data_dir / "nova_audit.log")
        # Memory is gated by the SAME consent toggle as the rest of the behavioral data.
        self.memory = MemoryStore(self.reader.data_dir, enabled=self.reader.nova_data_enabled())

    # ---- READ -------------------------------------------------------------
    def get_tasks(self, status: str = "active", priority: Optional[str] = None,
                  tag: Optional[str] = None) -> list[NovaTask]:
        tasks = self.reader.load_tasks()
        status = (status or "active").lower()
        if status == "active":
            tasks = [t for t in tasks if t.is_active]
        elif status == "completed":
            tasks = [t for t in tasks if t.completed]
        elif status == "overdue":
            tasks = [t for t in tasks if t.is_overdue]
        # "all" → no status filter
        if priority:
            want = iv.validate_priority(priority).lower()
            tasks = [t for t in tasks if (t.priority or "").lower() == want]
        if tag:
            tg = tag.strip().lstrip("#").lower()
            tasks = [t for t in tasks if tg in [x.lower() for x in t.tags]]
        return tasks

    def get_today_context(self) -> TodayContext:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        tasks = self.reader.load_tasks()
        active = [t for t in tasks if t.is_active]
        overdue = [t for t in active if t.is_overdue]

        def _overdue_key(t: NovaTask):
            tier = {"high": 0, "medium": 1}.get(t.priority_tier, 2)
            has_dur = 0 if t.duration else 1
            try:
                recency = -datetime.fromisoformat(t.deadline).timestamp()  # most-recent first
            except (ValueError, TypeError):
                recency = 0.0
            return (tier, has_dur, recency)

        candidates = sorted([t for t in overdue if t.postpone_count < 5], key=_overdue_key)[:5]
        scheduled_today = [
            t for t in active
            if t.scheduled_date == today or (t.deadline and str(t.deadline)[:10] == today)
        ]
        prime_id = self.reader.prime_target_id()
        prime = next((t for t in tasks if t.id == prime_id), None) if prime_id else None
        return TodayContext(
            now=now.isoformat(),
            is_evening=now.hour >= 18,
            prime_target=prime,
            scheduled_today=scheduled_today,
            overdue_total=len(overdue),
            overdue_candidates=candidates,
            active_count=len(active),
            load_minutes=sum(t.duration_minutes for t in scheduled_today),
        )

    def get_behavioral_stats(self) -> BehavioralStats:
        tasks = self.reader.load_tasks()
        total = len(tasks)
        completed = sum(1 for t in tasks if t.completed)
        avg_postpone = (sum(t.postpone_count for t in tasks) / total) if total else 0.0

        by_tag: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # tag -> [sum, count]
        for t in tasks:
            for tag in t.tags:
                bucket = by_tag[tag.lower()]
                bucket[0] += t.postpone_count
                bucket[1] += 1
        patterns = [
            PostponePattern(dimension="tag", key=tag, avg_postpone=round(s / n, 2), sample_size=n)
            for tag, (s, n) in by_tag.items()
            if n >= 2
        ]
        patterns.sort(key=lambda p: -p.avg_postpone)

        deadline_moves = sum(1 for e in self.reader.load_edit_history(days=0) if e.field == "deadline")
        return BehavioralStats(
            total_tasks=total,
            completion_rate=round(completed / total, 3) if total else 0.0,
            avg_postpone_count=round(avg_postpone, 2),
            most_postponed=patterns[:5],
            deadline_moves=deadline_moves,
        )

    def get_edit_history(self, task_id: Optional[int] = None, days: int = 7) -> list[EditEvent]:
        return self.reader.load_edit_history(days=days, task_id=task_id)

    # ---- WRITE (validated + audited) -------------------------------------
    def create_task(self, title: str, priority: str = "medium", tags=None,
                    deadline: Optional[str] = None, duration: Optional[str] = None,
                    notes: Optional[str] = None) -> NovaTask:
        clean = dict(
            title=iv.clean_title(title),
            priority=iv.validate_priority(priority),
            tags=iv.clean_tags(tags),
            deadline_iso=iv.validate_deadline(deadline),
            duration=iv.validate_duration(duration),
            notes=iv.clean_notes(notes),
        )
        raw = self.writer.create_task(**clean)
        self.audit.record("create_task", {"id": raw["id"], "title": clean["title"], "priority": clean["priority"]})
        return NovaTask.from_dict(raw)

    def complete_task(self, task_id: int) -> bool:
        ok = self.writer.complete_task(int(task_id))
        self.audit.record("complete_task", {"id": int(task_id), "ok": ok})
        return ok

    def schedule_task(self, task_id: int, date: str) -> Optional[NovaTask]:
        date_iso = iv.validate_date(date)
        raw = self.writer.schedule_task(int(task_id), date_iso)
        self.audit.record("schedule_task", {"id": int(task_id), "date": date_iso, "ok": raw is not None})
        return NovaTask.from_dict(raw) if raw else None

    def set_prime_target(self, task_id: int) -> bool:
        ok = self.writer.set_prime_target(int(task_id))
        self.audit.record("set_prime_target", {"id": int(task_id), "ok": ok})
        return ok

    # ---- MEMORY (consent-gated, local, transparent) ----------------------
    def recall_memory(self, limit: int = 20) -> list[dict]:
        return self.memory.recall(limit)

    def remember(self, note: str, kind: str = "pattern") -> dict:
        entry = self.memory.remember(note, kind)
        if entry:
            self.audit.record("remember", {"kind": entry.get("kind"), "text": entry.get("text", "")[:60]})
        return entry or {}

    def all_memory(self) -> list[dict]:
        return self.memory.all()

    def forget_all(self) -> int:
        n = self.memory.clear()
        self.audit.record("forget_all", {"count": n})
        return n
