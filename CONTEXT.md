# CONTEXT.md — for Antigravity / build agents

**Project:** Nova — a multi-agent productivity intelligence layer for the Kaggle × Google AI
Agents Capstone 2026 (Concierge Agents track).

**Foundation:** [TaskFlow v9.1.0](https://github.com/Mohith535/TaskFlow) — a shipped, offline,
behavioral task manager. Its data lives in `~/.taskflow/` (tasks with priority, deadlines,
postpone counts, focus history, and an append-only `edit_history` that records *why* the user
moved each deadline). Nova reads that real dataset; it does not invent behavior.

**What Nova adds:** an ADK orchestrator routing to three agents (briefing, planning, coach), an
MCP server exposing TaskFlow as 8 typed tools, a security layer (validation, audit, local-first),
and a daily-brief GitHub Action.

**The hook:** *Every productivity app tells you what you should do. Nova is the first agent that
knows why you keep avoiding it — and fixes that.*

**Tone everywhere:** behavioral, precise, judgment-free. Name the mechanism, not the person. No
cheerleading, no emoji. See `AGENTS.md` for the full rules and `README.md` for the architecture.

**Tech:** Python 3.11+, `google-adk` 2.x, `mcp` (FastMCP), `google-generativeai`, `pydantic` v2.
Free tier only (`gemini-2.5-flash`). Build/demo in Antigravity with a Claude model selected.
