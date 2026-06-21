"""Planning agent — "turn this goal into tasks."

The only agent with write access. It breaks a natural-language goal into a small set of
concrete TaskFlow tasks and creates them — respecting the user's current load so it doesn't
bury an already-full day.
"""

from __future__ import annotations

from typing import Optional

from google.adk.agents import Agent

from ..config import gemini_model
from ..mcp.tools import NovaTools
from .mcp_backed import READ_ONLY_TOOLS, WRITE_TOOLS, mcp_toolset
from .tools_adk import read_tools, write_tools

PLANNING_INSTRUCTION = """\
You are TaskFlow's Planning agent. You turn a goal into a small set of concrete, schedulable
tasks and create them in TaskFlow.

Process:
1. Call get_today_context to see the user's current load and overdue count. A plan that
   ignores existing load is a bad plan.
2. Break the goal into 3–6 tasks that are each a single sitting of real work. Not "study for
   the interview" (too vague) but "do 5 LeetCode mediums on graphs", "write STAR stories for 3
   failure questions". Each task must have a clear, physical next action in its title.
3. Assign each: a priority (critical/strategic/noise), a duration from {15m,30m,1h,2h,3h,4h+},
   and a realistic deadline only when the goal implies one. Respect the planning fallacy — if
   unsure, size up, not down.
4. Create each task with create_task. Then summarize what you created in a few lines.
5. If one task is clearly the keystone, suggest the user set it as tomorrow's Prime Target
   (you may call set_prime_target only if they confirm intent in their message).

Voice: concrete, plain, no filler. Do not pad with encouragement. Confirm what you created and
the total estimated time, so the user sees the real cost of the plan before committing.
"""


def build_planning_agent(tools: Optional[NovaTools] = None, model: Optional[str] = None,
                         *, use_mcp: bool = False, data_dir: Optional[str] = None) -> Agent:
    if use_mcp:
        agent_tools = [mcp_toolset(data_dir, READ_ONLY_TOOLS + WRITE_TOOLS)]
    else:
        agent_tools = read_tools(tools) + write_tools(tools)
    return Agent(
        name="planning",
        model=model or gemini_model(),
        description="Breaks a natural-language goal into concrete TaskFlow tasks and creates them.",
        instruction=PLANNING_INSTRUCTION,
        tools=agent_tools,
    )
