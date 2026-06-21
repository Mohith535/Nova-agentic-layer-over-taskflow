# Nova — the agent that knows *why* you keep avoiding it

**Subtitle:** A multi-agent productivity coach built on a shipped behavioral task manager.
**Track:** Concierge Agents
**Code:** https://github.com/Mohith535/Nova-agentic-layer-over-taskflow ·
**Foundation:** https://github.com/Mohith535/TaskFlow (v9.1.0)

> *Draft for the 2,500-word Kaggle writeup. Paste into the Kaggle Writeup editor; attach the
> cover image + the YouTube video in the Media Gallery before submitting.*

---

## The problem

Every productivity app is a better place to *write down* what you should do. None of them know
*why you don't do it.* You already know you should start the interview prep — you've known for two
weeks. The gap isn't information; it's behavior. And behavior leaves a trail: what you postpone,
*when* you postpone it, the little reason you mutter when you push a deadline. No tool reads that
trail back to you.

That's the problem Nova solves: **turn the behavioral exhaust of task management into specific,
honest coaching** — without becoming one more app that nags you or ships your private life to a
server.

## Why an agent — and why three?

This isn't a script. The input is a fuzzy human goal ("prepare for the Microsoft Explore
interview") or a fuzzy human question ("why do I keep avoiding this?"), and the right response
depends on messy, evolving personal data. That's an agent's job: *reason over tools and data,
decide what to fetch, and act.* Nova uses an **ADK router** over **three specialists**, and the
separation is deliberate, not decorative:

1. **Least privilege.** The Coach and Briefing agents are **read-only**; only the Planner can
   write. A "why am I failing?" request can therefore *never* mutate your data — the capability
   isn't on the table.
2. **Distinct voice.** The Coach's "name the mechanism, no cheerleading" instruction and the
   Planner's "respect current load, size up not down" discipline are different jobs that degrade
   when fused into one prompt.
3. **Distinct cadence.** Briefing runs unattended (a daily GitHub Action); the others run on
   demand. Separating them lets each boundary be scheduled and reasoned about independently.

## The foundation: a real product, not a demo

Nova is built on **TaskFlow v9.1.0** — a shipped, 100%-offline behavioral task manager I built
first. It already records, per task: priority, soft/hard deadlines, duration estimates vs. actual
focus time, postpone counts, and — crucially — an **append-only `edit_history`** that captures
*the reason the user gave when they moved a deadline* ("I haven't been able to start it yet",
"ran out of evening again"). That field is the difference between coaching that's invented and
coaching that's **true**. Nova doesn't guess your patterns; it reads them.

## Architecture

```
You → Nova Orchestrator (ADK router) → one specialist (briefing | planning | coach)
                                              │  same tools, two front doors
                                   ┌──────────▼───────────┐
                                   │ TaskFlow MCP server   │ stdio · no network surface
                                   │ 8 typed tools         │ path-contained · audited
                                   └───────────────────────┘ → ~/.taskflow/
```

The seam that matters: **logic vs. transport.** All capability lives in one class (`NovaTools`),
returning typed Pydantic models. It's exposed two ways from the *same* implementation — in-process
to the agents (reliable default) and over an **MCP server** (`python -m nova.mcp.server`, stdio) to
any external client. With `nova ask --mcp`, the agents themselves pull their tools from the live
MCP subprocess, so MCP is load-bearing, not a checkbox — and the read-only/write split is enforced
**per agent even over MCP** (the Coach literally cannot see the write tools; this is verified in
the eval harness).

Eight tools: `get_today_context`, `get_tasks`, `get_behavioral_stats`, `get_edit_history` (read);
`create_task`, `complete_task`, `schedule_task`, `set_prime_target` (write, validated + audited).

## The three agents (the Coach is the star)

- **Briefing** — *"what do I do right now?"* Synthesizes live load, prime target, overdue
  candidates, and time of day into a directive. After 6pm it flips to wind-down mode (one thing
  for tomorrow) — because willpower is lowest at night.
- **Planning** — *"turn this goal into tasks."* Reads current load first, then creates 3–6
  right-sized tasks, sizing up (the planning fallacy) and suggesting a Prime Target.
- **Coach** — *"why do I keep failing at this?"* Reads the real behavioral data and reflects the
  pattern back in three beats: **the pattern with the number → the mechanism → one concrete
  change.** It is judgment-free and never cheerleads. A live run on the sample data:

  > *"Your completion rate is 0.2. Tasks tagged #course are postponed 4 times on average... This
  > is the Zeigarnik effect: an unstarted task creates a mental open loop that drains focus. The
  > stated reasons — 'haven't been able to start it yet' and 'ran out of evening' — confirm the
  > tasks feel too large to begin. Break the next one into a single 15-minute first step, and
  > schedule only that."*

  It quoted the user's *own* deadline-change reasons. That's the whole thesis in one paragraph.

The voice is grounded in published research (Zeigarnik 1927; Baumeister on ego depletion; the
planning fallacy; Gollwitzer's implementation intentions; the Fresh Start Effect) — and applied
correctly, not as decoration. The full research basis lives in TaskFlow's `docs/deep-dive.md`.

## Security (a Concierge-track first-class concern)

Most submissions will claim "no data leaves your machine" while calling a cloud LLM. That's not
true, and a careful judge can disprove it. Nova states the boundary honestly and enforces it:

- **No network surface.** The MCP server runs over **stdio** — no socket. (If HTTP is ever
  enabled, the server refuses any non-loopback bind.)
- **Path containment.** Every read/write is resolved and verified inside the TaskFlow data dir
  (`realpath` + `commonpath`); traversal is blocked.
- **Fail-closed validation.** Every value crossing into a write is sanitized and routed through
  TaskFlow's own normalizers, so nothing invalid enters the dataset.
- **Audit + consent.** Every write is appended to a local audit log; richer behavioral data is
  read only when TaskFlow's `nova_data_enabled` consent toggle is on.
- **Honest LLM boundary.** Files never leave the machine; only the *derived* context an agent
  needs is sent to the model. For zero egress, `NOVA_MODEL_BACKEND=local` runs an Ollama model.
- **No secrets in code.** The key comes from `.env` (gitignored); `.env.example` is the template.

## Agent Skills, deployability, and the build

- **Agent Skills:** `.agents/skills/nova/SKILL.md` implements the open standard (mirrored to
  `.claude/` and `.antigravitycli/`) — declaring when to invoke Nova, the agents, the tools, the
  voice, and the security model.
- **Deployability:** a GitHub Action runs the read-only Briefing agent every morning and writes
  the brief to the run summary, using a committed sanitized sample so it's green without exposing
  real data.
- **Evaluation:** `eval/run_eval.py` reproducibly checks the behavioral derivations, the overdue
  ranking, MCP least-privilege, and (with a key) that the live Coach grounds its answer in real
  numbers and never cheerleads — 10/10 on the sample.
- **The build:** developed in **Antigravity with a Claude model**. The most instructive moment was
  a *course-correction*: an early plan claimed "no data exfiltration" while using Gemini. That's
  false. The honest reframe — local-first, derived-context-only, consent-gated, with an offline
  option — is both more truthful and a stronger security story.

## What makes it real

The coaching is true because the data is true. Nova isn't an LLM imagining your habits; it's an
agent reading a behavioral dataset a real product has been keeping, and reflecting it back in a
voice engineered not to make you feel judged. TaskFlow gave you the execution engine. **Nova gives
it a brain.**
