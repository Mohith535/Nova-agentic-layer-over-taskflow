[IMAGE: cover — the 560×280 card, also drop it here as the hero]

> **Nova reads how you _actually_ work — what you postpone, why deadlines slip, how long things really take — and coaches you with specifics no generic assistant can. Then it acts: it manages your task board and commands a second, independent agent pipeline that hunts opportunities for you. Your data never leaves your machine.**

> 💬 *"Your #course tasks are postponed 4× on average and your completion rate is 0.2 — that's not a discipline gap, it's the signature of tasks too big to start. Split the next one into a 15-minute first step, and schedule only that."*
> — Nova's Coach, grounded in a real behavioral dataset

> 💬 *"Run a fresh hunt."* → Scout launches a separate scraping+scoring pipeline in the background, reports what it found, and turns the best find into a scheduled task — in one conversation.
> — Nova's Scout, commanding a second agent system

---

## ⚡ At a glance

| | |
|:--|:--|
| **What it is** | A privacy-first, **multi-agent command center** that coaches you from your *real* behavioral data — and acts on it |
| **Built on** | **TaskFlow v9.1.0** — a *shipped* behavioral task manager (real usage data, not a demo fixture) |
| **Commands** | Its own task board **and a second, independent agent pipeline** (the Opportunity Hunter) |
| **The tech** | **10 ADK agents** · a real **MCP server (17 tools)** · Gemini · **100% local data** |
| **Course concepts** | **6 of 6** demonstrated (only 3 required) |
| **Security** | No network surface · path containment · consent-gated · audit log · fail-closed |
| **Try it** | **One command.** Demo data bundled. **No API key needed** to explore. |

---

## The problem — the gap isn't writing tasks down, it's *doing* them

Every to-do app is a better place to *write down* what you should do. None of them know *why you don't do it.* You've known for two weeks you should start the interview prep. The gap isn't information — it's **behavior**.

And behavior leaves a trail: which tasks you postpone, **how many times**, the small reason you mutter when you push a deadline, how long a task *really* takes versus your guess. **No tool reads that trail back to you.** Meanwhile every AI assistant bolted onto a to-do app gives the same hollow advice — *"break it into smaller steps!"* — because it only knows what you **typed**, never what you **did**.

**Nova's bet:** advice grounded in your real behavior beats motivation grounded in nothing.

---

## What Nova does

| | Capability | What it actually means |
|:--:|:--|:--|
| 🔍 | **Reads evidence, not the list** | Every claim cites a real number from your history — never a guess |
| ✅ | **Plans that wait for your sign-off** | Proposes editable tasks; **nothing is written until you confirm** |
| 🧭 | **Coaches like a colleague who read the research** | Pattern → mechanism → one small next step. No cheerleading, no emoji, no invented stats |
| ⚙️ | **Runs your board from chat** | Complete, schedule, postpone, drop — with TaskFlow's psychology intact (drop asks first, record preserved) |
| 🛰️ | **Commands a second agent system** | Launches the Opportunity Hunter pipeline on request, reads its health, turns finds into scheduled tasks |
| 🧠 | **Remembers you across sessions** | Consent-gated, local, erasable. Continuity, not surveillance |
| ✦ | **Knows you from question one** | A 7-question psychological onboarding **+ optional import** from your other AI |

### The onboarding is psychology, not a form
An agent that's going to coach you has to understand you first. Nova's 7-question onboarding is built on behavioral science: **positively-framed** questions (Ferrari, 2018) for honest self-report, **operational kept separate from relational** (Tzeng & Liu, 2015) so deep answers stay deep, and **an ending that's proof, not a question** (McBreen & Jack, 2001) — Nova quotes your *verbatim* 90-day purpose back to you. And because many users arrive after months with another AI, an **optional import** lets you paste what ChatGPT, Claude, Gemini, or Perplexity already knows about you (Nova supplies a tailored prompt per model) and **pre-fills the 7 questions** for you to confirm.

---

## Architecture — one implementation, two front doors

[IMAGE: architecture — screenshot the rendered diagram from the GitHub README, or generate from the prompt in chat]

