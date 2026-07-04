"""Quota-frugal path: one model call per turn (no tool round-trips).

The tool-using agents are the default and the showcase — but a single coaching turn can fan out
into several model calls (recall_memory -> stats -> edit_history -> compose -> remember). On a
tight free tier that burns the daily quota fast and adds latency. This path fetches the *same*
real data DETERMINISTICALLY via NovaTools (zero model calls), injects it as context, and makes
exactly ONE generate_content call. Same grounded, emotion-aware answer; ~5x fewer requests.

Used via `nova coach --fast` / `nova brief --fast`, or the "⚡ Fast" toggle in the web console.
Ask also has a fast path (conversational with full context injected). Plan still requires the
full agent (it needs task write access and step-by-step approval).
"""

from __future__ import annotations

import json
from typing import Optional

from ..config import fast_gemini_model
from ..mcp.tools import NovaTools

# The single most important thing about Nova's voice, shared by every user-facing prompt.
# The old prompts over-corrected "no cheerleading" into "no warmth" — the result read like a
# clipboard. Warmth and cheerleading are NOT the same thing, and this block draws that line.
_VOICE = """\
VOICE — this is what separates Nova from a generic assistant, so get it right:
- Talk like a real person who actually knows them. Use their NAME when you have it. When it fits,
  connect what you're saying to their own 90-day purpose (in their words) or how they work — that
  is the proof you know THEM, not a generic user.
- Warmth is REQUIRED, and warmth is NOT cheerleading. Sound human: a little texture, a real
  reaction, plain feeling. "That #study tag has been sitting heavy, hasn't it?" is warm.
  "You've got this!" is hollow — that's the banned kind.
- BANNED: empty hype ("you've got this", "you're crushing it", "stay positive", "don't worry"),
  therapy clichés, and emoji. Meet a hard feeling honestly instead of papering over it.
- Grounded always: every claim traces to the data provided; if it's thin, say so like a person
  would ("honestly, I don't have much on you yet"), never invent a number or a pattern.
- Autonomy-supporting: offer and invite ("you could…", "one way…"), don't command. Speak in
  short, real sentences — warm does not mean long."""


COACH_SYS = """\
You are Nova's Coach: an emotionally intelligent partner who has read the research AND actually
knows this person, grounded ONLY in their real data (provided below). Never a motivational app —
but never a cold one either.

First, read the emotional state in the user's message and meet it, as a person would:
- Shame / self-blame ("I'm the problem", "I keep failing"): meet it warmly and de-shame first.
  Shame triggers a threat response that shuts down planning, so name the mechanism, not the person
  ("this is avoidance, not a character flaw").
- Overwhelm: shrink the world to ONE 15-minute first step.
- Avoidance ("I keep forgetting / putting it off"): give an implementation intention — a specific
  when + where.

Then deliver three beats: (1) the pattern, with the number; (2) the mechanism it matches
(decision fatigue, the Zeigarnik open loop, the planning fallacy, implementation intentions, the
fresh-start effect — only what the data supports); (3) ONE concrete, small, physical next step.

""" + _VOICE + """
If the provided memory or profile holds something relevant, reference it naturally — that
continuity is the whole point. Keep it tight."""

BRIEF_SYS = """\
You are TaskFlow's Briefing agent. From the user's real context below, tell them what to focus on
right now — a directive, not a list.

- If it is NOT evening (is_evening false): name the ONE thing to do now (the prime target, else
  the most time-pressured task), its deadline pressure, and the realistic next physical action.
  Then at most 2 supporting tasks. Stop.
- If it IS evening (is_evening true): do not dump a list. Acknowledge the day is winding down and
  help name ONE specific thing to start tomorrow. If there's overdue work, surface 1–2 candidates
  as starting points for tomorrow, never as failures.
- If opportunity_pipeline shows the last hunt is more than 3 days old, you may add ONE final
  line offering a fresh hunt ("Scout's feed is N days old — say 'run a hunt' for fresh finds.").
  Never more than one line, and only when the data shows it.

""" + _VOICE + """
Use only the provided data — never invent tasks or deadlines."""


def _profile_block(t: NovaTools) -> dict:
    """Who the person IS — name, purpose, work style, and what the Hunter is chasing for them.
    A local read, zero quota. This is what makes the answer about a PERSON, not a task list."""
    try:
        prof = t.read_user_profile()
    except Exception:
        prof = {}
    basics = prof.get("basics", {}) if isinstance(prof, dict) else {}
    nova = prof.get("nova", {}) if isinstance(prof, dict) else {}
    chasing = []
    try:
        chasing = [{"title": o.get("title"), "score": o.get("score")}
                   for o in t.get_opportunities(min_score=7, limit=4)]
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
        "energy_state": nova.get("energy_state"),
        "currently_chasing": chasing,
    }


def _gather_coach(t: NovaTools) -> str:
    stats = t.get_behavioral_stats().model_dump()
    hist = [e.model_dump() for e in t.get_edit_history(days=30)][:25]
    mem = t.recall_memory()
    ctx = t.get_today_context().model_dump()
    return json.dumps({
        "who_they_are": _profile_block(t),
        "behavioral_stats": stats,
        "recent_edit_history": hist,
        "what_nova_remembers": mem,
        "today": {"overdue_total": ctx.get("overdue_total"), "active_count": ctx.get("active_count"),
                  "is_evening": ctx.get("is_evening")},
    }, ensure_ascii=False, indent=2, default=str)


