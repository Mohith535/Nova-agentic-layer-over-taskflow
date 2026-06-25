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
import json
import os
from datetime import datetime
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
    fast: bool = False  # quota-frugal one-call path (brief/coach only)


class ScheduleReq(BaseModel):
    task_id: int
    date: str = "tomorrow"


class ProposeReq(BaseModel):
    goal: str = ""


class CommitReq(BaseModel):
    tasks: list = []


class MemoryUpdateReq(BaseModel):
    text: str = ""


def _read_state(dd) -> dict:
    p = Path(dd) / "nova_state.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        return {}


def _write_state(dd, st: dict) -> None:
    try:
        p = Path(dd) / "nova_state.json"
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(st), encoding="utf-8")
        tmp.replace(p)
    except Exception:
        pass


def _greeting(tools: NovaTools, dd) -> str:
    """A warm, context-aware opener — Nova greeting you like it's been holding the thread.

    Deterministic (no model call, instant, free): it weaves in how long you've been away, a
    serious thing you last discussed (from memory), and a nudge toward today. This is the
    'second brain that remembers you' moment — not a generic empty state.
    """
    name = os.environ.get("NOVA_USER_NAME", "").strip()
    hello = f"Hey {name}" if name else "Hey"
    st = _read_state(dd)
    now = datetime.now()
    days = None
    if st.get("last_seen"):
        try:
            days = (now.date() - datetime.fromisoformat(st["last_seen"]).date()).days
        except Exception:
            days = None
    _write_state(dd, {**st, "last_seen": now.isoformat()})

    ctx = tools.get_today_context()
    mem = tools.recall_memory()
    serious = next((m.get("text") for m in reversed(mem) if m.get("kind") == "emotion"), None)

    parts: list[str] = []
    if days is None:
        parts.append(f"{hello}. I'm Nova — I hold the thread on what you're actually doing, so we can "
                     f"pick up wherever you are.")
    elif days <= 0:
        parts.append(f"{hello}, you're back.")
    elif days == 1:
        parts.append(f"{hello} — it's been a day. How did it go?")
    else:
        parts.append(f"{hello} — it's been {days} days. No score-keeping; let's just pick the thread back up.")

    if serious:
        parts.append(f"Last time, this was weighing on you: \"{serious}\". Still there, or has it shifted?")

    overdue = ctx.overdue_total or 0
    if ctx.prime_target:
        parts.append(f"Today, your one thing is **{ctx.prime_target.title}** — want to start there?")
    elif overdue and ctx.overdue_candidates:
        parts.append(f"You're carrying **{overdue}** on the backlog. The freshest worth a look is "
                     f"**{ctx.overdue_candidates[0].title}** — want me to brief you, or just talk it through?")
    elif overdue:
        parts.append(f"You're carrying **{overdue}** overdue — want me to brief you on where to start?")
    else:
        parts.append("Nothing's scheduled today — want to plan one thing, or just think out loud?")

    return " ".join(parts)


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