```
You → Web Console / CLI → Orchestrator (ADK router, least-privilege)
        ├─ Briefing  (read-only)            "what now?"
        ├─ Planning  (write after confirm)  "goal → tasks"
        ├─ Coach     (read-only)            "why do I stall?"
        ├─ Operator  (board management)     "done / postpone / drop / prime"
        └─ Scout     (pipeline command)     "find opportunities / run a hunt"
   + supporting agents: Greeting · Profile · Reflection · Pattern Intelligence
        ↓ all call → NovaTools (one implementation)
            • in-process (fast default)
            • MCP server · stdio · 17 typed tools  → external clients
        ↓ ~/.taskflow  (tasks · memory · profile · insights)
        ↓ HunterBridge → Opportunity Hunter (a second, independent agent system)
   NovaTools ┄(derived context, consent-gated)┄→ Gemini API
```

**The seam that matters: logic vs. transport.** All capability lives in one class, `NovaTools`, returning typed Pydantic models — exposed **two ways from the same code**: in-process to the agents (the reliable default), and over a real **MCP server on stdio** (17 typed tools) that external clients (Claude Desktop, other ADK systems) can connect to. With `nova ask --mcp`, the agents themselves pull tools from the live MCP subprocess — so MCP is **load-bearing, not a checkbox** — and each agent's least-privilege tool list is enforced **even over MCP.**

### The 10 agents

| Agent | Trigger | Reads | Writes / Acts |
|:--|:--|:--|:--|
| **Orchestrator** | every message | intent | routes to one specialist |
| **Briefing** | "what now?" / daily cron | live load, prime target, overdue | — |
| **Planning** | "turn this goal into tasks" | current load, behavioral tags | creates tasks (after you confirm) |
| **Coach** | "why do I keep avoiding this?" | postpone patterns, edit reasons, insights | — |
| **Operator** | "mark 3 done" / "postpone 5 to Friday" / "drop it" | the board + cloud-sync state | complete · schedule · postpone · soft-drop *(asks first)* · prime |
| **Scout** | "find opportunities" / "run a hunt" | Hunter feed + pipeline health | launches hunts · opportunity → task |
| **Greeting** | every session start | profile + recent memory | — *(single fast call, quota-frugal)* |
| **Profile** | onboarding (once) | 7 answers + optional AI import | `user_profile.json` |
| **Reflection** | "End session" | today's activity | 2–3 memory notes |
| **Pattern Intelligence** | weekly | 4 weeks of behavior | `nova_insights.json` *(Coach reads it)* |

**Why multi-agent, not one big prompt?** Three concrete reasons: **least privilege** (Coach literally cannot see a write tool, and only the Operator can complete, postpone, or drop — a "why am I failing?" request can never mutate your data), **distinct voice per discipline**, and **a feedback loop that compounds** (Pattern writes insights → Coach cites them; Reflection writes memory → Greeting opens with it).

---

## The part most agents don't have: agents that command agents

Most "multi-agent" submissions are one brain wearing several prompts. Nova crosses a harder line: **it commands a separate agent system that existed before Nova did.**

The **Opportunity Hunter** is its own project — an 11-source scraping + LLM-scoring pipeline (Devpost, MLH, GitHub, arXiv, coding contests…) that hunted hackathons, internships, and fellowships on a daily schedule, alone, for weeks. Nova's **Scout** agent now commands it in conversation: *"run a fresh hunt"* launches the pipeline as a **detached process** (a real hunt takes minutes — Scout says so instead of pretending), *"is it working?"* reads the pipeline's own output for last-run health, and *"add that one"* turns a scored find into a scheduled TaskFlow task, deadline and all. The coupling is **data + process, never imports** — either project can be rebuilt freely without breaking the other, and without the Hunter installed, Scout **degrades honestly** to the bundled demo feed and says so.

