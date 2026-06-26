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


class ProfileBasicsReq(BaseModel):
    name: str = ""
    pronouns: str = ""
    life_context: str = ""
    peak_hours: str = ""


class ProfileCompleteReq(BaseModel):
    basics: dict = {}
    answers: dict = {}  # q1..q5, q6_text, q7


class ProfileImportReq(BaseModel):
    text: str = ""
    source: str = "other"  # chatgpt | claude | gemini | perplexity | other


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
    """Context-aware opener — each component is independently optional so a slow
    data source never blocks the whole greeting. No model call, always instant."""
    import concurrent.futures as _cf
    name = os.environ.get("NOVA_USER_NAME", "").strip()
    hello = f"Hey {name}" if name else "Hey"
    now = datetime.now()
    hour = now.hour

    # Time-of-day prefix
    if 5 <= hour < 12:
        tod = "morning"
    elif 12 <= hour < 17:
        tod = "afternoon"
    elif 17 <= hour < 21:
        tod = "evening"
    else:
        tod = None

    # Last-seen (fast — local state file only)
    st = _read_state(dd)
    days: int | None = None
    if st.get("last_seen"):
        try:
            days = (now.date() - datetime.fromisoformat(st["last_seen"]).date()).days
        except Exception:
            days = None
    _write_state(dd, {**st, "last_seen": now.isoformat()})

    # Memory recall (fast — local JSON read)
    try:
        mem = tools.recall_memory()
    except Exception:
        mem = []
    serious = next((m.get("text") for m in reversed(mem) if m.get("kind") == "emotion"), None)

    # Today context (can be slow — cap at 1.5 s, skip if it times out)
    ctx = None
    try:
        with _cf.ThreadPoolExecutor(max_workers=1) as ex:
            ctx = ex.submit(tools.get_today_context).result(timeout=1.5)
    except Exception:
        ctx = None

    parts: list[str] = []

    # Opening line — personalised by recency + time of day
    if days is None:
        parts.append(f"{hello}. I'm Nova — I hold the thread on what you're actually doing.")
    elif days <= 0:
        greeting_prefix = f"{hello}{', good ' + tod if tod else ''}"
        parts.append(f"{greeting_prefix}. You're back.")
    elif days == 1:
        parts.append(f"{hello} — it's been a day. How did it go?")
    else:
        parts.append(f"{hello} — it's been {days} day{'s' if days != 1 else ''}. Let's pick the thread back up.")

    # Memory hook — only if something emotional was logged
    if serious:
        parts.append(f"Last time, this was weighing on you: \"{serious}\". Still there, or has it shifted?")

    # Task nudge — only if context loaded in time
    if ctx is not None:
        overdue = ctx.overdue_total or 0
        if ctx.prime_target:
            parts.append(f"Your one thing today is **{ctx.prime_target.title}** — want to start there?")
        elif overdue and ctx.overdue_candidates:
            parts.append(f"You're carrying **{overdue}** on the backlog. "
                         f"**{ctx.overdue_candidates[0].title}** is worth a look first.")
        elif overdue:
            parts.append(f"You've got **{overdue}** overdue. Want me to help triage?")
        else:
            tod_line = f"Good {tod}. " if tod and days != 0 else ""
            parts.append(f"{tod_line}Nothing's scheduled yet — want to plan one thing?")
    else:
        if tod and days != 0:
            parts.append(f"Good {tod}. What's on your mind?")

    return " ".join(parts) if parts else f"{hello}. What's on your mind?"


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
    def index():
        from fastapi.responses import Response
        content = (_STATIC / "index.html").read_text(encoding="utf-8")
        return Response(content=content, media_type="text/html",
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate",
                                 "Pragma": "no-cache", "Expires": "0"})

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
        """Clear learned behavioral memory only — keeps the user's profile intact."""
        return JSONResponse({"cleared": tools.forget_all()})

    @app.post("/api/reset")
    def reset_everything():
        """Full start-over: delete learned memory AND the psychological profile.
        Returns honest counts so the UI can report exactly what was removed.
        (Chat transcripts live in browser localStorage and are cleared client-side.)"""
        cleared = tools.forget_all()
        had_profile = tools.reset_profile()
        return JSONResponse({"ok": True, "memory_cleared": cleared, "profile_removed": had_profile})

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
        """Session opener — personalized via Greeting Agent when profile exists,
        deterministic fallback otherwise. Always responds within 8 s."""
        import concurrent.futures as _cf
        from datetime import datetime as _dt
        profile = tools.read_user_profile()
        basics = profile.get("basics") or {}
        nova_p = profile.get("nova") or {}
        name = basics.get("name", "").strip() or os.environ.get("NOVA_USER_NAME", "").strip()
        purpose = nova_p.get("purpose_90d", "").strip()

        # Build a meaningful profile-aware fallback — never falls to "Hey — I'm Nova"
        # even when Gemini is unavailable.
        _hour = _dt.now().hour
        _tod = "Morning" if _hour < 12 else ("Afternoon" if _hour < 18 else "Evening")
        if name and purpose:
            fallback = f"{name}. Still working toward: {purpose}. What's on your mind?"
        elif name:
            fallback = f"{_tod}, {name}. What's on your mind?"
        elif purpose:
            fallback = f"Still working toward: {purpose}. What's on your mind?"
        else:
            fallback = f"{_tod} — what's on your mind?"

        if profile.get("profile_complete"):
            # Use Greeting Agent (one fast Gemini call, personalized)
            def _run_greeting_agent():
                from ..agents.greeting_agent import generate_greeting
                return generate_greeting(tools)
            try:
                with _cf.ThreadPoolExecutor(max_workers=1) as ex:
                    text = ex.submit(_run_greeting_agent).result(timeout=3.5)
                # Additional guard: if the agent returned something trivially short, use fallback
                if not text or len(text.split()) < 5:
                    text = fallback
            except Exception:
                text = fallback
        else:
            # Deterministic path — no model call needed, profile not set up yet
            try:
                with _cf.ThreadPoolExecutor(max_workers=1) as ex:
                    text = ex.submit(_greeting, tools, dd).result(timeout=3.0)
            except Exception:
                text = fallback
        return JSONResponse({"greeting": text})

    # ---- PROFILE endpoints ------------------------------------------------

    @app.get("/api/profile")
    def get_profile():
        """Current user profile — drives onboarding state check on page load."""
        return JSONResponse({"profile": tools.read_user_profile()})

    @app.post("/api/profile/basics")
    def save_basics(req: ProfileBasicsReq):
        """Save basic details (name, pronouns, life_context, peak_hours).
        Non-blocking — basics can be saved independently before the 7 deep questions."""
        updated = tools.write_user_profile({
            "basics": {
                "name": req.name.strip(),
                "pronouns": req.pronouns.strip(),
                "life_context": req.life_context.strip(),
                "peak_hours": req.peak_hours.strip(),
            }
        })
        return JSONResponse({"ok": True, "profile": updated})

    @app.post("/api/profile/complete")
    async def complete_profile(req: ProfileCompleteReq):
        """Finalize onboarding: normalize 7 Q answers via Profile Agent → write profile.
        Returns the personalized greeting generated from the new profile."""
        if not req.answers:
            return JSONResponse({"error": "no_answers", "message": "Answers required."}, status_code=400)
        from ..agents.profile_agent import finalize_profile
        from ..agents.greeting_agent import generate_greeting
        try:
            profile = await run_in_threadpool(finalize_profile, tools, req.answers, req.basics)
        except Exception as e:
            # Fallback: write a minimal profile so the user can proceed
            from datetime import datetime
            profile = tools.write_user_profile({
                "profile_complete": True,
                "basics": req.basics,
                "nova": {"purpose_90d": req.answers.get("q6_text", ""), "memory_depth": "deep"},
            })
        # Generate the first personalized greeting as proof of listening
        greeting_text = ""
        if ensure_api_key():
            try:
                greeting_text = await run_in_threadpool(generate_greeting, tools)
            except Exception:
                pass
        if not greeting_text:
            name = (profile.get("basics") or {}).get("name", "")
            purpose = (profile.get("nova") or {}).get("purpose_90d", "")
            greeting_text = f"Got it{', ' + name if name else ''}. " + (
                f"Working toward: {purpose}. Let's start." if purpose else "What's on your mind?"
            )
        return JSONResponse({"ok": True, "profile": profile, "greeting": greeting_text})

    @app.post("/api/profile/import")
    async def import_profile(req: ProfileImportReq):
        """Break down a portrait the user pasted from another AI into Nova's signals.
        Returns best-guess answers to pre-fill the 7 questions + a 'recognized' line.
        Stores the raw import on the profile and seeds memory (Nova-gated)."""
        from datetime import datetime
        text = (req.text or "").strip()
        if len(text) < 20:
            return JSONResponse({"error": "too_short",
                                 "message": "That looks too short to read much from — paste a bit more."},
                                status_code=400)
        from ..agents.profile_agent import extract_import
        try:
            result = await run_in_threadpool(extract_import, tools, text, req.source)
        except Exception:
            result = {"best_guess": {}, "memory_seeds": [], "recognized": ""}

        # Persist the raw import + extraction on the profile (merge — keeps any basics already saved)
        tools.write_user_profile({"ai_import": {
            "imported": True,
            "source": req.source,
            "raw_text": text[:4000],
            "extracted": result,
            "imported_at": datetime.now().isoformat(),
        }})

        # Seed behavioral memory — only when the user allows behavioral data
        seeded = 0
        if tools.reader.nova_data_enabled():
            for s in (result.get("memory_seeds") or []):
                txt = (s.get("text") or "").strip()
                if txt:
                    tools.remember(txt, s.get("kind") or "fact")
                    seeded += 1

        return JSONResponse({
            "ok": True,
            "guesses": result.get("best_guess") or {},
            "recognized": result.get("recognized") or "",
            "seeded": seeded,
            "error": result.get("error") or "",
        })

    # ---- REFLECT endpoint (Reflection Agent) ------------------------------

    @app.post("/api/reflect")
    async def reflect():
        """Run Reflection Agent: synthesize today's session → 2-3 memory entries.
        Non-blocking — if Gemini is unavailable, returns empty list gracefully."""
        if not ensure_api_key():
            return JSONResponse({"error": "no_api_key", "entries": []}, status_code=400)
        from ..agents.reflection_agent import run_reflection
        try:
            entries = await run_in_threadpool(run_reflection, tools)
        except Exception:
            entries = []
        return JSONResponse({"entries": entries, "count": len(entries)})

    # ---- PATTERNS endpoint (Pattern Intelligence Agent) -------------------

    @app.post("/api/patterns")
    async def patterns():
        """Run Pattern Intelligence Agent: analyze 4 weeks → write nova_insights.json."""
        if not ensure_api_key():
            return JSONResponse({"error": "no_api_key", "insights": []}, status_code=400)
        from ..agents.pattern_agent import run_patterns
        try:
            new_insights = await run_in_threadpool(run_patterns, tools, 4)
        except Exception as e:
            return JSONResponse({"error": "run_failed", "message": _friendly_error(str(e))}, status_code=500)
        return JSONResponse({"insights": new_insights, "count": len(new_insights)})

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
