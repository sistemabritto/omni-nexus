---
name: prod-end-of-day
description: "End-of-day consolidation — analyzes agent memory, ADW logs, meetings, tasks, and learnings to generate a complete daily log. Trigger when user says 'end of day', 'wrap up', 'done for today', 'goodnight', 'shutdown', or anything that signals finishing a work session."
---

# End of Day — Daily Consolidation

End-of-day routine that consolidates everything that happened during the day: agent memory, ADW logs, meetings, tasks, and learnings.

**Always respond in English.**

## Step 0 — Did a dossier arrive?

| How it was invoked | What to do |
|---|---|
| With `--dossie-pronto` in the arguments | **Cron mode.** Skip Step 1 entirely. |
| No arguments (someone typed "end of day") | **Conversation mode.** Run Step 1. |

In cron mode the routine (`ADWs/routines/end_of_day.py` →
`dashboard/backend/briefing_dados.py`) has already collected, before calling
you: today's commits and working-tree diff, every routine that ran and how it
ended, the memory/meeting files written today, open tasks, pending approvals
and open tickets.

Re-collecting that with tools is paying twice for the same data — one turn per
source is exactly what made this routine the most expensive in the workspace
(US$ 7.84 accumulated). In cron mode go straight to Step 2, and read a file
from the dossier's list **only** when you need its content to judge whether it
holds a learning.

Also skip Step 1f in cron mode: there is no session conversation to review at
21:00 — the dossier is the whole record of the day.

## Step 1 — Collect data for the day (silently) — conversation mode only

Read all available sources without narrating each step:

### 1a. Agent memory
Read recent memory files from each agent in `.claude/agent-memory/`:
- `flux-finance/` — financial decisions of the day
- `atlas-project/` — project updates
- `kai-personal-assistant/` — if there is anything relevant
- Any other agent that was used

### 1b. ADW logs
Read today's JSONL log at `ADWs/logs/YYYY-MM-DD.jsonl` to see which routines ran, duration, and status.

### 1c. Meetings of the day
Check `workspace/meetings/summaries/` and `workspace/meetings/fathom/` for today's synced meetings.

### 1d. Tasks
Run `todoist today` to see completed and pending tasks for the day.

### 1e. Git changes of the day
Run `git diff --stat` and `git log --oneline --since="today 00:00"` to see:
- Files created, modified, or deleted today
- Commits made (messages and authors)
- Uncommitted changes (working tree)

This gives the real overview of what changed in the workspace — more accurate than reading the conversation.

### 1f. Current session
Review the current session conversation — what was discussed, decided, and done.

## Step 2 — Consolidate learnings

Analyze everything that was collected and identify:
- **Decisions made** — what was decided and why
- **Learnings** — patterns, corrections, feedback that should be remembered
- **People** — new context about team members
- **Real pending items** — things that truly remain open (do not fabricate)

## Step 3 — Save memory

If there are relevant decisions, learnings, or feedback, save to persistent memory in `memory/` following the workspace memory system (see `prod-memory-management`).

Do not duplicate — check if similar memory already exists before creating.

## Step 4 — Generate daily log

Read the template at `.claude/templates/end-of-day-log.md` and fill with the consolidated data.

Save to:
```
workspace/daily-logs/[C] YYYY-MM-DD.md
```

The log should include:
- What was done (projects, tasks, meetings)
- Files created or modified
- ADW routines that ran (with status)
- Pending items (only if real)
- Where to resume tomorrow

## Step 5 — Organize tasks

Review Todoist tasks directly (do NOT invoke `/prod-review-todoist` as a sub-skill — it sends a duplicate Telegram notification):
- Run `todoist today` to list today's tasks
- For each uncategorized or non-PT-BR task: rename/recategorize via `todoist update`
- Report how many were organized

## Step 6 — Confirm

Present a short summary:

```
## Day closed

**Log:** workspace/daily-logs/[C] YYYY-MM-DD.md
**ADW Routines:** {N} executed ({status})
**Tasks:** {completed}/{total} completed
**Memories:** {N} created/updated
**Learnings:** {N} recorded

**Tomorrow:** {sentence about where to resume}
```