The **Operator** agent (named for TaskFlow's own "OPERATOR M" persona) is Nova's hands on the board: complete, schedule, postpone, drop — from chat. It carries TaskFlow's psychology *into* the agent layer: a drop needs your explicit confirmation and **preserves the behavioral record** (soft-drop, never a hard delete — "rescue, not punishment"), and a postpone updates the same honest postpone-count mirror TaskFlow shows you. It even knows whether your cloud backup is fresh.

That is the real shape of the system: **one intelligence layer that knows and commands an execution engine (TaskFlow) and a discovery engine (the Hunter) — a personal AI OS in miniature.**

### The 17 MCP tools
`get_tasks` · `get_today_context` · `get_behavioral_stats` · `get_edit_history` · `get_opportunities` · `recall_memory` · `get_hunter_status` · `get_sync_status` *(read)* — `create_task` · `complete_task` · `schedule_task` · `set_prime_target` · `postpone_task` · `drop_task` · `run_opportunity_hunt` · `sync_taskflow` · `remember` *(write/act, validated + audited)*

---

## Course concepts — 6 of 6 (only 3 required)

| Concept | Where it lives |
|:--|:--|
| ✅ **Multi-agent (ADK)** | Orchestrator + 5 least-privilege sub-agents + 4 supporting agents — including two that command external systems |
| ✅ **MCP Server** | 17 typed tools over stdio — same implementation in-process *and* over the protocol |
| ✅ **Security** | No network surface, path containment, consent-gated LLM boundary, audit log |
| ✅ **Deployability** | GitHub Action runs the read-only Briefing on a schedule; green with or without a key |
| ✅ **Agent Skills** | A `SKILL.md` defining when to invoke Nova, its tools, voice, and security model |
| ✅ **Antigravity** | Nova was vibe-coded in Antigravity (shown in the demo video) |

---

## Security — the bar Nova holds (enforced, not claimed)

| Guarantee | How |
|:--|:--|
| **No network surface** | MCP runs over **stdio** — no socket, no port. Console binds to `127.0.0.1` only |
| **Path containment** | Every file access is `realpath` + `commonpath` checked — traversal blocked |
| **Honest LLM boundary** | Raw files never leave the machine; only *derived* context is sent to Gemini, and consent is re-checked **live** on every memory access |
| **Least privilege** | Read-only agents cannot see write tools |
| **Audit + fail-closed** | Every write is logged; all write inputs are sanitized through validators |
| **No secrets in code** | Key from a gitignored `.env`; the repo ships only a placeholder template |

---

## Built on a real product, not a demo

Nova didn't start from zero. It sits on **TaskFlow v9.1.0** — a shipped, 100%-offline behavioral task manager — so Nova's "dataset" is **real usage**, not a fixture: genuine postpone counts, actual durations vs. estimates, and an **append-only `edit_history` that captures the reason you gave when you moved a deadline** ("haven't been able to start it yet", "ran out of evening"). That single field is the difference between coaching that's *invented* and coaching that's **true**. Nova doesn't guess your patterns — it reads them.

---

## The build — and the discipline behind it

The most instructive moment wasn't a feature — it was **honesty under pressure**. An early draft claimed a *"fully offline, zero-cloud"* mode the code didn't implement. In a track judged partly on security and code, a claim a reviewer can falsify by reading one file is a liability — so it was cut. The honest reframe (local-first *data*, derived-context-only to the model, consent-gated) is **both more truthful and a stronger story.** The same discipline produced a live-checked consent gate, a three-tier data-reset flow with honest confirmations, and a dead-code audit. An agent handling personal data has to be **trustworthy first** — and trustworthy means the claims match the code.

---

## Try it — genuinely one command

Nova **self-seeds a demo board on first run** (without ever touching a real install), so there's nothing else to set up — **no separate TaskFlow install, no API key needed just to explore** the console, the live data grounding, and the architecture.

```bash
# Windows
git clone https://github.com/Mohith535/Nova-agentic-layer-over-taskflow.git nova && cd nova && setup.bat

# macOS / Linux
git clone https://github.com/Mohith535/Nova-agentic-layer-over-taskflow.git nova && cd nova && bash setup.sh
```

The browser opens at the console with sample data already loaded. Add a free Gemini key only to switch the live AI agents on.

---

## Honest limitations & what's next

Nova's intelligence depends on Gemini; the free-tier daily quota is the main practical limit (the quota-aware router manages it, but can't eliminate it). The Pattern Intelligence agent is wired and callable but not yet surfaced with its own UI. The Opportunity Hunter is the author's local pipeline — judges see the bundled demo feed, with Scout saying so honestly. The richest version of Nova is the **digital-twin** direction — smart duration estimation from history, implementation-intention capture at the moment of planning, a proactive brief that reaches out before you ask. The hooks are already in place.

---

**TaskFlow gave you an execution engine. The Hunter gave you a discovery engine. Nova is the mind that runs them both — on *your* data, on *your* machine, for *you*.**
