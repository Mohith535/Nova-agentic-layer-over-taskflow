# TaskFlow + Nova — Full Testing Playbook

> Every feature, every direction, step-by-step. Run this before any demo or submission.

---

## PART 1 — TaskFlow CLI

### 1. Fresh Start (overdue red wall → rescued)

Open terminal in `e:\cli-task-manager`:

```powershell
$env:PYTHONIOENCODING="utf-8"
py -3.12 -m taskflow.cli list          # see current tasks + overdue state
py -3.12 -m taskflow.cli freshstart    # lifts the overdue pressure (reschedules, doesn't delete)
py -3.12 -m taskflow.cli list          # overdue wall should be gone
```

Nuclear wipe:
```powershell
py -3.12 -m taskflow.cli freshstart --all   # deletes all tasks (confirm prompt appears)
py -3.12 -m taskflow.cli list               # empty board
```

---

### 2. Create Mission draft persistence

```powershell
py -3.12 -m taskflow.cli ui
```

1. Click **"+ New Mission"** — type a title and notes, don't submit
2. Click **X** to close
3. Click **"+ New Mission"** again — draft is still there
4. Submit → draft clears

---

### 3. Focus System — full run

```powershell
py -3.12 -m taskflow.cli ui
```

**A — Setup modal:**
1. Click a task → click **"Start Focus"**
2. Set duration to **25m**
3. Toggle **Gentle** vs **Strict** — Strict reveals site picker chips
4. In Strict: add `youtube.com`, `instagram.com`
5. Click **"Begin Focus"**

**B — Mid-session check-in (fires at learned attention span):**
- Card slides in: *"Still in it?"*
- Click **"Yes, keep going"** or **"Take a break"**

**C — Break modal:**
- Click "Take a break" → timed break modal (15 min countdown)
- Click "I'm back" to resume

**D — Session end decision (timer hits 0):**
- Overlay: *"Is the task done?"*
- **"Need more time"** → 15m added, countdown re-arms
- **"Done"** → completion flow

**E — Abort mid-session:**
- Click **"Abort Protocol"** → confirm
- Overlay disappears and stays gone (no resurrection)
- Open browser → YouTube should load (proxy torn down)

**F — Strict mode blocking:**
- During Strict session with `youtube.com` in list
- Open browser → `youtube.com` → blocked page
- After session ends → YouTube loads normally

---

### 4. Intelligence tab

```powershell
py -3.12 -m taskflow.cli ui
```

1. Click **"Intelligence"** in sidebar
2. Expect insight cards: estimated vs actual duration gap, productivity by day, most-postponed tasks
3. No data yet → shows "not enough data" message

---

## PART 2 — Nova Agent

```powershell
cd e:\nova
.venv\Scripts\activate
nova web    # opens at http://127.0.0.1:8765
```

---

### 5. Greeting (automatic on load)

No action needed. Should say:
- How long you've been away
- Something from memory (if stored)
- Your prime target or an overdue candidate

---

### 6. Ask mode — routing test

Send each message one by one:

```
What should I focus on right now?
```
*(→ briefing agent: prime target + load)*

```
Why do I keep avoiding my hardest tasks?
```
*(→ coach agent: behavioral pattern)*

```
I want to start fresh. Forget everything you know about me.
```
*(→ warm clean-slate response: how to wipe memory + tasks)*

---

### 7. Brief mode

Click **"Brief"**, send:
```
Give me my briefing for today
```
Expect: prime target, overdue count, scheduled tasks, notable opportunities.

---

### 8. Coach mode

Click **"Coach"**, send:
```
What pattern should I fix? Be specific.
```
Expect: named mechanism (e.g. "#code tasks average 2.3 postpones — avoidance, not overload").

---

### 9. Scout feed (Opportunity Hunter bridge)

- Left rail → **Opportunities** section: hackathons/internships from Opportunity Hunter, scored and ranked

In Ask mode:
```
What hackathons should I apply to this month?
```
Nova routes to briefing agent → pulls Scout feed → discusses real opportunities by name.

---

### 10. Plan mode — human-in-the-loop gate

Click **"Plan"**, send:
```
Prepare for the Google Solution Challenge
```

What happens:
1. Nova proposes 3–7 tasks — **nothing written yet**
2. Editable card appears (title, priority, duration, deadline per row)
3. Edit a row, change priority, set a deadline
4. Click **"+ Add step"** to add a row
5. Click **X** on a row to remove it
6. Click **"Create N in TaskFlow →"**
7. Verify: `py -3.12 -m taskflow.cli list` — tasks are there

Opportunity-grounded goal:
```
Plan my application for the Microsoft hackathon
```
Should pull real deadline from Scout feed.

---

### 11. Memory panel

1. Click **"What Nova remembers"** in sidebar
2. Click **"clear"** → memory wiped, tasks untouched
3. Panel is now empty

---

### 12. End-to-end showcase loop

Run this in one sitting for the demo:

```
Step 1. Open Nova → read greeting (real context)

Step 2. Ask: "What hackathons should I apply to?"
         → Scout surfaces real opportunities

Step 3. Plan: "Apply to the top hackathon I just saw"
         → Proposal card with real deadline
         → Edit steps, click "Create"

Step 4. py -3.12 -m taskflow.cli today
         → Tasks are there

Step 5. Start a Focus session on Task 1
         → Blocking on, timer runs, decision modal at end

Step 6. Back in Nova: "I just finished the research step. What's next?"
         → Briefing or coach responds in context
```

---

## Quick Smoke Checklist

| Feature | Action | Expected |
|---|---|---|
| Freshstart soft | `taskflow freshstart` | Overdue rescheduled, red wall gone |
| Freshstart hard | `taskflow freshstart --all` | All tasks deleted (confirm first) |
| Draft preserved | Open panel, close, reopen | Content still there |
| Focus setup | Click "Start Focus" | Setup modal appears |
| Gentle mode | Start focus, Gentle selected | No proxy, no blocking |
| Strict mode | Add youtube.com, start | YouTube blocked during session |
| Session end | Timer reaches 0 | Decision modal: done / more time |
| Extend time | "Need more time" | 15m added, countdown re-arms |
| Abort | "Abort Protocol" | Overlay gone, stays gone, sites unblocked |
| Intelligence | Click Intelligence tab | Insight cards appear |
| Nova greeting | Open 127.0.0.1:8765 | Context-aware welcome |
| Scout | Opportunities rail | Hackathon list from Opportunity Hunter |
| Plan propose | Plan mode + goal | Editable card, nothing in TaskFlow yet |
| Plan commit | Click "Create N" | Tasks in `taskflow list` |
| Memory clear | Clear link in sidebar | Memory wiped, tasks untouched |
