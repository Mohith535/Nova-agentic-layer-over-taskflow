"""Pattern Intelligence Agent — weekly behavioral analysis, writes nova_insights.json.

The 7th agent in the Nova system. Triggered by:
  - `nova patterns` CLI command
  - Weekly (Sunday evening, GitHub Actions or local cron)
  - On-demand via the Nova web console

Role: longitudinal observer, not session coach. The Coach gives advice in the moment.
Pattern Agent analyzes 4 weeks of data to surface stable behavioral signatures — things
you can only see at scale that a single session can never reveal.

Examples of findings:
  - "Sunday completion rate is 3x higher than Monday (8 vs 2.4 avg)"
  - "#study tasks take 2.3x longer than estimated; 4+ postpones is the modal pattern"
  - "Deadline changes cluster on Thursdays — end-of-week pressure signature"

The Coach reads nova_insights.json and cites these in its responses, so the feedback loop is:
  Behavior → Pattern Agent → insights.json → Coach context → better coaching.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..mcp.tools import NovaTools


PATTERN_SYS = """\
You are Nova's Pattern Intelligence module. Analyze multi-week behavioral data and surface
3-5 specific, quantified, stable behavioral patterns.

Rules:
- Every insight must cite at least one number from the provided data.
- Describe what IS, not what SHOULD BE. Zero prescriptions, zero coaching, zero advice.
- Confidence: "high" = 10+ events supporting it; "medium" = 4-9; "low" = 1-3.
- Max 140 characters per insight. Be precise, not verbose.
- Focus on: timing patterns (day-of-week), tag patterns (postpone by domain), duration
  accuracy, what kind of tasks actually complete vs what stays stuck indefinitely.
- Do NOT restate obvious stats already visible on the dashboard (e.g. total count).
  Surface patterns the user cannot see without cross-session analysis.

Return ONLY a JSON array — no markdown, no commentary:
[
  {"insight": "<one sentence, max 140 chars>", "confidence": "high|medium|low", "data_points": N},
  ...
]
"""

_INSIGHTS_FILE = "nova_insights.json"


def run_patterns(
    tools: NovaTools,
    weeks: int = 4,
    model: Optional[str] = None,
) -> list[dict]:
    """Analyze N weeks of behavioral data, write nova_insights.json, return new entries.

    Never raises — returns [] on any failure.
    """
    from google import genai
    from google.genai import types
    from ..config import fast_gemini_model

    model = model or fast_gemini_model()

    try:
        patterns = tools.get_behavioral_patterns(weeks=weeks)
        prompt = (
            f"Surface behavioral patterns from {weeks} weeks of data.\n\n"
            f"DATA:\n{json.dumps(patterns, indent=2, ensure_ascii=False, default=str)}"
        )

        client = genai.Client()
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=PATTERN_SYS,
                temperature=0.3,
                max_output_tokens=500,
            ),
        )
        text = (getattr(resp, "text", None) or "").strip()
        m = re.search(r"\[.*\]", text, re.DOTALL)
        new_insights: list[dict] = json.loads(m.group(0)) if m else []
    except Exception:
        return []

    insights_path = Path(tools.reader.data_dir) / _INSIGHTS_FILE
    existing: list[dict] = []
    try:
        if insights_path.exists():
            data = json.loads(insights_path.read_text(encoding="utf-8"))
            existing = data if isinstance(data, list) else []
    except Exception:
        pass

    existing_texts = {e.get("insight", "").lower() for e in existing}
    saved = []
    for ins in new_insights[:5]:
        if not isinstance(ins, dict) or not (ins.get("insight") or "").strip():
            continue
        if ins["insight"].lower() in existing_texts:
            continue
        ins["generated_at"] = datetime.now().isoformat()
        ins["weeks"] = weeks
        saved.append(ins)
        existing_texts.add(ins["insight"].lower())

    all_insights = (saved + existing)[:60]
    tmp = insights_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(all_insights, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(insights_path)

    tools.audit.record("pattern_intelligence", {
        "new_insights": len(saved), "weeks": weeks, "total_on_disk": len(all_insights)
    })
    return saved


def read_insights(tools: NovaTools, limit: int = 10) -> list[dict]:
    """Read nova_insights.json — used by Coach Agent to enrich its context."""
    insights_path = Path(tools.reader.data_dir) / _INSIGHTS_FILE
    if not insights_path.exists():
        return []
    try:
        data = json.loads(insights_path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else []
        return items[:max(1, min(int(limit), 50))]
    except Exception:
        return []
