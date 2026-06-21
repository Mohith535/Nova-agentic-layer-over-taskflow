"""Quota-frugal path: one model call per turn (no tool round-trips).

The tool-using agents are the default and the showcase — but a single coaching turn can fan out
into several model calls (recall_memory -> stats -> edit_history -> compose -> remember). On a
tight free tier that burns the daily quota fast and adds latency. This path fetches the *same*
real data DETERMINISTICALLY via NovaTools (zero model calls), injects it as context, and makes
exactly ONE generate_content call. Same grounded, emotion-aware answer; ~5x fewer requests.

Used via `nova coach --fast` / `nova brief --fast`, or the "⚡ Fast" toggle in the web console.
Plan and Ask still use the full tool-using agents (they need writes / routing).
"""

from __future__ import annotations

import json
from typing import Optional

from ..config import gemini_model
from ..mcp.tools import NovaTools

COACH_SYS = """\
You are TaskFlow's Coach: an emotionally intelligent behavior-change partner, grounded ONLY in
the user's real data (provided below). Never a motivational app.

First, read the emotional state in the user's message and meet it:
- Shame / self-blame ("I'm the problem", "I keep failing"): normalize and de-shame first. Shame
  triggers a threat response that shuts down planning, so name the mechanism, not the person.
- Overwhelm: shrink the world to ONE 15-minute first step.
- Avoidance ("I keep forgetting / putting it off"): give an implementation intention — a specific
  when + where.

Then deliver three beats: (1) the pattern, with the number; (2) the mechanism it matches
(decision fatigue, the Zeigarnik open loop, the planning fallacy, implementation intentions, the
fresh-start effect — only what the data supports); (3) ONE concrete, small, physical next step.

Rules: ground every claim in the provided data; if it's thin, say so honestly rather than invent.
Be autonomy-supporting, never controlling — offer and invite ("you could…"), don't command
(controlling language backfires). No cheerleading ("you've got this", "don't worry"), no emoji.
If the provided memory holds a relevant prior insight, reference it naturally. Keep it tight."""

BRIEF_SYS = """\
You are TaskFlow's Briefing agent. From the user's real context below, tell them what to focus on
right now — a directive, not a list.

- If it is NOT evening (is_evening false): name the ONE thing to do now (the prime target, else
  the most time-pressured task), its deadline pressure, and the realistic next physical action.
  Then at most 2 supporting tasks. Stop.
- If it IS evening (is_evening true): do not dump a list. Acknowledge the day is winding down and
  help name ONE specific thing to start tomorrow. If there's overdue work, surface 1–2 candidates
  as starting points for tomorrow, never as failures.

Voice: concrete, brief, judgment-free. No cheerleading, no emoji. Use only the provided data —
never invent tasks or deadlines."""


def _gather_coach(t: NovaTools) -> str:
    stats = t.get_behavioral_stats().model_dump()
    hist = [e.model_dump() for e in t.get_edit_history(days=30)][:25]
    mem = t.recall_memory()
    ctx = t.get_today_context().model_dump()
    return json.dumps({
        "behavioral_stats": stats,
        "recent_edit_history": hist,
        "what_nova_remembers": mem,
        "today": {"overdue_total": ctx.get("overdue_total"), "active_count": ctx.get("active_count"),
                  "is_evening": ctx.get("is_evening")},
    }, ensure_ascii=False, indent=2, default=str)


def _gather_brief(t: NovaTools) -> str:
    return json.dumps(t.get_today_context().model_dump(), ensure_ascii=False, indent=2, default=str)


def run_fast(tools: NovaTools, mode: str, message: str = "", model: Optional[str] = None) -> tuple[str, list[str]]:
    """One generate_content call, grounded in deterministically-gathered data.

    Returns (text, tools_used) — tools_used reflects the data we pulled, so the UI can still show
    what Nova looked at even though the gathering wasn't model-driven this time.
    """
    from google import genai
    from google.genai import types

    model = model or gemini_model()
    if mode == "coach":
        sys_inst = COACH_SYS
        data = _gather_coach(tools)
        used = ["get_behavioral_stats", "get_edit_history", "recall_memory"]
        user = message or "What pattern should I fix? Be specific."
    else:  # brief
        sys_inst = BRIEF_SYS
        data = _gather_brief(tools)
        used = ["get_today_context"]
        user = message or "Give me my briefing for right now."

    prompt = (f"USER MESSAGE:\n{user}\n\n"
              f"THE USER'S REAL DATA (ground everything in this; do not invent anything):\n{data}")
    client = genai.Client()  # reads GOOGLE_API_KEY from env
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=sys_inst, temperature=0.6),
    )
    text = (getattr(resp, "text", None) or "").strip()

    # Keep memory alive without a second model call: store the strongest derived pattern.
    if mode == "coach":
        try:
            stats = tools.get_behavioral_stats()
            if stats.most_postponed:
                p = stats.most_postponed[0]
                tools.remember(f"Most-postponed tag is #{p.key} (~{p.avg_postpone}x on average)", "pattern")
        except Exception:
            pass
    return text, used
