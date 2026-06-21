"""Nova CLI — ``nova brief | plan | coach | ask | mcp``.

Each agent command runs one turn through ADK and prints the response. ``mcp`` runs/inspects the
MCP server (no key needed). Agent commands need a Gemini key; if it's missing we say exactly how
to set it instead of crashing.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
import warnings

from . import __version__

# ADK emits an experimental-feature UserWarning while building tool schemas. It's harmless;
# silence it so the CLI/demo output is just the agent's response.
warnings.filterwarnings("ignore", message=r".*JSON_SCHEMA_FOR_FUNC_DECL.*")


def _run_once(agent, message: str) -> str:
    """Run a single user turn through an ADK agent and return its final text."""
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    runner = InMemoryRunner(agent=agent, app_name="nova")
    user_id = "local"
    created = runner.session_service.create_session(app_name="nova", user_id=user_id)
    if inspect.isawaitable(created):
        created = asyncio.run(created)
    session_id = created.id

    content = types.Content(role="user", parts=[types.Part(text=message)])
    chunks: list[str] = []
    for event in runner.run(user_id=user_id, session_id=session_id, new_message=content):
        try:
            if event.is_final_response() and event.content and event.content.parts:
                for part in event.content.parts:
                    if getattr(part, "text", None):
                        chunks.append(part.text)
        except Exception:
            continue
    return "\n".join(chunks).strip()


def main(argv=None) -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="nova", description=f"Nova v{__version__} — TaskFlow intelligence layer.")
    parser.add_argument("--output", choices=["text", "markdown"], default="text")
    parser.add_argument("--mcp", action="store_true",
                        help="Route tools through the live MCP server (stdio subprocess) rather "
                             "than in-process — demonstrates the real MCP transport.")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("brief", help="A daily mission briefing from your live TaskFlow data.")
    p_plan = sub.add_parser("plan", help="Turn a goal into concrete TaskFlow tasks.")
    p_plan.add_argument("goal", nargs="+", help="The goal, e.g. \"prepare for the Microsoft interview\".")
    p_coach = sub.add_parser("coach", help="Behavioral coaching grounded in your real data.")
    p_coach.add_argument("question", nargs="*", help="Optional question; default analyzes your patterns.")
    p_ask = sub.add_parser("ask", help="Ask Nova anything; it routes to the right specialist.")
    p_ask.add_argument("message", nargs="+")
    p_mcp = sub.add_parser("mcp", help="Run or inspect the MCP server.")
    p_mcp.add_argument("--selftest", action="store_true", help="List MCP tools and exit.")
    p_web = sub.add_parser("web", help="Launch the Nova web console (localhost).")
    p_web.add_argument("--port", type=int, default=8765)

    args = parser.parse_args(argv)

    if args.cmd is None:
        parser.print_help()
        return

    if args.cmd == "mcp":
        from .mcp.server import main as mcp_main

        mcp_main(["--selftest"] if args.selftest else [])
        return

    if args.cmd == "web":
        from .web.server import serve

        serve(port=args.port)  # localhost console; needs a key only when you run an agent
        return

    # Agent commands need a model key.
    from . import config

    if not config.ensure_api_key():
        print(
            "Nova needs a Gemini API key for its agents.\n"
            "  Get one (free): https://aistudio.google.com/apikey\n"
            "  Then either put GEMINI_API_KEY=... in a .env file here, or run:\n"
            "    setx GEMINI_API_KEY your-key   (then open a new terminal)\n"
            "Tip: `nova mcp --selftest` works without a key.",
            file=sys.stderr,
        )
        sys.exit(2)

    from .config import data_dir
    from .mcp.tools import NovaTools

    dd = data_dir()
    use_mcp = args.mcp
    tools = None if use_mcp else NovaTools(dd)  # in-process tools (skipped in MCP mode)
    if use_mcp:
        print("(routing through the live MCP server subprocess…)", file=sys.stderr)

    if args.cmd == "brief":
        from .agents.briefing_agent import build_briefing_agent

        agent = build_briefing_agent(tools, use_mcp=use_mcp, data_dir=dd)
        message = "Give me my briefing for right now."
    elif args.cmd == "plan":
        from .agents.planning_agent import build_planning_agent

        agent = build_planning_agent(tools, use_mcp=use_mcp, data_dir=dd)
        message = " ".join(args.goal)
    elif args.cmd == "coach":
        from .agents.coach_agent import build_coach_agent

        agent = build_coach_agent(tools, use_mcp=use_mcp, data_dir=dd)
        message = " ".join(args.question) or (
            "What patterns do you see in how I work, and what is the one thing I should change?"
        )
    elif args.cmd == "ask":
        from .orchestrator import build_orchestrator

        agent = build_orchestrator(dd, use_mcp=use_mcp)
        message = " ".join(args.message)
    else:
        parser.print_help()
        return

    try:
        out = _run_once(agent, message)
    except Exception as e:  # surface a clean error, not a stack trace
        print(f"Nova run failed: {e}", file=sys.stderr)
        sys.exit(1)
    print(out or "(no response)")


if __name__ == "__main__":
    main()