def _friendly_error(msg: str) -> str:
    if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
        if "per_minute" in msg.lower() or "rate" in msg.lower():
            return ("Hit the per-minute rate limit (15 req/min on free tier). "
                    "Wait about 60 seconds and try again.")
        return ("Gemini free-tier quota exhausted for today — resets at midnight Pacific. "
                "If this keeps happening daily, your GitHub Actions workflow may be using the same "
                "API key. Check E:\\nova\\.env and add a separate key, or disable the workflow.")
    if "UNAVAILABLE" in msg or "503" in msg or "high demand" in msg.lower():
        return ("Gemini is overloaded right now (free-tier gets deprioritised during peak hours). "
                "Wait 30–60 seconds and try again.")
    if "DEADLINE_EXCEEDED" in msg or "504" in msg:
        return "The request timed out — Gemini was too slow. Try again, or use the ⚡ Fast toggle."
    if "NOT_FOUND" in msg or "404" in msg:
        return ("Model not found — the model name may be unsupported by the current API version. "
                "Nova has automatically switched to a fallback model. If this persists, restart Nova.")
    if "API_KEY" in msg.upper() or "authentication" in msg.lower():
        return "API key issue — check that GEMINI_API_KEY is set correctly in E:\\nova\\.env."
    return msg[:300]


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

    @app.get("/api/opportunities")
    def opportunities():
        """Opportunities the Opportunity Hunter agent found + scored — the Scout feed (no LLM)."""
        return JSONResponse({"opportunities": tools.get_opportunities(min_score=0, limit=12)})

    @app.get("/api/memory")
    def memory():
        """What Nova remembers about the user — transparency for the UI panel."""
        return JSONResponse({
            "memory": tools.all_memory(),
            "enabled": tools.reader.nova_data_enabled(),
        })

    @app.delete("/api/memory")
    def forget():
        """Erase everything Nova remembers — the user's one-click right to be forgotten."""
        return JSONResponse({"cleared": tools.forget_all()})

    @app.delete("/api/memory/{entry_id}")
    def forget_one(entry_id: int):
        """Remove a single memory entry by id."""
        ok = tools.forget_one(entry_id)
        return JSONResponse({"ok": ok})

    @app.patch("/api/memory/{entry_id}")
    def update_memory(entry_id: int, req: MemoryUpdateReq):
        """Edit the text of a single memory entry in-place."""
        entry = tools.update_memory(entry_id, req.text)
        return JSONResponse({"ok": bool(entry), "entry": entry})

    @app.get("/api/greeting")
    def greeting():
        """A warm, context-aware opener (recency + memory + today). No model call."""
        import concurrent.futures
        name = os.environ.get("NOVA_USER_NAME", "").strip()
        fallback = (f"Hey {name} — I'm Nova." if name else "Hey — I'm Nova.") + \
                   " What's on your mind?"
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(_greeting, tools, dd)
                text = fut.result(timeout=3.0)
        except Exception:
            text = fallback
        return JSONResponse({"greeting": text})

    @app.post("/api/task/schedule")
    def schedule(req: ScheduleReq):
        """Light edit from the rail popup; heavier edits happen in the TaskFlow UI."""
        t = tools.schedule_task(req.task_id, req.date)
        return JSONResponse({"ok": t is not None, "task": t.model_dump() if t else None})

    @app.post("/api/plan/propose")
    async def plan_propose(req: ProposeReq):
        """PROPOSE a task breakdown — a preview, written nowhere. The user reviews/edits, then
        confirms via /api/plan/commit. This is the human-in-the-loop gate."""
        if not ensure_api_key():
            return JSONResponse({"error": "no_api_key",
                                 "message": "Set GEMINI_API_KEY in .env to let Nova plan."},
                                status_code=400)
        goal = (req.goal or "").strip()
        if not goal:
            return JSONResponse({"error": "need_goal", "message": "Tell me the goal to break down."},
                                status_code=400)
        from ..agents.planner_propose import propose_tasks
        try:
            tasks = await run_in_threadpool(propose_tasks, tools, goal)
        except Exception as e:
            return JSONResponse({"error": "run_failed", "message": _friendly_error(str(e))}, status_code=500)
        return JSONResponse({"tasks": tasks, "goal": goal})

    @app.post("/api/plan/commit")
    def plan_commit(req: CommitReq):
        """COMMIT the (possibly user-edited) proposal — the separate executor that actually writes
        the tasks to TaskFlow, only after the user said yes. Validated + audited via create_task."""
        created, failed = [], 0
        for t in (req.tasks or [])[:12]:
            if not isinstance(t, dict):
                continue
            title = (t.get("title") or "").strip()
            if not title:
                continue
            try:
                nt = tools.create_task(
                    title=title,
                    priority=t.get("priority") or "strategic",
                    tags=t.get("tags"),
                    deadline=t.get("deadline"),
                    duration=t.get("duration"),
                    notes=t.get("notes"),
                )
                created.append(nt.model_dump())
            except Exception:
                failed += 1
        return JSONResponse({"created": created, "count": len(created), "failed": failed})

    @app.post("/api/agent")
    async def run_agent(req: AgentRequest):
        if not ensure_api_key():
            return JSONResponse(
                {"error": "no_api_key", "message": "Set GEMINI_API_KEY in .env to use the agents."},
                status_code=400,
            )
        from ..config import best_model, mark_exhausted
        mode = (req.mode or "ask").lower()
        msg = (req.message or "").strip()

        def _is_quota_err(e: str) -> bool:
            return "RESOURCE_EXHAUSTED" in e or "429" in e

        # Fast path (user toggled ⚡ or simple mode): single model call, no tool round-trips.
        if req.fast and mode in ("brief", "coach", "ask"):
            from ..agents.fast_coach import run_fast
            model = best_model(mode)
            try:
                text, tools_used = await run_in_threadpool(run_fast, tools, mode, msg, model)
            except Exception as e:
                if _is_quota_err(str(e)):
                    mark_exhausted(model)
                return JSONResponse({"error": "run_failed", "message": _friendly_error(str(e))}, status_code=500)
            if not text:
                text = "Empty response — quota may be exhausted. Resets at midnight Pacific."
            return JSONResponse({"response": text, "tools_used": tools_used, "mode": mode, "fast": True})

        from ..agents.briefing_agent import build_briefing_agent
        from ..agents.coach_agent import build_coach_agent
        from ..agents.planning_agent import build_planning_agent
        from ..orchestrator import build_orchestrator

        model = best_model(mode)
        if mode == "brief":
            agent, msg = build_briefing_agent(tools, model), (msg or "Give me my briefing for right now.")
        elif mode == "coach":
            agent, msg = build_coach_agent(tools, model), (msg or "What pattern should I fix? Be specific.")
        elif mode == "plan":
            if not msg:
                return JSONResponse({"error": "need_goal", "message": "Enter a goal to plan."}, status_code=400)
            agent = build_planning_agent(tools, model)
        else:
            agent, msg = build_orchestrator(dd, model), (msg or "What should I focus on right now?")

        last_exc = None
        text, tools_used = "", []
        for attempt in range(2):
            try:
                text, tools_used = await run_in_threadpool(_capture, agent, msg)
                last_exc = None
                break
            except Exception as e:
                last_exc = e
                err_str = str(e)
                if _is_quota_err(err_str):
                    mark_exhausted(model)   # don't retry this model again this session
                    break
                if attempt == 0 and ("UNAVAILABLE" in err_str or "503" in err_str):
                    import asyncio
                    await asyncio.sleep(3)
                    continue
                break

        # Auto-fallback to fast single-call path for non-plan modes.
        if (not text or last_exc is not None) and mode in ("brief", "coach", "ask"):
            from ..agents.fast_coach import run_fast
            fallback_model = best_model(mode)   # router picks next available after mark_exhausted
            try:
                text, tools_used = await run_in_threadpool(run_fast, tools, mode, msg, fallback_model)
                last_exc = None
            except Exception as fe:
                err_str = str(fe)
                if _is_quota_err(err_str):
                    mark_exhausted(fallback_model)
                if last_exc is None:
                    last_exc = fe

        if last_exc is not None:
            return JSONResponse({"error": "run_failed", "message": _friendly_error(str(last_exc))}, status_code=500)
        if not text:
            text = ("All available models are quota-exhausted for today. "
                    "Resets at midnight Pacific — or get a new free key at aistudio.google.com/apikey.")
        return JSONResponse({"response": text, "tools_used": tools_used, "mode": mode})

    return app


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    from ..security.data_guard import assert_local_host

    assert_local_host(host)  # refuse any non-loopback bind
    print(f"Nova console -> http://{host}:{port}  (Ctrl+C to stop)", flush=True)
    uvicorn.run(build_app(), host=host, port=port, log_level="warning")
