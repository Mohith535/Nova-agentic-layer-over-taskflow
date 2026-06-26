"""Greeting Agent — fast-path personalized session opener.

Architecturally a separate agent with its own system prompt, data contract, and output spec.
Runs as a single Gemini call (no ADK tool loop) for quota efficiency — the greeting fires
every session start, so burning 3-5 calls per hello is wasteful on a free tier.

What it reads (deterministic, zero model calls before the single generate):
  1. user_profile.json  — psychological profile (purpose_anchor, work_style, coaching_style …)
  2. recall_memory()    — last 5 memory entries (emotional thread, patterns)
  3. get_today_context() — prime target, overdue count, time of day  (capped 1.5 s)

Output: 2-4 sentences. Uses the user's verbatim words from their purpose_anchor. "Bro code"
register — specific enough to be personal, discrete enough not to embarrass if seen by others.
"""

from __future__ import annotations

import json
from typing import Optional

from ..mcp.tools import NovaTools


GREETING_SYS = """\
You are Nova — a trusted AI partner who knows this user deeply. Your single job right now is
to write the OPENING MESSAGE of a new session in 2–4 short sentences.

You have been given everything: the user's psychological profile, recent memory, and their
current task situation. Use it. Do not waste it on a generic hello.

RULES — break any of these and the greeting fails:
1. Use the user's EXACT WORDS from purpose_90d when referencing their goal. Not a summary,
   not a paraphrase. If they wrote "build a product 1,000 people use" — say exactly that.
2. 2–4 sentences. Short. Tight is respectful.
3. Peer-to-peer voice, not assistant-to-user. Trusted colleague who has been watching, not
   a service agent opening a ticket.
4. "Bro code" standard: warm and specific, but if a stranger looks over their shoulder it
   reads as a colleague greeting — not an AI exposing private data. Imply; don't spell out.
5. NEVER start with: Hello / Hi / Hey / Good morning / Welcome back / How can I assist.
   Start with something specific and real.
6. NEVER say "I'm Nova" or introduce yourself — they know.
7. Adapt tone to coaching_style:
   - direct:     blunt opener, no softeners, name the situation fast
   - analytical: open with a number or pattern ("Three days. Two things stacked.")
   - socratic:   open with a question that makes them think
   - behavioral: anchor to one small first step immediately
8. If memory has a serious emotional thread, reference it briefly without naming it loudly.
9. If profile is empty / profile_complete is false: write a warm neutral opener using the
   name if available. Never invent profile data.
10. No emoji. No cheerleading. No "you've got this." No "I'm here to help."
"""


def generate_greeting(tools: NovaTools, model: Optional[str] = None) -> str:
    """One Gemini call → personalized 2-4 sentence greeting.

    Returns plain text (may contain **bold** markdown). Never raises — returns a safe
    fallback string on any error.
    """
    from google import genai
    from google.genai import types
    from ..config import fast_gemini_model
    import concurrent.futures as _cf

    model = model or fast_gemini_model()

    # ---- gather data deterministically (zero model calls) ----
    profile = tools.read_user_profile()
    mem = tools.recall_memory()

    ctx = None
    try:
        with _cf.ThreadPoolExecutor(max_workers=1) as ex:
            ctx = ex.submit(tools.get_today_context).result(timeout=1.5)
    except Exception:
        pass

    basics = profile.get("basics") or {}
    nova_p = profile.get("nova") or {}
    name = basics.get("name", "")

    data = {
        "profile_complete": profile.get("profile_complete", False),
        "user": {
            "name": name,
            "pronouns": basics.get("pronouns", ""),
            "life_context": basics.get("life_context", ""),
            "peak_hours": basics.get("peak_hours", ""),
        },
        "psychological_profile": {
            "energy_state": nova_p.get("energy_state", ""),
            "work_style": nova_p.get("work_style", ""),
            "drive_type": nova_p.get("drive_type", ""),
            "coaching_style": nova_p.get("coaching_style", ""),
            "accountability": nova_p.get("accountability", ""),
            "purpose_90d": nova_p.get("purpose_90d", ""),
            "memory_depth": nova_p.get("memory_depth", ""),
        },
        "recent_memory": (mem[-5:] if mem else []),
        "today": (
            {
                "is_evening": ctx.is_evening,
                "prime_target": ctx.prime_target.title if ctx.prime_target else None,
                "overdue_total": ctx.overdue_total,
                "overdue_first": ctx.overdue_candidates[0].title if ctx.overdue_candidates else None,
            }
            if ctx else {}
        ),
    }

    prompt = (
        "Generate the session opening message.\n\n"
        f"ALL USER DATA:\n{json.dumps(data, indent=2, ensure_ascii=False, default=str)}"
    )

    try:
        client = genai.Client()
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=GREETING_SYS,
                temperature=0.75,
                max_output_tokens=200,
            ),
        )
        text = (getattr(resp, "text", None) or "").strip()
        if text:
            return text
    except Exception:
        pass

    # Safe fallback — always returns something personal
    hello = f"Hey {name}" if name else "Hey"
    purpose = nova_p.get("purpose_90d", "")
    if purpose:
        return f"{hello}. Still working toward: {purpose}. What's on your mind today?"
    return f"{hello}. What's on your mind?"
