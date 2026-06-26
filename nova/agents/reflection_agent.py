"""Reflection Agent — end-of-session synthesis, writes 2-3 behavioral memory entries.

The 6th agent in the Nova system. Triggered by:
  - `nova reflect` CLI command
  - "End session" button in the Nova web UI
  - (future) automatic trigger after each TaskFlow focus session completes

Voice: scientist-observer. Field notes, not a diary. Short, specific, non-judgmental.
"Avoided the API task 3 days running" is a fact. "You're lazy" is not.

The entries it writes become the raw material for tomorrow's Greeting Agent — creating a
feedback loop: Reflection (today) → Memory → Greeting (tomorrow) → more grounded session.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from ..mcp.tools import NovaTools


REFLECT_SYS = """\
You are Nova's observational memory logger. Your job is to write 2-3 crisp behavioral field
notes about what happened in this session/day, for the user's private memory store.

Each entry is one sentence, under 120 characters.
Write at least:
  - 1 [pattern] entry: a behavioral observation (what they did or avoided)
  - 1 [fact] entry: numbers (X completed, Y postponed, Z focus minutes)
  - 1 [emotion] entry ONLY if clearly supported by the data (inferred energy state)

Tone rules:
  - "Avoided" is a behavior, not a judgment. Use it.
  - "Postponed again" is a fact. Use it.
  - "Failed", "lazy", "unproductive" — never. These are not observations.
  - If data is thin (nothing completed, nothing postponed), write what IS there. Don't invent.
  - Ground every claim in the provided data. No invented details.

Return ONLY a JSON array — no commentary, no markdown, no explanation:
[
  {"kind": "pattern|emotion|fact", "text": "<one sentence, max 120 chars>"},
  ...
]
"""


def run_reflection(tools: NovaTools, model: Optional[str] = None) -> list[dict]:
    """Gather today's session activity, generate 2-3 memory entries, persist them.

    Returns the list of memory entries that were successfully saved.
    Never raises — returns [] on any failure (non-blocking, session cleanup tool).
    """
    from google import genai
    from google.genai import types
    from ..config import fast_gemini_model

    model = model or fast_gemini_model()

    try:
        activity = tools.get_session_activity(hours=24)
        profile = tools.read_user_profile()
        name = (profile.get("basics") or {}).get("name", "")

        prompt = (
            f"Write memory entries for {'this session' if not name else name + chr(39) + 's session'}.\n\n"
            f"SESSION DATA:\n{json.dumps(activity, indent=2, ensure_ascii=False, default=str)}"
        )

        client = genai.Client()
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=REFLECT_SYS,
                temperature=0.35,
                max_output_tokens=300,
            ),
        )
        text = (getattr(resp, "text", None) or "").strip()

        m = re.search(r"\[.*\]", text, re.DOTALL)
        entries: list[dict] = json.loads(m.group(0)) if m else []
    except Exception:
        return []

    saved = []
    for e in entries[:3]:
        if isinstance(e, dict) and (e.get("text") or "").strip():
            result = tools.remember(e["text"].strip(), e.get("kind", "pattern"))
            if result:
                saved.append(result)

    return saved
