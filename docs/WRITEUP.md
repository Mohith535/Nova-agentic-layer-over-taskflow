# Nova — the agent that knows *why* you keep avoiding it

**Subtitle:** A privacy-first, multi-agent concierge built on a shipped behavioral task manager — it reads how you *actually* work and tells you what to do about it.
**Track:** Concierge Agents
**Code:** https://github.com/Mohith535/Nova-agentic-layer-over-taskflow ·
**Foundation:** https://github.com/Mohith535/TaskFlow (v9.1.0)

> *Draft for the 2,500-word Kaggle writeup. Paste into the Kaggle Writeup editor; attach the cover image + the YouTube video in the Media Gallery before submitting.*

---

## The problem: the gap isn't writing tasks down — it's doing them

Every productivity app is a better place to *write down* what you should do. None of them know *why you don't do it.* You've known for two weeks that you should start the interview prep. The gap isn't information — it's behavior. And behavior leaves a trail: which tasks you postpone, *how many times*, the small reason you mutter when you push a deadline, how long a task really takes versus what you guessed. No tool reads that trail back to you. Meanwhile every AI assistant bolted onto a to-do app gives the same hollow advice — *"break it into smaller steps!"* — because it only knows what you **typed**, never what you actually **did**.

That trail is the fingerprint of *why a specific person* stalls: the planning fallacy, decision fatigue, a task too large to start, a Zeigarnik open loop. Nova's whole thesis: **turn the behavioral exhaust of task management into specific, honest coaching** — without becoming one more app that nags you, or one that ships your private life to a server.

## Why this is a Concierge problem

The data that makes Nova useful is intensely personal — your avoidance patterns, the emotional weight you've named around certain work, your 90-day ambitions. A system holding that is only acceptable if the knowledge stays *yours*. That constraint shaped the architecture from the first line, not as a track requirement bolted on later: task data never leaves the machine, memory is consent-gated and one-click erasable, and the only outbound call is to the language model — with *derived* context, never your raw files. Security here is enforced, not claimed.

## Why an agent — and why several

This isn't a script. The input is a fuzzy human goal ("prepare for the Microsoft Explore interview") or a fuzzy question ("why do I keep avoiding this?"), and the right response depends on messy, evolving personal data. That's an agent's job: *reason over tools and data, decide what to fetch, and act* — while refusing to do things it shouldn't. Nova is deliberately **multi-agent**, for three concrete reasons:

1. **Least privilege.** The Coach and Briefing agents are **read-only** — they literally cannot see a write tool, so a "why am I failing?" request can *never* mutate your board. Only the Planner writes, and only after you confirm.
2. **Distinct voice per discipline.** The Coach's "name the mechanism, no cheerleading" instruction and the Planner's "respect the load, size up not down" discipline are different jobs that degrade when fused into one prompt.
3. **A loop that compounds.** The Pattern agent writes weekly insights; the Coach reads them. The Reflection agent writes memory at session end; the Greeting agent reads it to open tomorrow. The system sharpens with use.

## The foundation: a real product, not a demo

Nova sits on **TaskFlow v9.1.0** — a shipped, 100%-offline behavioral task manager I built first. It already records, per task: priority, soft/hard deadlines, duration estimates vs. actual focus time, postpone counts, and — crucially — an **append-only `edit_history`** that captures *the reason the user gave when they moved a deadline* ("I haven't been able to start it yet", "ran out of evening again"). That field is the difference between coaching that's invented and coaching that's **true**. Nova doesn't guess your patterns; it reads them.

## What Nova does

