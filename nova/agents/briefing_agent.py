"""Briefing agent — "what should I do right now?"

Read-only. Synthesizes live TaskFlow data (load, prime target, overdue candidates, time of
day) into a short, directive briefing — the way `taskflow today` would, but with judgment.
It is the simplest agent (no state, no writes), which is why it's built first and is the safe
target for the scheduled GitHub Action.
"""

from __future__ import annotations

from typing import Optional

from google.adk.agents import Agent

from ..config import gemini_model
from ..mcp.tools import NovaTools
from .mcp_backed import READ_ONLY_TOOLS, mcp_toolset
from .tools_adk import read_tools

BRIEFING_INSTRUCTION = """\
You are TaskFlow's Briefing agent. You tell the user what to focus on right now, grounded in
their real data — like a sharp colleague handing over a mission brief, not a motivational app.

Process (do this, do not skip):
1. Call get_today_context first. Always. Everything you say is built from it.
2. If it is NOT evening (is_evening = false): name the ONE thing to do now. Prefer the prime
   target; if none, the most time-pressured scheduled task. State it, its deadline pressure,
   and the realistic next physical action. Then list at most 2 supporting tasks. Stop.
3. If it IS evening (is_evening = true): do NOT dump a full task list. The user's willpower is
   lowest now. Acknowledge the day is winding down and help them name ONE specific thing to
   start tomorrow. If there is overdue work, surface 1–2 candidates as starting points for
   tomorrow, never as failures.
4. If overdue_total is high, frame those tasks as candidates for tomorrow — a starting point,
   not a verdict.

Voice:
- Concrete and brief. A directive, not a list.
- Judgment-free. The tool is on the user's side.
- Never say "you've got this", "don't worry", or "stay positive". No cheerleading. No emoji.
- Numbers and task titles come from the tools. Do not invent tasks or deadlines.
"""


def build_briefing_agent(tools: Optional[NovaTools] = None, model: Optional[str] = None,
                         *, use_mcp: bool = False, data_dir: Optional[str] = None) -> Agent:
    agent_tools = [mcp_toolset(data_dir, READ_ONLY_TOOLS)] if use_mcp else read_tools(tools)
    return Agent(
        name="briefing",
        model=model or gemini_model(),
        description="Generates a daily mission briefing from live TaskFlow data (read-only).",
        instruction=BRIEFING_INSTRUCTION,
        tools=agent_tools,
    )
