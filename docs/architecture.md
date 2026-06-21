# Architecture

## The shape

```
nl request → Orchestrator (ADK router) → one specialist agent → NovaTools → TaskFlow data
                                                     │
                                          (the same NovaTools is also wrapped
                                           by the MCP server for external clients)
```

## Three deliberate seams

**1. Logic vs. transport.** `nova/mcp/tools.py::NovaTools` holds *all* capability logic and
returns typed Pydantic models. `nova/mcp/server.py` is a thin FastMCP wrapper; `agents/tools_adk.py`
is a thin ADK wrapper. One tested implementation, two front doors (MCP for external clients,
in-process for the agents). This is why the agents are reliable in a demo — they aren't talking to
a flaky subprocess, they're calling the exact code the MCP server exposes.

**2. Read vs. write.** `TaskFlowReader` (read-only, path-contained, dual-source) and
`TaskFlowWriter` (atomic temp+replace, in-process lock, append-only `edit_history`) are separate.
The Coach and Briefing agents receive only read tools; the Planner is the only agent given write
tools. Capability is enforced by composition, not by trusting the prompt.

**3. Derived vs. raw.** Tools return *derived* views (`TodayContext`, `BehavioralStats`) — counts,
patterns, ranked candidates. The agents reason over those; the raw files never need to leave the
machine.

## Data sourcing (the reader)

`TaskFlowReader` prefers TaskFlow's own loader (`task_manager.storage.load_tasks()`) when pointed
at the real `~/.taskflow` — true single source of truth, inheriting TaskFlow's schema handling and
corrupt-recovery. When pointed elsewhere (a CI runner with only synced JSON, or the committed
sample), it falls back to a schema-tolerant JSON parse. Same typed output either way.

## Computed fields

`is_overdue`, `duration_minutes`, and `priority_tier` mirror TaskFlow's server-side
`_computed_task_fields()` exactly, so Nova and TaskFlow never disagree about whether a task is
overdue or how long it is. Duration is TaskFlow's fixed enum (`15m/30m/1h/2h/3h/4h+`), not a free
integer.

## Behavioral derivations (the coach's evidence)

`get_behavioral_stats` and `get_edit_history` turn raw fields into signal: postpone-rate by tag,
completion rate, deadline-move count, and the *reasons* the user gave when moving deadlines (from
the append-only `edit_history`). The Coach agent is constrained to reason only over these — it
cannot invent a pattern that isn't in the data.

## Concurrency / integrity

Writes use atomic temp+replace (a crash mid-write can't tear the file) plus an in-process lock to
serialize Nova's own writes. This is the same guarantee TaskFlow itself relies on, which is what
makes it safe to run Nova alongside the TaskFlow CLI/UI.