- **Cites evidence, not vibes.** *"Your #study tasks are postponed 4× on average with a 0.2 completion rate — that's not a discipline gap, it's the signature of tasks too large to start."*
- **Plans that wait for your sign-off.** Ask it to plan a goal and it *proposes* an editable set of tasks — adjust priority, duration, deadline, delete any — and nothing is written until you click Confirm. This is implementation-intention theory in practice (Gollwitzer & Sheeran, 2006): review and commitment is where follow-through is built.
- **Coaches like a colleague who read the research.** Three beats, every time — the pattern (a real number), the mechanism, one concrete next step:

  > *"Your completion rate is 0.2. Tasks tagged #course are postponed 4 times on average. This is the Zeigarnik effect: an unstarted task creates a mental open loop that drains focus. The stated reasons — 'haven't been able to start it yet' and 'ran out of evening' — confirm the tasks feel too large to begin. Break the next one into a single 15-minute first step, and schedule only that."*

  It quoted the user's *own* deadline-change reasons. That's the whole thesis in one paragraph — judgment-free, no cheerleading, no invented numbers; if the data is thin, it says so.
- **Remembers you across sessions** — consent-gated, locally stored, visible and erasable in the UI. Continuity, not surveillance.
- **Scouts opportunities** — surfaces real, scored hackathons/competitions and turns any into a planned task in one click.

## The onboarding: psychology, not a form

A concierge that's going to coach you has to *understand* you first. Nova opens with a seven-question psychological onboarding, designed against behavioral-science constraints rather than UX convention: **positively-framed** procrastination items (Ferrari, 2018) improve self-report accuracy; **operational and relational questions are kept separate** (Tzeng & Liu, 2015) so the deep answers stay deep; and **the ending is proof, not a question** (McBreen & Jack, 2001) — immediately after the last question, Nova quotes the user's *verbatim* 90-day purpose back to them. And because many arrive having spent months with another AI, an **optional import** lets them paste what ChatGPT, Claude, Gemini, or Perplexity already knows about them (Nova supplies a tailored prompt per model) and **pre-fills the seven questions** for confirmation — turning cold decisions into quick ones.

## Architecture

```
You → Web Console (FastAPI, localhost) or CLI
        │
   Orchestrator  (ADK root agent — least-privilege router)
     ├─ Briefing  (read-only)            "what now?"
     ├─ Planning  (write after confirm)  "goal → tasks"
     └─ Coach     (read-only)            "why do I stall?"

   Supporting agents (invoked by the console):
     Greeting · Profile · Reflection · Pattern Intelligence

   All agents → NovaTools (one implementation)
                 ├─ in-process (default, fast)
                 └─ MCP server · stdio · 11 typed tools
                          │
                ~/.taskflow  (tasks · memory · profile · insights)
   NovaTools ┄(derived context, consent-gated)┄→ Gemini API
```

