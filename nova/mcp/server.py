"""Nova MCP server — TaskFlow exposed as Model Context Protocol tools.

Transport is **stdio** by default: there is no socket and therefore no network surface — the
strongest possible posture for a Concierge-track agent handling personal data. (If an HTTP
transport is ever enabled, `data_guard.assert_local_host` forbids any non-loopback bind.)

Run standalone:  ``python -m nova.mcp.server``
Or register in an MCP client (Claude Desktop, ADK) pointing at that command.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .tools import NovaTools


def _eprint(*args) -> None:
    """Print to STDERR only. In stdio mode, stdout is the MCP protocol channel and must
    never carry human text — so all banners/logs go to stderr."""
    print(*args, file=sys.stderr, flush=True)


def build_server(data_dir: Optional[str] = None) -> FastMCP:
    """Construct the FastMCP app with all Nova tools bound to one data directory."""
    tools = NovaTools(data_dir or os.environ.get("TASKFLOW_DATA_PATH"))
    mcp = FastMCP("nova-taskflow")

    # ---- READ tools ----
    @mcp.tool()
    def get_tasks(status: str = "active", priority: Optional[str] = None,
                  tag: Optional[str] = None) -> list[dict]:
        """List TaskFlow tasks. status = active | completed | overdue | all."""
        return [t.model_dump() for t in tools.get_tasks(status, priority, tag)]

    @mcp.tool()
    def get_today_context() -> dict:
        """Where the user stands right now: prime target, scheduled-today, overdue total +
        ranked candidates, current load, and whether it's past TaskFlow's 6pm shift."""
        return tools.get_today_context().model_dump()

    @mcp.tool()
    def get_behavioral_stats() -> dict:
        """Real behavioral signal: completion rate, average postpone count, the tags that get
        postponed most, and how many deadlines have been moved. Computed from data, not guessed."""
        return tools.get_behavioral_stats().model_dump()

    @mcp.tool()
    def get_edit_history(task_id: Optional[int] = None, days: int = 7) -> list[dict]:
        """Append-only edit history — status changes, postpones, and the *reasons* the user
        gave when moving deadlines. This is the substrate for behavioral coaching."""
        return [e.model_dump() for e in tools.get_edit_history(task_id, days)]

    # ---- WRITE tools (validated + audited) ----
    @mcp.tool()
    def create_task(title: str, priority: str = "medium", tags: Optional[list[str]] = None,
                    deadline: Optional[str] = None, duration: Optional[str] = None,
                    notes: Optional[str] = None) -> dict:
        """Create a TaskFlow task. priority: critical/strategic/noise; duration:
        15m/30m/1h/2h/3h/4h+; deadline: ISO or natural language ('tomorrow 3pm')."""
        return tools.create_task(title, priority, tags, deadline, duration, notes).model_dump()

    @mcp.tool()
    def complete_task(task_id: int) -> bool:
        """Mark a task complete."""
        return tools.complete_task(task_id)

    @mcp.tool()
    def schedule_task(task_id: int, date: str) -> Optional[dict]:
        """Schedule a task for a date ('YYYY-MM-DD', 'today', or 'tomorrow')."""
        t = tools.schedule_task(task_id, date)
        return t.model_dump() if t else None

    @mcp.tool()
    def set_prime_target(task_id: int) -> bool:
        """Set today's single Prime Target (the One Frog Protocol — one per day)."""
        return tools.set_prime_target(task_id)

    return mcp


def _list_tool_summaries(srv: FastMCP):
    import asyncio

    try:
        tools = asyncio.run(srv.list_tools())
    except Exception:
        tools = srv._tool_manager.list_tools()
    return tools


def main(argv=None) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="nova-mcp",
        description="Nova MCP server — TaskFlow exposed as Model Context Protocol tools.",
    )
    parser.add_argument("--selftest", action="store_true",
                        help="List the registered tools and exit (no server, no client needed).")
    parser.add_argument("--data-dir", default=None, help="TaskFlow data dir (default: ~/.taskflow).")
    args = parser.parse_args(argv)

    srv = build_server(args.data_dir)

    if args.selftest:
        tools = _list_tool_summaries(srv)
        _eprint(f"Nova MCP server — {len(tools)} tools registered:")
        for t in tools:
            first_line = (t.description or "").strip().splitlines()[0] if t.description else ""
            _eprint(f"  - {t.name}: {first_line}")
        _eprint("\nSelf-test OK. To serve, run without --selftest and connect an MCP client.")
        return

    _eprint("Nova MCP server is listening on stdio.")
    _eprint("This is correct: it now waits for an MCP client (Claude Desktop / ADK) to connect.")
    _eprint("There is no network socket. Run with --selftest to just inspect tools. Ctrl+C to stop.")
    try:
        srv.run()  # stdio transport — no network surface
    except (KeyboardInterrupt, EOFError):
        _eprint("\nNova MCP server stopped.")


if __name__ == "__main__":
    main()
