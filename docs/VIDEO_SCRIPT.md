# Nova — 5-minute video script (shot-by-shot)

Target: ≤5:00, published to YouTube, attached to the Kaggle Media Gallery. Record in Antigravity
with a **Claude model visibly selected** (one of the six required concepts is shown here).
Voiceover lines are tight on purpose — read at a calm pace and you'll land ~4:40.

---

### 0:00–0:30 · The hook (talking head or screen + VO)
> "Every productivity app is a better place to write down what you should do. None of them know
> *why you don't do it.* I built one that does."

On screen: the Nova title card + the one-liner. Then your real TaskFlow board with a few overdue
tasks visible. Keep it human — name the feeling: *"I've known I should start this for two weeks."*

### 0:30–1:10 · Problem → why agents
> "The gap isn't information, it's behavior — and behavior leaves a trail: what you postpone,
> when, and the reason you give when you move a deadline. Reading that trail and acting on it is
> an agent's job, not a script's."

On screen: a slow zoom on a task's edit history showing a real reason like *"ran out of evening
again."* This is the emotional core — let it breathe for 2 seconds.

### 1:10–1:50 · Architecture (diagram)
> "Nova is an ADK router over three specialists. Briefing and Coach are read-only; only the
> Planner can write — least privilege, by construction. All of them share one tool implementation,
> exposed in-process and over an MCP server."

On screen: the architecture diagram from the README. Highlight the read-only vs. write split.

### 1:50–3:10 · THE DEMO (this is what wins — give it the most time)
Terminal in Antigravity. Run, in order:
1. `nova coach` → let the full response render. **Pause on the line where it quotes the user's own
   deadline reason.** VO: *"It didn't invent that — it read my own words back to me."*
2. `nova plan "prepare for the Microsoft Explore interview"` → show the 5 created tasks + the
   Prime Target suggestion. VO: *"It respected my current load and sized the work up, not down."*
3. `nova brief` → the evening wind-down line. VO: *"After 6pm it stops piling on and helps me pick
   one thing for tomorrow."*

### 3:10–3:50 · MCP is real (not a checkbox)
1. `python -m nova.mcp.server --selftest` → the 8 tools.
2. `nova ask --mcp "what should I focus on?"` → VO: *"With one flag, the agents pull their tools
   from the live MCP server over stdio — and the Coach still can't see the write tools. Least
   privilege holds over the wire."*

### 3:50–4:20 · Security + evaluation
> "It's a Concierge agent, so I was honest about data. The MCP server has no network socket. Files
> never leave the machine — only derived context goes to the model, with a consent toggle, and an
> offline model option for zero egress."

On screen: run `python eval/run_eval.py` → the green PASS list. VO: *"And it's evaluated — the
coaching is checked against real data, including that it never cheerleads."*

### 4:20–4:50 · Deployability + the build
On screen: the GitHub Action page, trigger `workflow_dispatch`, show the brief in the run summary.
> "A daily brief ships via GitHub Actions. And all of this is built on TaskFlow — a real, shipped
> product — so the behavioral data is real, which is the whole point."

### 4:50–5:00 · Close
> "Every productivity app tells you what to do. Nova is the first that knows why you avoid it — and
> fixes that. TaskFlow gave you the execution engine. Nova gives it a brain."

End card: repo URL + "built in Antigravity with Claude."

---

## Recording checklist
- [ ] Antigravity visible with a **Claude model selected** (satisfies the Antigravity concept).
- [ ] Use real `~/.taskflow` data for `nova coach` (the quoted reason is the money shot) — or the
      committed sample if you'd rather not show personal tasks.
- [ ] Terminal font large enough to read at 1080p.
- [ ] Keep each command's output on screen long enough to read the key line.
- [ ] ≤ 5:00. If long, trim the architecture narration, never the demo.