**Eight agents.** The Orchestrator routes to three least-privilege conversation specialists; four supporting agents handle the relational layer (a Greeting agent that opens each session, a Profile agent that runs onboarding, a Reflection agent at session end, and a Pattern Intelligence agent for multi-week analysis). The Greeting agent deliberately uses a **single fast model call** rather than a tool loop — it fires every session start, so the data (profile + recent memory + today's context) is assembled deterministically and passed in one shot to spare the free-tier budget.

**One implementation, two front doors** — the seam that matters. All capability lives in one class, `NovaTools`, returning typed Pydantic models, exposed two ways from the *same* code: in-process to the agents (the reliable default), and over a real **MCP server on stdio** (11 typed tools) that external clients — Claude Desktop, other ADK systems — can connect to. With `nova ask --mcp` the agents themselves pull their tools from the live MCP subprocess, so MCP is load-bearing, not a checkbox — and the read-only/write split is enforced **per agent even over MCP**. The 11 tools: `get_tasks`, `get_today_context`, `get_behavioral_stats`, `get_edit_history`, `get_opportunities`, `recall_memory` (read); `create_task`, `complete_task`, `schedule_task`, `set_prime_target`, `remember` (write/validated/audited).

**Quota-aware routing.** Complex modes (Plan, Coach) try the most capable Gemini model first; simple modes start cheap. On a `429`, that model is marked exhausted for the session and the router silently falls back — a user never sees a quota error unless every tier is down.

## Course concepts demonstrated (the capstone asks for ≥3; Nova has 6)

| Concept | Where |
|:--|:--|
| **Multi-agent (ADK)** | Orchestrator + 3 least-privilege sub-agents + 4 supporting agents |
| **MCP Server** | 11 typed tools over stdio; same implementation in-process and over the protocol |
| **Security** | No network surface · path containment · consent-gated LLM boundary · audit log · fail-closed validation |
| **Deployability** | A GitHub Action runs the read-only Briefing agent on a schedule; green with or without a key |
| **Agent Skills** | `SKILL.md` — when to invoke Nova, its tools, voice, and security model |
| **Antigravity** | Nova was vibe-coded in Antigravity — shown in the demo video |

## Security (a Concierge-track first-class concern)

Many submissions will claim "no data leaves your machine" while calling a cloud LLM. That isn't true, and a careful judge can disprove it. Nova states the boundary honestly and enforces it:

- **No network surface** — MCP runs over **stdio**, no socket; the console binds to `127.0.0.1` only.
- **Path containment** — every read/write is `realpath` + `commonpath` verified inside the data dir; traversal blocked.
- **Fail-closed validation** — every value crossing into a write is sanitized through TaskFlow's own normalizers.
- **Audit + live consent** — every write is appended to a local audit log; richer behavioral data is read only when the `nova_data_enabled` toggle is on, and that gate is re-checked **live** on every memory access (not frozen at startup).
- **Honest LLM boundary** — files never leave the machine; only the *derived* context an agent needs is sent to Gemini.
- **No secrets in code** — the key comes from a gitignored `.env`; the repo ships only a placeholder template.

## Evaluation, deployability, and frictionless setup

- **Reproducible eval:** `eval/run_eval.py` checks the behavioral derivations, the overdue ranking, and MCP least-privilege; with a key it also verifies the live Coach grounds its answer in real numbers and never cheerleads.
- **Deployability:** a GitHub Action runs the read-only Briefing agent every morning and writes the brief to the run summary, using a committed sanitized sample so it stays green without exposing real data.
- **Zero-config setup:** a tool a judge can't run is a tool a judge can't reward. Nova **self-seeds demo data on first run** (never clobbering a real install) and ships a one-command setup that installs and opens the console — no separate dependencies, no API key required just to explore the architecture and the live data grounding.

## The build — and the discipline behind it

Nova didn't start from zero; it sits on TaskFlow, a behavioral engine I'd already shipped, which means its "dataset" is real usage — genuine postpone counts, real deadline-change reasons, actual durations vs. estimates. That foundation is what lets the Coach cite numbers instead of guessing.

The most instructive moment in the build was a **course-correction in honesty**. An early plan claimed a "fully offline, zero-cloud" mode the code didn't actually implement. In a track judged partly on security and code, a claim a reviewer can falsify by reading one file is a liability — so it was cut. The honest reframe — local-first *data*, derived-context-only to the model, consent-gated — is both more truthful and a stronger security story. The same discipline produced the live-checked consent gate (a bug freezing consent at startup was found and fixed), a three-tier data-reset flow with honest, count-aware confirmations, and a dead-code audit. A concierge handling personal data has to be *trustworthy first*, and trustworthy means the claims match the code. Nova was vibe-coded in **Antigravity**.

## Who it's for, and what makes it real

Nova is for the person whose problem was never *making the list* — students, builders, knowledge workers rewriting the same overdue task. The coaching is true because the data is true: Nova isn't an LLM imagining your habits, it's an agent reading a behavioral dataset a real product has been keeping, and reflecting it back in a voice engineered not to make you feel judged — all without handing your personal data to the cloud.

## Honest limitations and what's next

Nova's intelligence depends on Gemini; the free-tier daily quota is the main practical limit, which the router manages but can't eliminate. The Pattern Intelligence agent is wired and callable but not yet surfaced with its own UI. The richest version of Nova is the **digital-twin** direction — smart duration estimation from history, implementation-intention capture at the moment of planning, a proactive brief that reaches out before you ask. The hooks are already in place.

TaskFlow gave you the execution engine. **Nova gives it a brain.**
