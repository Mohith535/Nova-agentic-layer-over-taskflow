"""Nova web console (FastAPI, localhost only).

The point of this UI is not "a chat box." It's to make it *visible* that Nova is an agent
reasoning over real behavioral data: the page shows the live signal it reads (the grounding
strip), the tools each agent actually calls, and the grounded response. That's the difference
between "looks like a chatbot" and "obviously a real agent over real data" — which is what a
human judge rewards.

No new data path: the endpoints use the same `NovaTools` as the CLI and MCP server. Binds to
127.0.0.1 only.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from ..config import data_dir, ensure_api_key
from ..mcp.tools import NovaTools

_STATIC = Path(__file__).resolve().parent / "static"


class AgentRequest(BaseModel):
    mode: str = "ask"  # ask | brief | plan | coach
    message: str = ""


def _capture(agent, message: str) -> tuple[str, list[str]]:
    """Run one agent turn; return (final_text, [tool names the agent actually called])."""
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    runner = InMemoryRunner(agent=agent, app_name="nova-web")
    created = runner.session_service.create_session(app_name="nova-web", user_id="local")
    if inspect.isawaitable(created):
        created = asyncio.run(created)
    content = types.Content(role="user", parts=[types.Part(text=message)])

    text_parts: list[str] = []
    tools_used: list[str] = []
    for event in runner.run(user_id="local", session_id=created.id, new_message=content):
        c = getattr(event, "content", None)
        if not c or not getattr(c, "parts", None):
            continue
        is_final = getattr(event, "is_final_response", lambda: False)()
        for part in c.parts:
            fc = getattr(part, "function_call", None)
            if fc and getattr(fc, "name", None):
                tools_used.append(fc.name)
            if is_final and getattr(part, "text", None):
                text_parts.append(part.text)
    # de-dupe tools, preserve order
    seen = set()
    ordered = [t for t in tools_used if not (t in seen or seen.add(t))]
    return "\n".join(text_parts).strip(), ordered


def build_app(dd: Optional[str] = None) -> FastAPI:
    app = FastAPI(title="Nova Console", docs_url=None, redoc_url=None)
    dd = dd or data_dir()
    tools = NovaTools(dd)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (_STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/api/context")
    def context():
        """Live grounding data — what Nova is looking at (no LLM, no key needed)."""
        return JSONResponse({
            "context": tools.get_today_context().model_dump(),
            "stats": tools.get_behavioral_stats().model_dump(),
        })

    @app.post("/api/agent")
    async def run_agent(req: AgentRequest):
        if not ensure_api_key():
            return JSONResponse(
                {"error": "no_api_key", "message": "Set GEMINI_API_KEY in .env to use the agents."},
                status_code=400,
            )
        mode = (req.mode or "ask").lower()
        msg = (req.message or "").strip()

        from ..agents.briefing_agent import build_briefing_agent
        from ..agents.coach_agent import build_coach_agent
        from ..agents.planning_agent import build_planning_agent
        from ..orchestrator import build_orchestrator

        if mode == "brief":
            agent, msg = build_briefing_agent(tools), (msg or "Give me my briefing for right now.")
        elif mode == "coach":
            agent, msg = build_coach_agent(tools), (msg or "What pattern should I fix? Be specific.")
        elif mode == "plan":
            if not msg:
                return JSONResponse({"error": "need_goal", "message": "Enter a goal to plan."}, status_code=400)
            agent = build_planning_agent(tools)
        else:
            agent, msg = build_orchestrator(dd), (msg or "What should I focus on right now?")

        try:
            text, tools_used = await run_in_threadpool(_capture, agent, msg)
        except Exception as e:
            return JSONResponse({"error": "run_failed", "message": str(e)}, status_code=500)
        return JSONResponse({"response": text or "(no response)", "tools_used": tools_used, "mode": mode})

    return app


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    from ..security.data_guard import assert_local_host

    assert_local_host(host)  # refuse any non-loopback bind
    print(f"Nova console -> http://{host}:{port}  (Ctrl+C to stop)", flush=True)
    uvicorn.run(build_app(), host=host, port=port, log_level="warning")
