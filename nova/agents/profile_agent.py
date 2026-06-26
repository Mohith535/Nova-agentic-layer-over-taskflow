"""Profile Agent — psychological onboarding: maps 7 raw Q&A answers to user_profile.json.

The web UI owns the Q&A state machine (one question at a time, full screen, dot progress).
This module provides the intelligence layer:
  1. finalize_profile() — one Gemini call normalizes free-text + option answers to the
     structured schema (handles "definitely a night person" → "evening", etc.)
  2. The canonical profile schema (PROFILE_SCHEMA) used by every other agent.

Architecturally this is the 5th agent in the Nova system. It runs once at onboarding (and
whenever the user recalibrates), not on every session — so the full ADK tool loop is
justified here by the one-time cost model.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional

from ..mcp.tools import NovaTools


# Canonical schema — the valid values every downstream agent reads
PROFILE_SCHEMA = {
    "energy_state":     ["momentum", "overwhelmed", "behind", "uncertain", "steady"],
    "work_style":       ["deadline_driven", "step_by_step", "planner", "focus_defender"],
    "drive_type":       ["promotion", "prevention", "both"],
    "coaching_style":   ["direct", "analytical", "socratic", "behavioral"],
    "accountability":   ["internal", "external", "momentum", "deadline"],
    "memory_depth":     ["deep", "standard", "light", "fresh"],
}

# Human-readable labels for the onboarding UI
Q_OPTIONS = {
    "q1_energy": [
        ("momentum",    "I have clarity and momentum. I know what to do and I'm moving."),
        ("overwhelmed", "There's too much. I don't know where to start."),
        ("behind",      "I'm behind, and I know it. That weight is there."),
        ("uncertain",   "I'm running, but I'm not sure I'm working on the right things."),
        ("steady",      "Scattered. Too many open threads, nothing fully closed."),
    ],
    "q2_work_style": [
        ("deadline_driven", "I work best when the deadline is close. Pressure is where clarity lives."),
        ("step_by_step",    "Big things shut me down until I break them into something smaller."),
        ("planner",         "I need to know the right approach before I can start. I think before I move."),
        ("focus_defender",  "Starting isn't the problem. Staying in it without getting pulled away is."),
    ],
    "q3_drive": [
        ("promotion",  "The gain. What I can build, learn, or become because of it."),
        ("prevention", "The cost. What gets worse or breaks if I don't do it."),
        ("both",       "Both. Loss and gain both have real weight."),
    ],
    "q4_coaching": [
        ("direct",      "Tell me straight what's happening. Unvarnished is fine."),
        ("analytical",  "Show me the pattern. Data without the lecture."),
        ("socratic",    "Ask me what I think is wrong. I usually know — I just need to say it."),
        ("behavioral",  "Give me one thing I can do in the next 10 minutes. Small is real."),
    ],
    "q5_accountability": [
        ("internal",  "A promise to myself. I don't want to be the person who doesn't."),
        ("external",  "Someone else counting on me. External stakes make it real."),
        ("momentum",  "Seeing it move. Once momentum starts, I stay in it."),
        ("deadline",  "The deadline itself. If urgency isn't real, nothing moves."),
    ],
    "q7_memory": [
        ("deep",     "Everything. The more you know, the better you show up for me."),
        ("standard", "Track what I do and how I work. Keep the emotional layer lighter."),
        ("light",    "Just who I am and what I'm building. Professional context only."),
        ("fresh",    "Start fresh each time. I'll bring you what you need when I need you."),
    ],
}

NORMALIZE_SYS = """\
You are a data normalizer for a psychological profiling system. The user answered 7 onboarding
questions. Map their answers to the structured schema.

Return ONLY a valid JSON object — no commentary, no markdown fences, no explanation:
{
  "energy_state":   "momentum|overwhelmed|behind|uncertain|steady",
  "work_style":     "deadline_driven|step_by_step|planner|focus_defender",
  "drive_type":     "promotion|prevention|both",
  "coaching_style": "direct|analytical|socratic|behavioral",
  "accountability": "internal|external|momentum|deadline",
  "purpose_90d":    "<VERBATIM text the user wrote for their 90-day goal>",
  "memory_depth":   "deep|standard|light|fresh"
}

