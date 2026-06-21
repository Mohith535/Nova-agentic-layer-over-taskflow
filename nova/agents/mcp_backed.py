"""MCP-in-the-loop: give an ADK agent its tools from the *live* Nova MCP server.

This is what makes the MCP server load-bearing rather than decorative. When an agent is built
with ``use_mcp=True``, its tools are not the in-process Python functions — they are discovered
from a freshly spawned ``python -m nova.mcp.server`` subprocess over stdio, exactly as an
external MCP client (Claude Desktop, another ADK app) would consume them.

Least privilege is preserved *over the wire*: each agent gets a `tool_filter` so the Coach and
Briefing agents can only ever see the read-only tools, even through MCP.

The in-process path (`tools_adk.py`) remains the reliable default; this is the mode you switch
on with `nova ... --mcp` to demonstrate (and stress-test) the real MCP transport.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

READ_ONLY_TOOLS = ["get_today_context", "get_tasks", "get_behavioral_stats", "get_edit_history", "recall_memory"]
WRITE_TOOLS = ["create_task", "complete_task", "schedule_task", "set_prime_target"]
# Memory is a separate, low-stakes capability: writing a note about the user can never mutate
# their tasks. Kept distinct from WRITE_TOOLS so the read-only/task-write split stays clean.
MEMORY_TOOLS = ["remember"]


def mcp_toolset(data_dir: Optional[str] = None, tool_names: Optional[list[str]] = None,
                timeout: float = 30.0) -> McpToolset:
    """An ADK toolset backed by a live `python -m nova.mcp.server` stdio subprocess.

    `tool_names` filters which tools the agent may see (least privilege over MCP).
    `data_dir` is forwarded to the server subprocess as TASKFLOW_DATA_PATH.
    """
    env = {**os.environ}
    if data_dir:
        env["TASKFLOW_DATA_PATH"] = data_dir
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,            # the same interpreter — nova is importable here
                args=["-m", "nova.mcp.server"],
                env=env,
            ),
            timeout=timeout,
        ),
        tool_filter=tool_names,                    # None = all tools
    )
