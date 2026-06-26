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

    def get_opportunities(self, min_score: int = 0, limit: int = 10,
                          source: Optional[str] = None) -> list[dict]:
        """Opportunities surfaced by the Opportunity Hunter agent (hackathons, internships,
        fellowships, research, contests) — already filtered to the user's profile and scored 1–10.

        Read-only bridge: Nova never runs the hunt, it reads what the hunter already found and
        deduped, so it can discuss real opportunities and (on the user's say-so) turn them into
        tasks. Resolves the findings file from NOVA_OPPORTUNITIES_PATH, then known locations.
        """
        import json
        import os
        from pathlib import Path

        candidates = []
        env = os.environ.get("NOVA_OPPORTUNITIES_PATH")
        if env:
            candidates.append(Path(env))
        candidates += [
            Path(self.reader.data_dir) / "opportunities.json",
            Path.home() / ".taskflow" / "opportunities.json",
            Path("E:/agent for my self/data/history.json"),
        ]
        path = next((p for p in candidates if p.exists()), None)
        if not path:
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

        items: list[dict] = []
        if isinstance(data, dict) and "runs" in data:
            for run in data.get("runs", []):
                items.extend(run.get("items", []) or [])
        elif isinstance(data, list):
            items = data

        # Dedup by native id / url / title — latest run wins.
        seen: dict[str, dict] = {}
        for it in items:
            if not isinstance(it, dict):
                continue
            key = it.get("native_id") or it.get("url") or it.get("title")
            if key:
                seen[key] = it

        def _score(o: dict) -> int:
            # ai_score is -1 until Opportunity Hunter's Phase-2 LLM scorer runs, so only trust it
            # when positive; otherwise fall back to the rule-based score.
            for k in ("ai_score", "score"):
                try:
                    v = int(o.get(k) or 0)
                except (TypeError, ValueError):
                    v = 0
                if v > 0:
                    return v
            return 0

        opps = list(seen.values())
        if source:
            opps = [o for o in opps if (o.get("source") or "").lower() == source.lower()]
        opps = [o for o in opps if _score(o) >= int(min_score or 0)]
        opps.sort(key=lambda o: (_score(o), o.get("deadline") or ""), reverse=True)

        out = []
        for o in opps[: max(1, min(int(limit or 10), 25))]:
            out.append({
                "title": o.get("title", ""),
                "source": o.get("source", ""),
                "url": o.get("url", ""),
                "score": _score(o),
                "deadline": o.get("deadline"),
                "summary": (o.get("ai_summary") or o.get("description") or "")[:240],
                "tags": o.get("tags", []) or [],
            })
        return out

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

    def forget_one(self, entry_id: int) -> bool:
        ok = self.memory.delete_one(int(entry_id))
        if ok:
            self.audit.record("forget_one", {"id": int(entry_id)})
        return ok

    def update_memory(self, entry_id: int, text: str) -> dict:
        entry = self.memory.update_one(int(entry_id), text)
        if entry:
            self.audit.record("update_memory", {"id": int(entry_id), "text": (text or "")[:60]})
        return entry or {}

    def forget_all(self) -> int:
        n = self.memory.clear()
        self.audit.record("forget_all", {"count": n})
        return n

    # ---- USER PROFILE (shared by Nova + TaskFlow) -----------------------
    def read_user_profile(self) -> dict:
        """Read user_profile.json — the psychological profile shared by all agents."""
        path = self.reader.data_dir / "user_profile.json"
        if not path.exists():
            return {}
        try:
            import json as _json
            data = _json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def write_user_profile(self, updates: dict) -> dict:
        """Atomically deep-merge updates into user_profile.json."""
        import json as _json
        path = self.reader.data_dir / "user_profile.json"
        try:
            current = _json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            if not isinstance(current, dict):
                current = {}
        except Exception:
            current = {}
        for k, v in updates.items():
            if isinstance(v, dict) and isinstance(current.get(k), dict):
                current[k] = {**current[k], **v}
            else:
                current[k] = v
        current.setdefault("version", 1)
        current["updated_at"] = datetime.now().isoformat()
        current.setdefault("created_at", current["updated_at"])
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(_json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        self.audit.record("write_user_profile", {"fields": list(updates.keys())})
        return current

    def reset_profile(self) -> bool:
        """Delete user_profile.json entirely — used by the full 'start over' reset.
        Returns True if a profile file existed and was removed."""
        path = self.reader.data_dir / "user_profile.json"
        existed = path.exists()
        try:
            if existed:
                path.unlink()
            # also clear any leftover temp
            tmp = path.with_suffix(".json.tmp")
            if tmp.exists():
                tmp.unlink()
        except OSError:
            return False
        self.audit.record("reset_profile", {"existed": existed})
        return existed

    # ---- SESSION ACTIVITY (Reflection Agent) ----------------------------
    def get_session_activity(self, hours: int = 24) -> dict:
        """Last N hours of activity — completed, postponed, edits, focus state."""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(hours=max(1, min(int(hours), 168)))
        tasks = self.reader.load_tasks()

        completed = []
        for t in tasks:
            if t.completed and t.completed_at:
                try:
                    if datetime.fromisoformat(t.completed_at[:19]) >= cutoff:
                        completed.append({"id": t.id, "title": t.title, "priority": t.priority})
                except Exception:
                    pass

        postponed = []
        for t in tasks:
            for p in reversed((t.postpone_history or [])[-3:]):
                if not p:
                    continue
                try:
                    if datetime.fromisoformat(str(p)[:19]) >= cutoff:
                        postponed.append({"id": t.id, "title": t.title,
                                          "postpone_count": t.postpone_count, "tags": t.tags})
                        break
                except Exception:
                    pass

        edits = [e.model_dump() for e in self.reader.load_edit_history(days=1)][:15]
        focus_state = self.reader._read_json("focus_state.json", {})
        return {
            "period_hours": int(hours),
            "completed_count": len(completed),
            "completed": completed[:10],
            "postponed_count": len(postponed),
            "postponed": postponed[:10],
            "edit_count": len(edits),
            "recent_edits": edits,
            "focus_state": focus_state,
        }

    # ---- BEHAVIORAL PATTERNS (Pattern Intelligence Agent) ---------------
    def get_behavioral_patterns(self, weeks: int = 4) -> dict:
        """Multi-week aggregate patterns — completion by day-of-week, chronic postponers, etc."""
        from collections import defaultdict as _dd
        tasks = self.reader.load_tasks()
        stats = self.get_behavioral_stats()

        by_dow: dict[str, dict] = _dd(lambda: {"completed": 0, "created": 0})
        for t in tasks:
            if t.created_at:
                try:
                    dow = datetime.fromisoformat(t.created_at[:19]).strftime("%A")
                    by_dow[dow]["created"] += 1
                except Exception:
                    pass
            if t.completed and t.completed_at:
                try:
                    dow = datetime.fromisoformat(t.completed_at[:19]).strftime("%A")
                    by_dow[dow]["completed"] += 1
                except Exception:
                    pass

        chronic = [
            {"id": t.id, "title": t.title, "postpone_count": t.postpone_count,
             "priority": t.priority, "tags": t.tags}
            for t in sorted(tasks, key=lambda x: x.postpone_count, reverse=True)
            if t.postpone_count >= 3 and t.is_active
        ][:8]

        edits = self.reader.load_edit_history(days=weeks * 7)
        deadline_moves = [e.model_dump() for e in edits if e.field == "deadline"][:15]

        return {
            "weeks_analyzed": int(weeks),
            "stats": stats.model_dump(),
            "completion_by_day_of_week": dict(by_dow),
            "chronically_postponed": chronic,
            "recent_deadline_moves": deadline_moves,
            "total_edit_events": len(edits),
        }
