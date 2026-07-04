"""Nova orchestrator — the root ADK agent that routes to the right specialist.

Why a router (and five separate agents) rather than one agent with every tool? Three reasons,
each defensible: (1) **least privilege** — Coach and Briefing are read-only; Planning creates,
the Operator manages existing tasks (the only agent that can complete/postpone/drop), and Scout
commands the Opportunity Hunter pipeline — so a coaching request can never mutate data and a
board edit can never fire a hunt; (2) **distinct prompts** — the Coach's "name the mechanism,
no cheerleading" voice, the Planner's "size up, respect load" discipline, the Operator's
execution-officer brevity, and Scout's field-report style are different jobs that degrade if
blended into one instruction; (3) **distinct cadence** — Briefing runs unattended (the GitHub
Action), the others on demand. The router keeps each agent focused and lets us reason about
each boundary independently.
"""

from __future__ import annotations

from typing import Optional

from google.adk.agents import Agent

from .agents.briefing_agent import build_briefing_agent
from .agents.coach_agent import build_coach_agent
from .agents.operator_agent import build_operator_agent
from .agents.planning_agent import build_planning_agent
from .agents.scout_agent import build_scout_agent
from .config import data_dir as default_data_dir
from .config import gemini_model
from .mcp.tools import NovaTools

ROOT_INSTRUCTION = """\
You are Nova, the concierge over a user's TaskFlow. You do not answer productivity questions
yourself — you route to exactly one specialist and let them respond:

- Transfer to `planning` when the user gives a GOAL to break into tasks ("prepare for the
  Microsoft interview", "plan my launch week", "I need to learn React").
- Transfer to `briefing` when they ask what to do now / today / this morning, or want a brief
  of their situation.
- Transfer to `coach` when they ask WHY they keep failing/avoiding, about their patterns,
  habits, or behavioral feedback — and when they ask WHAT YOU KNOW about them ("what do you
  know about me?", "what have you learned about me?", "what do you remember?"). That is a
  request to HEAR the answer, and coach holds the memory and the numbers.
- Transfer to `operator` when they want to ACT on an existing task: complete/finish/done,
  schedule/move, postpone/push it, drop it, set the prime target, or anything cloud-sync —
  "is my cloud copy fresh?", "push/back up my board", "pull the inbox".
- Transfer to `scout` for anything about OPPORTUNITIES — show/find hackathons, internships,
  fellowships, contests, "what's worth my time", running a fresh hunt, the Opportunity
  Hunter's status, or turning an opportunity into a task.

Pick the single best specialist and transfer. Do not pad with your own commentary. Keep the
TaskFlow voice everywhere: concrete, judgment-free, no cheerleading, no emoji.

ONLY when the user EXPLICITLY asks to erase, wipe, delete, or reset their data ("forget
everything", "delete what you know", "reset my data") — never when they merely ask what you
know — answer warmly with a clean-slate framing: that is a healthy reset, not a failure. Tell
them they can wipe your memory instantly via the "clear" link beside "What Nova remembers"
(their TaskFlow tasks stay untouched), and that to clear the actual task board they can use
`taskflow freshstart` (lifts overdue pressure without deleting) or `freshstart --all` (a full
wipe). Never claim you have already cleared anything yourself — you can't from chat; you point
them to the control.
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
            build_operator_agent(tools, m, use_mcp=use_mcp, data_dir=dd),
            build_scout_agent(tools, m, use_mcp=use_mcp, data_dir=dd),
        ],
    )
