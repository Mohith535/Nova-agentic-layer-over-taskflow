"""Nova orchestrator — the root ADK agent that routes to the right specialist.

Why a router (and three separate agents) rather than one agent with every tool? Three reasons,
each defensible: (1) **least privilege** — the Coach and Briefing agents are read-only; only the
Planner can write, so a coaching request can never mutate data; (2) **distinct prompts** — the
Coach's "name the mechanism, no cheerleading" voice and the Planner's "size up, respect load"
discipline are different jobs that degrade if blended into one instruction; (3) **distinct
cadence** — Briefing runs unattended (the GitHub Action), the others on demand. The router keeps
each agent focused and lets us reason about each boundary independently.
"""

from __future__ import annotations

from typing import Optional

from google.adk.agents import Agent

from .agents.briefing_agent import build_briefing_agent
from .agents.coach_agent import build_coach_agent
from .agents.planning_agent import build_planning_agent
from .config import data_dir as default_data_dir
from .config import gemini_model
from .mcp.tools import NovaTools

ROOT_INSTRUCTION = """\
You are Nova, the concierge over a user's TaskFlow. You do not answer productivity questions
yourself — you route to exactly one specialist and let them respond:

- Transfer to `planning` when the user gives a GOAL to break into tasks ("prepare for the
  Microsoft interview", "plan my launch week", "I need to learn React").
- Transfer to `briefing` when they ask what to do now / today / this morning, or want a brief.
- Transfer to `coach` when they ask WHY they keep failing/avoiding, or about their patterns,
  habits, or behavioral feedback.

Pick the single best specialist and transfer. Do not pad with your own commentary. Keep the
TaskFlow voice everywhere: concrete, judgment-free, no cheerleading, no emoji.

If the user wants to reset, start over, or have you forget what you know about them: answer
warmly with a clean-slate framing — that is a healthy reset, not a failure. Tell them they can
wipe your memory instantly via the "clear" link beside "What Nova remembers" (their TaskFlow
tasks stay untouched), and that to clear the actual task board they can use `taskflow freshstart`
(lifts overdue pressure without deleting) or `freshstart --all` (a full wipe). Never claim you
have already cleared anything yourself — you can't from chat; you point them to the control.
"""


def build_orchestrator(data_dir: Optional[str] = None, model: Optional[str] = None,
                       *, use_mcp: bool = False) -> Agent:
    """Build the router + its three specialists.

    `use_mcp=False` (default): the agents call the shared NovaTools in-process — reliable, the
    primary multi-agent showcase. `use_mcp=True`: every specialist gets its tools from a live
    `nova.mcp.server` subprocess over stdio, with the read-only/write split enforced per agent
    *through MCP* — the load-bearing MCP demonstration.
    """
    dd = data_dir or default_data_dir()
    tools = None if use_mcp else NovaTools(dd)
    m = model or gemini_model()
    return Agent(
        name="nova",
        model=m,
        description="Nova — multi-agent productivity intelligence over TaskFlow.",
        instruction=ROOT_INSTRUCTION,
        sub_agents=[
            build_briefing_agent(tools, m, use_mcp=use_mcp, data_dir=dd),
            build_planning_agent(tools, m, use_mcp=use_mcp, data_dir=dd),
            build_coach_agent(tools, m, use_mcp=use_mcp, data_dir=dd),
        ],
    )
