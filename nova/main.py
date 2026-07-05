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


def _doctor() -> None:
    """Green/red health report — the one command that answers 'is it set up right?'.
    Read-only and key-free to run; verifies the Gemini key live if one is present."""
    import json as _json
    import os as _os
    from pathlib import Path as _P

    from . import __version__, config

    OK, WARN, BAD, OFF = "✓", "!", "✗", "-"
    rows: list[tuple[str, str, str]] = []

    rows.append((OK, "Nova installed", f"v{__version__}"))

    # Gemini key — present? and does it actually work?
    if config.ensure_api_key():
        print("  Verifying your Gemini key (a moment)…")
        res = config.validate_gemini_key(_os.environ.get("GOOGLE_API_KEY", ""))
        if res is True:
            rows.append((OK, "Gemini API key", "verified — live AI is ON"))
        elif res is False:
            rows.append((BAD, "Gemini API key", "rejected — the key looks wrong. Fix: python configure.py"))
        else:
            rows.append((WARN, "Gemini API key", "set, but couldn't verify right now (network?) — try again"))
    else:
        rows.append((BAD, "Gemini API key", "missing — run: python configure.py  (or explore on demo data)"))

    # TaskFlow data — report state, don't seed (that's a launch-time action)
    explicit = _os.environ.get("TASKFLOW_DATA_PATH")
    dd = _P(explicit).expanduser() if explicit else (_P.home() / ".taskflow")
    tj = dd / "tasks.json"
    try:
        if tj.exists():
            n = len(_json.loads(tj.read_text(encoding="utf-8")))
            rows.append((OK, "TaskFlow data", f"ready — {n} tasks at {dd}"))
        else:
            rows.append((OFF, "TaskFlow data", f"will seed demo data on first launch ({dd})"))
    except Exception as e:
        rows.append((WARN, "TaskFlow data", f"couldn't read ({str(e)[:40]})"))

    # Opportunity Hunter — optional
    try:
        from .mcp.hunter_bridge import HunterBridge
        st = HunterBridge().status()
        if st.get("connected"):
            rows.append((OK, "Opportunity Hunter", f"connected — last run {st.get('last_run') or 'not yet'}"))
        else:
            rows.append((OFF, "Opportunity Hunter", "not installed (optional) — add via python configure.py"))
    except Exception:
        rows.append((OFF, "Opportunity Hunter", "not installed (optional)"))

    # Cloud sync — optional
    try:
        from .mcp.tools import NovaTools
        ss = NovaTools(config.data_dir()).get_sync_status()
        if ss.get("enabled"):
            rows.append((OK, "Cloud sync", f"on — {ss.get('repo')}"))
        else:
            rows.append((OFF, "Cloud sync", "not configured (optional)"))
    except Exception:
        rows.append((OFF, "Cloud sync", "not configured (optional)"))

    print("\n  ✦  NOVA — HEALTH CHECK\n")
    for mark, label, detail in rows:
        print(f"   [{mark}] {label:<20} {detail}")
    bad = sum(1 for m, _, _ in rows if m == BAD)
    warn = sum(1 for m, _, _ in rows if m == WARN)
    print()
    if bad == 0 and warn == 0:
        print("   All green — Nova is ready.\n")
    elif bad == 0:
        print("   Ready to go. Anything marked '-' is an optional extra.\n")
    else:
        print("   A couple of things need attention (see ✗). Fix them with:  python configure.py\n")


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
    sub.add_parser("doctor", help="Health check — verify your key, data, and the Opportunity Hunter.")
    parser.add_argument("--fast", action="store_true",
                        help="Quota-frugal: one model call per turn (applies to brief/coach).")

    args = parser.parse_args(argv)

    if args.cmd is None:
        parser.print_help()
        return

    if args.cmd == "mcp":
        from .mcp.server import main as mcp_main

        mcp_main(["--selftest"] if args.selftest else [])
        return

    if args.cmd == "doctor":
        _doctor()
        return

    if args.cmd == "web":
        from . import config
        config.ensure_data_dir()  # seed demo data on a clean machine so the console always runs
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

    config.ensure_data_dir()  # seed demo data on a clean machine so agents have a board to read
    from .config import data_dir
    from .mcp.tools import NovaTools

    dd = data_dir()
    use_mcp = args.mcp
    tools = None if use_mcp else NovaTools(dd)  # in-process tools (skipped in MCP mode)
    if use_mcp:
        print("(routing through the live MCP server subprocess…)", file=sys.stderr)

    # Quota-frugal path: one model call, no tool round-trips (brief/coach only).
    if args.fast and args.cmd in ("brief", "coach"):
        from .agents.fast_coach import run_fast

        fmsg = " ".join(getattr(args, "question", []) or []) if args.cmd == "coach" else ""
        try:
            out, _ = run_fast(NovaTools(dd), args.cmd, fmsg)
        except Exception as e:
            m = str(e)
            if "RESOURCE_EXHAUSTED" in m or "429" in m:
                m = "Gemini's free-tier daily limit was reached (resets in 24h). Try later, or set NOVA_GEMINI_MODEL."
            print(f"Nova: {m}", file=sys.stderr)
            sys.exit(1)
        print(out or "(no response)")
        return

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
        msg = str(e)
        if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
            msg = ("Gemini's free-tier daily limit was reached (resets every 24h). "
                   "Try later, or set NOVA_GEMINI_MODEL to another model in .env.")
        print(f"Nova: {msg}", file=sys.stderr)
        sys.exit(1)
    if not out:
        out = ("I couldn't finish that — usually the Gemini free-tier daily limit (resets in 24h). "
               "You can also set NOVA_GEMINI_MODEL to another model in .env.")
    print(out)


if __name__ == "__main__":
    main()