Purpose_90d MUST be exactly what the user typed for Q6 — no editing, no shortening, no
paraphrasing. Copy it character-for-character. If they left it blank, use empty string "".
For all other fields: if the user selected a labelled option, map it directly. If they typed
free text, pick the closest schema value.
"""


def finalize_profile(
    tools: NovaTools,
    raw_answers: dict,
    basics: dict,
    model: Optional[str] = None,
) -> dict:
    """Map raw onboarding answers to a normalized user_profile.json.

    Args:
        raw_answers: {
            "q1": "<selected label or value>",
            "q2": "<selected label or value>",
            "q3": "<selected label or value>",
            "q4": "<selected label or value>",
            "q5": "<selected label or value>",
            "q6_text": "<free text — the 90-day purpose>",
            "q7": "<selected label or value>",
        }
        basics: {"name": ..., "pronouns": ..., "life_context": ..., "peak_hours": ...}
    Returns:
        The full profile dict (already written to disk).
    """
    from google import genai
    from google.genai import types
    from ..config import fast_gemini_model

    model = model or fast_gemini_model()

    prompt = (
        "Map these onboarding answers to the profile schema.\n\n"
        "ANSWERS:\n" + json.dumps(raw_answers, indent=2, ensure_ascii=False) + "\n\n"
        "QUESTION GUIDE:\n"
        "q1 = current energy / relationship with work ahead (→ energy_state)\n"
        "q2 = how they get started on important work (→ work_style)\n"
        "q3 = what drives prioritization (→ drive_type)\n"
        "q4 = what helps when stuck (→ coaching_style)\n"
        "q5 = what makes them follow through (→ accountability)\n"
        "q6_text = verbatim 90-day purpose — copy exactly (→ purpose_90d)\n"
        "q7 = how much to remember between sessions (→ memory_depth)\n"
    )

    nova_fields: dict = {}
    try:
        client = genai.Client()
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=NORMALIZE_SYS,
                temperature=0.1,
                max_output_tokens=400,
            ),
        )
        text = (getattr(resp, "text", None) or "").strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            nova_fields = json.loads(m.group(0))
    except Exception:
        # Fallback: direct value mapping from the answer keys
        nova_fields = {
            "energy_state":   _direct_map(raw_answers.get("q1", ""), "q1_energy"),
            "work_style":     _direct_map(raw_answers.get("q2", ""), "q2_work_style"),
            "drive_type":     _direct_map(raw_answers.get("q3", ""), "q3_drive"),
            "coaching_style": _direct_map(raw_answers.get("q4", ""), "q4_coaching"),
            "accountability": _direct_map(raw_answers.get("q5", ""), "q5_accountability"),
            "purpose_90d":    (raw_answers.get("q6_text") or "").strip(),
            "memory_depth":   _direct_map(raw_answers.get("q7", ""), "q7_memory"),
        }

    # Validate — fall back to first valid option if model hallucinated
    for field, valid in PROFILE_SCHEMA.items():
        if nova_fields.get(field) not in valid:
            nova_fields[field] = valid[0]

    profile = {
        "version": 1,
        "profile_complete": True,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "basics": {
            "name":         (basics.get("name") or "").strip(),
            "pronouns":     (basics.get("pronouns") or "").strip(),
            "life_context": (basics.get("life_context") or "").strip(),
            "peak_hours":   (basics.get("peak_hours") or "").strip(),
        },
        "nova": {
            "energy_state":   nova_fields.get("energy_state", ""),
            "work_style":     nova_fields.get("work_style", ""),
            "drive_type":     nova_fields.get("drive_type", ""),
            "coaching_style": nova_fields.get("coaching_style", ""),
            "accountability": nova_fields.get("accountability", ""),
            "purpose_90d":    (nova_fields.get("purpose_90d") or raw_answers.get("q6_text") or "").strip(),
            "memory_depth":   nova_fields.get("memory_depth", "deep"),
        },
        "ai_import": None,
    }

    tools.write_user_profile(profile)
    return profile


def _direct_map(answer: str, q_key: str) -> str:
    """If the answer is already a valid schema value or a known label, map it directly."""
    opts = Q_OPTIONS.get(q_key, [])
    answer_lower = (answer or "").lower().strip()
    for value, label in opts:
        if answer_lower == value or answer_lower == label.lower():
            return value
    # Partial match on value
    for value, _ in opts:
        if value in answer_lower:
            return value
    return opts[0][0] if opts else ""
