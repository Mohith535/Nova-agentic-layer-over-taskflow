"""Propose a task breakdown for a goal — WITHOUT creating anything.

This is the heart of the human-in-the-loop gate: Nova plans *with* the user (proposes a sequenced
breakdown), the user reviews/edits, and only a separate commit step writes the tasks. One model
call, strict JSON out — quota-frugal and easy to render as editable cards.

Grounded in the user's real context (and, when the goal is opportunity-shaped, the Scout feed), so
the plan respects their actual load and never invents a deadline.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from ..config import gemini_model
from ..mcp.tools import NovaTools

PROPOSE_SYS = """You are TaskFlow's planning agent. Break the user's goal into a SHORT, sequenced
set of concrete tasks they can actually execute. Output ONLY a JSON array — no prose, no markdown
fences.

Each task object has exactly:
{"title": "action-first, <=80 chars (\\"Draft...\\", \\"Email...\\", \\"Build...\\")",
 "priority": "critical" | "strategic" | "noise",
 "duration": "15m" | "30m" | "1h" | "2h" | "3h" | "4h+",
 "deadline": "YYYY-MM-DD" or null,
 "notes": "one short line of why/how, or empty"}

Rules:
- 3 to 7 tasks. Never more. Fewer is better than padded.
- Order them so the FIRST task is the smallest possible starting step (beat inertia).
- Respect the user's current load shown in context — do not pile on.
- Use a deadline only when the goal implies one (e.g. an opportunity's real deadline). Never invent one.
- Ground everything in the provided context. Return the JSON array and nothing else."""

_VALID_PRIORITY = {"critical", "strategic", "noise", "high", "medium", "low"}
_VALID_DURATION = {"15m", "30m", "1h", "2h", "3h", "4h+"}


def parse_tasks(text: str) -> list[dict]:
    """Robustly extract a task list from the model's reply (tolerates code fences / stray prose)."""
    if not text:
        return []
    t = text.strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    start, end = t.find("["), t.rfind("]")
    if start != -1 and end != -1 and end > start:
        t = t[start:end + 1]
    try:
        arr = json.loads(t)
    except Exception:
        return []
    if not isinstance(arr, list):
        return []
    out = []
    for it in arr:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title", "")).strip()[:80]
        if not title:
            continue
        pr = str(it.get("priority", "strategic")).strip().lower()
        if pr not in _VALID_PRIORITY:
            pr = "strategic"
        du = str(it.get("duration", "")).strip().lower()
        if du not in _VALID_DURATION:
            du = "1h"
        dl = it.get("deadline")
        notes = str(it.get("notes", "")).strip()[:200]
        out.append({"title": title, "priority": pr, "duration": du,
                    "deadline": dl or None, "notes": notes})
    return out[:7]


def propose_tasks(tools: NovaTools, goal: str, model: Optional[str] = None) -> list[dict]:
    """One generate_content call → a validated, sequenced task proposal (not written anywhere)."""
    from google import genai
    from google.genai import types

    model = model or gemini_model()
    ctx = tools.get_today_context().model_dump()
    extra = ""
    gl = (goal or "").lower()
    if any(k in gl for k in ("hackathon", "intern", "opportunit", "apply", "fellowship",
                             "contest", "gsoc", "competition", "scholarship")):
        opps = tools.get_opportunities(min_score=5, limit=6)
        if opps:
            extra = "\n\nRELEVANT OPPORTUNITIES (real, already scored — ground in these):\n" + \
                    json.dumps(opps, ensure_ascii=False, default=str)

    prompt = (f"GOAL:\n{goal}\n\nUSER CONTEXT (ground everything in this; respect the load):\n"
              f"{json.dumps({'today': ctx}, ensure_ascii=False, default=str)}{extra}")
    client = genai.Client()  # reads GOOGLE_API_KEY from env
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=PROPOSE_SYS, temperature=0.4),
    )
    return parse_tasks(getattr(resp, "text", None) or "")
