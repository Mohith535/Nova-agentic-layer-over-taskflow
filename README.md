<div align="center">

# 🧠 Nova — the TaskFlow Intelligence Layer

### Kaggle × Google · AI Agents Capstone 2026 · Concierge Agents track

**Every productivity app tells you what you *should* do.**
**Nova is the first agent that knows *why* you keep avoiding it — and fixes that.**

</div>

---

## The story (three sentences)

[TaskFlow v9.1.0](https://github.com/Mohith535/TaskFlow) is a shipped, 100%-offline behavioral
task manager that has been quietly recording *how you actually work* — what you postpone, the
reasons you give when a deadline slips, how long tasks really take. **Nova is its brain.** It
reads that real behavioral dataset through an MCP server and routes your request to one of three
specialized ADK agents — so the coaching is grounded in your data, not invented by a model.

> TaskFlow gave you the execution engine. Nova gives it a brain.

---

## Architecture

```
            You (natural language)
                     │
        ┌────────────▼─────────────┐
        │     Nova Orchestrator     │   ADK root agent — routes by intent,
        │   (least-privilege router)│   transfers to exactly one specialist
        └────┬──────────┬───────────┘
             │          │           │
        ┌────▼───┐ ┌────▼────┐ ┌────▼────┐
        │Briefing│ │Planning │ │ Coach   │
        │read-only│ │ +write  │ │read-only│
        └────┬───┘ └────┬────┘ └────┬────┘
             └──────────┴───────────┘
                        │  (same validated tools, two front doors)
              ┌─────────▼──────────┐
              │  TaskFlow MCP server │  stdio · no network surface
              │  reads/writes        │  path-contained · audited
              │  ~/.taskflow/        │
              └─────────────────────┘
```

## Why agents — and why *three*?

A single LLM with a pile of tools would have been simpler. Three agents behind a router is the
right call for three concrete reasons:

1. **Least privilege.** The Coach and Briefing agents are **read-only**; only the Planner can
   write. A "why do I keep failing?" request can therefore *never* mutate your data — the
   capability isn't even on the table.
2. **Distinct voice.** The Coach's "name the mechanism, no cheerleading" instruction and the
   Planner's "respect current load, size up not down" discipline are different jobs that degrade
   when blended into one prompt.
3. **Distinct cadence.** Briefing runs unattended (the daily GitHub Action); the others run on
   demand. Separating them lets each boundary be reasoned about — and scheduled — independently.

## The three agents

| Agent | Answers | Reads | Writes |
|---|---|---|---|
| **Briefing** | "What do I do right now?" | live load, prime target, overdue candidates, time of day | — |
| **Planning** | "Turn this goal into tasks" | current load (so it doesn't bury you) | creates tasks |
| **Coach** | "Why do I keep avoiding this?" | postpone patterns, deadline-change reasons, completion rate | — |

The Coach is the heart. It speaks like a colleague who has read the research: **(1)** the pattern
with the number, **(2)** the psychological mechanism it matches, **(3)** one concrete change.
Never "you've got this." On the sample data it would say something like:

> *"Your #course tasks are postponed 4× on average and your completion rate sits at 0.2 — that's
> not a discipline gap, it's the signature of tasks too big to start. Split the next one to a
> 15-minute first step and schedule only that. Starting is the part that's actually hard."*

## MCP server

TaskFlow is exposed as a Model Context Protocol server (`nova/mcp/server.py`). It speaks over
**stdio** — there is no socket, so there is no network surface to attack, the strongest posture
for a tool handling personal data. Eight typed tools:

- **Read:** `get_today_context`, `get_tasks`, `get_behavioral_stats`, `get_edit_history`
- **Write (validated + audited):** `create_task`, `complete_task`, `schedule_task`, `set_prime_target`

The agents call the *same* tool implementations two ways: **in-process** (the reliable default)
or, with `--mcp`, **through this live server** — `nova ask --mcp` spawns `python -m nova.mcp.server`
and the agents discover their tools over stdio, exactly as an external client would. The
read-only/write split is enforced **per agent even over MCP** (the Coach literally cannot see the
write tools). That makes the MCP server load-bearing, not decorative.

```bash
python -m nova.mcp.server --selftest    # list the tools, no client needed
python -m nova.mcp.server               # serve over stdio to any MCP client (Claude Desktop, ADK)
nova ask --mcp "what should I do now?"  # the agents pull tools from the live server
```

## Security

This is a Concierge track — security is a scored criterion, so it's enforced, not claimed:

- **No network surface.** MCP over stdio = no socket. (If HTTP is ever enabled, the server
  refuses any non-loopback bind.)
- **Path containment.** Every file read/write is resolved and verified to stay inside the
  TaskFlow data directory (`realpath` + `commonpath`) — path traversal is blocked.
- **Honest LLM boundary.** TaskFlow's files never leave the machine. The agents send only the
  *derived* context they need to the model, gated by TaskFlow's `nova_data_enabled` consent
  toggle. Want zero cloud calls? Set `NOVA_MODEL_BACKEND=local` for an Ollama backend.
- **Audit trail.** Every write is appended to a local `nova_audit.log`.
- **Fail-closed validation.** All write inputs are sanitized and routed through TaskFlow's own
  normalizers, so nothing invalid can enter the dataset.
- **No secrets in code.** The Gemini key comes from the environment / `.env` (gitignored);
  `.env.example` is the template.

Nova extends the security work already shipped in TaskFlow v9.0.0 (CSRF + Host validation, CSP,
output escaping, path-traversal containment, the verified-offline promise).

## Agent Skills

The open Agent Skills standard is implemented at
[`.agents/skills/nova/SKILL.md`](.agents/skills/nova/SKILL.md) (mirrored to `.claude/` and
`.antigravitycli/`). It declares when to invoke Nova, the three agents, the MCP tools, the voice,
and the security model.

## Quick start

```bash
git clone <this-repo> nova && cd nova
python -m venv .venv && .venv\Scripts\activate      # Windows  (source .venv/bin/activate on *nix)
pip install -e .                                     # + pip install -e <taskflow> to read real data
copy .env.example .env                               # then add your free Gemini key

nova mcp --selftest          # works with no key — lists the 8 MCP tools
nova brief                   # today's mission briefing from your data
nova plan "prepare for the Microsoft Explore interview"
nova coach                   # behavioral patterns + one concrete change
nova ask "what should I focus on this morning?"      # router picks the agent
```

A free Gemini key (1500 req/day): <https://aistudio.google.com/apikey>.

## Deployment

[`.github/workflows/nova-daily-brief.yml`](.github/workflows/nova-daily-brief.yml) runs the
read-only Briefing agent every morning (08:00 IST) and writes the brief into the run summary. It
uses a committed, sanitized sample dataset by default, so it goes green without exposing real data
— add a `GEMINI_API_KEY` secret to enable it, and optionally a `TASKFLOW_TASKS_JSON` secret to
brief on your real tasks. Trigger it manually (`workflow_dispatch`) for the demo.

## Competition track: Concierge Agents

Nova is a concierge for your own commitments: it plans, briefs, and coaches over **your** data,
keeps that data **on your machine**, and is accountable for every change it makes. It hits all six
capstone concepts — multi-agent ADK system, an MCP server, Agent Skills, explicit security,
GitHub-Actions deployability, and a build in Antigravity — on a foundation that is a *real shipped
product*, not a demo.

---

<div align="center"><sub>Built on TaskFlow v9.1.0 · MIT · K Mohith Kannan</sub></div>