def _gather_brief(t: NovaTools) -> str:
    data = {"today": t.get_today_context().model_dump()}
    # Staleness nudge material — a local file read, zero model cost. If the opportunity feed
    # is old, the brief may offer a fresh hunt (prompting at the decision point).
    try:
        hs = t.get_hunter_status()
        data["opportunity_pipeline"] = {"connected": hs.get("connected"),
                                        "last_run": hs.get("last_run")}
    except Exception:
        pass
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _gather_ask(t: NovaTools) -> str:
    """Everything Nova can see, gathered deterministically — all LOCAL reads, zero quota cost.
    Fast-ask must never claim ignorance of a thing the full agents know about."""
    ctx = t.get_today_context().model_dump()
    mem = t.recall_memory()
    tasks = t.get_tasks()[:15]  # top 15 tasks for context
    data = {
        "who_they_are": _profile_block(t),
        "today": ctx,
        "tasks": tasks,
        "what_nova_remembers": mem,
    }
    try:
        data["cloud_sync"] = t.get_sync_status()
    except Exception:
        pass
    try:
        data["opportunity_pipeline"] = t.get_hunter_status()
    except Exception:
        pass
    try:
        data["top_opportunities"] = t.get_opportunities(min_score=7, limit=5)
    except Exception:
        pass
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


ASK_SYS = """\
You are Nova — an honest, grounded partner who genuinely knows this person. You have their
profile (who_they_are: name, their own 90-day purpose, work style, what the Opportunity Hunter
is chasing for them), their current tasks, behavioral context, what you remember about them,
their cloud-sync state, the Hunter pipeline's health, and the top scored opportunities. Answer
questions about ANY of these from the provided data.

When they ask "what do you know about me?" — answer generously and warmly, like a friend who's
been paying attention: their name and what they're working toward (quote their purpose), how
they tend to work, what they're chasing right now (the opportunities), plus 2-3 real numbers
from their behavior. Weave it together as knowing a PERSON, not a database dump. Never pivot to
how they can erase your memory — they asked what you know, not how to delete it.

On this path you can SEE everything but cannot ACT (no completing, postponing, dropping,
launching hunts, or syncing from here).

""" + _VOICE + """
Meet the user's emotional tone first, then be useful."""

# How to respond when the user asked for an ACTION — depends on WHY we're on this path.
# Never tell a user to "turn off Fast" when they never turned it on (the fallback case).
_ASK_ADVICE_CHOSEN = """\
The user chose Fast (⚡) mode. If they ask for an action, answer what you can from the data,
then tell them to switch ⚡ off so the Operator or Scout agent can carry it out."""

_ASK_ADVICE_FALLBACK = """\
You are answering because the full agent crew was unavailable this turn (rate limit or model
quota — nothing the user did; do NOT mention any Fast toggle or ask them to change settings).
If they asked for an action, say plainly you couldn't reach the acting agents right now and
to try the same request again in a minute — or do it directly in TaskFlow (dashboard or CLI)."""


def run_fast(tools: NovaTools, mode: str, message: str = "", model: Optional[str] = None,
             fallback: bool = False) -> tuple[str, list[str]]:
    """One generate_content call, grounded in deterministically-gathered data.

    Returns (text, tools_used) — tools_used reflects the data we pulled, so the UI can still show
    what Nova looked at even though the gathering wasn't model-driven this time.

    fallback=True means the FULL agent path failed and we're covering for it — the action
    advice changes so we never blame a ⚡ toggle the user didn't touch.
    """
    from google import genai
    from google.genai import types

    model = model or fast_gemini_model()
    if mode == "coach":
        sys_inst = COACH_SYS
        data = _gather_coach(tools)
        used = ["get_behavioral_stats", "get_edit_history", "recall_memory"]
        user = message or "What pattern should I fix? Be specific."
    elif mode == "ask":
        sys_inst = ASK_SYS + "\n\n" + (_ASK_ADVICE_FALLBACK if fallback else _ASK_ADVICE_CHOSEN)
        data = _gather_ask(tools)
        used = ["get_today_context", "get_tasks", "recall_memory",
                "get_sync_status", "get_hunter_status", "get_opportunities"]
        user = message or "What should I focus on right now?"
    else:  # brief
        sys_inst = BRIEF_SYS
        data = _gather_brief(tools)
        used = ["get_today_context", "get_hunter_status"]
        user = message or "Give me my briefing for right now."

    prompt = (f"USER MESSAGE:\n{user}\n\n"
              f"THE USER'S REAL DATA (ground everything in this; do not invent anything):\n{data}")
    # Warmth lives partly in sampling: coach/ask get room to sound human (0.85); brief stays
    # tight and factual (0.55) because a directive shouldn't wander.
    temp = 0.55 if mode == "brief" else 0.85
    client = genai.Client()  # reads GOOGLE_API_KEY from env
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=sys_inst, temperature=temp),
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
