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


IMPORT_EXTRACT_SYS = """\
You are analyzing a "portrait" the user obtained from another AI assistant (ChatGPT, Claude,
Gemini, Perplexity, etc.) — their description of who the user is, how they work, and what they
want. Extract a structured profile for a behavioral focus tool called Nova.

Return ONLY valid JSON — no markdown, no commentary:
{
  "best_guess": {
    "q1": "momentum|overwhelmed|behind|uncertain|steady|",
    "q2": "deadline_driven|step_by_step|planner|focus_defender|",
    "q3": "promotion|prevention|both|",
    "q4": "direct|analytical|socratic|behavioral|",
    "q5": "internal|external|momentum|deadline|",
    "q6_text": "<their 90-day goal / what they're building — their own words if stated, else a faithful 1-2 sentence inference>",
    "q7": "deep|standard|light|fresh|"
  },
  "memory_seeds": [
    {"kind": "pattern|preference|fact|emotion", "text": "<one concrete thing worth remembering>"}
  ],
  "recognized": "<ONE short second-person sentence naming the single most defining thing you learned>"
}

Field meanings:
  q1 = current relationship with the work ahead (energy_state)
  q2 = how they start important work (work_style)
  q3 = what drives prioritization (drive_type)
  q4 = what helps when stuck (coaching_style)
  q5 = what makes them follow through (accountability)
  q6_text = the real 90-day goal underneath the to-do list (purpose)
  q7 = how much to remember between sessions (memory_depth)

Rules:
- For q1..q5,q7: ONLY output a listed value. If the portrait gives no clear signal, use "".
  Empty is honest — do NOT guess randomly.
- q1 is about CURRENT state; portraits rarely reveal it — usually "".
- q6_text: prefer the user's literal words about goals/ambition; infer faithfully only if implied.
- memory_seeds: 3-8 concrete, specific items. No flattery, no fluff. Empty list if the portrait is thin.
- recognized: must reference something real from the text. Never generic.
"""


def extract_import(tools: NovaTools, text: str, source: str = "other",
                   model: Optional[str] = None) -> dict:
    """Break a pasted AI portrait into Nova's structured signals.

    Returns: {"best_guess": {q1..q7}, "memory_seeds": [{kind,text}], "recognized": str}
    Never raises — returns the empty structure on any failure.
    """
    from google import genai
    from google.genai import types
    from ..config import best_model, mark_exhausted

    text = (text or "").strip()[:8000]  # cap input to protect quota
    out = {"best_guess": {}, "memory_seeds": [], "recognized": "", "error": ""}
    if not text:
        return out

    prompt = f"SOURCE AI: {source}\n\nPORTRAIT THE USER PASTED:\n{text}"
    # Quota-aware: if a model is rate-limited, mark it and fall through to the next tier —
    # the same routing the main agents use, so one exhausted model can't kill the import.
    for _ in range(3):
        m = model or best_model("ask")
        try:
            client = genai.Client()
            resp = client.models.generate_content(
                model=m,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=IMPORT_EXTRACT_SYS,
                    temperature=0.2,
                    max_output_tokens=900,
                ),
            )
            raw = (getattr(resp, "text", None) or "").strip()
            mm = re.search(r"\{.*\}", raw, re.DOTALL)
            if mm:
                parsed = json.loads(mm.group(0))
                out["best_guess"] = parsed.get("best_guess") or {}
                out["memory_seeds"] = parsed.get("memory_seeds") or []
                out["recognized"] = (parsed.get("recognized") or "").strip()
            out["error"] = ""
            break
        except Exception as e:
            msg = str(e)
            if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                mark_exhausted(m)
                out["error"] = "rate_limit"
                model = None  # let best_model pick the next non-exhausted tier
                continue
            out["error"] = "no_key" if ("API_KEY" in msg.upper() or "authentication" in msg.lower()) else "unavailable"
            break

    # Validate enums — honest "" if the model gave something invalid/missing
    enum_map = {
        "q1": PROFILE_SCHEMA["energy_state"],
        "q2": PROFILE_SCHEMA["work_style"],
        "q3": PROFILE_SCHEMA["drive_type"],
        "q4": PROFILE_SCHEMA["coaching_style"],
        "q5": PROFILE_SCHEMA["accountability"],
        "q7": PROFILE_SCHEMA["memory_depth"],
    }
    bg = out["best_guess"] if isinstance(out["best_guess"], dict) else {}
    for k, valid in enum_map.items():
        if bg.get(k) not in valid:
            bg[k] = ""
    bg["q6_text"] = (bg.get("q6_text") or "").strip()
    out["best_guess"] = bg
    # sanitize seeds
    seeds = []
    for s in (out["memory_seeds"] or [])[:10]:
        if isinstance(s, dict) and (s.get("text") or "").strip():
            seeds.append({"kind": (s.get("kind") or "fact").strip(),
                          "text": s["text"].strip()[:300]})
    out["memory_seeds"] = seeds
    return out


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
