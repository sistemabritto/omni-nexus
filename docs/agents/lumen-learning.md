# Lumen — Learning Retention

**Command:** `/lumen-learning` | **Color:** yellow | **Model:** Sonnet

Lumen is the knowledge retention agent. Where Mentor creates learning content, Lumen makes sure you actually keep it: it captures atomic facts from anything you paste, reviews them on a spaced-repetition schedule (SM-2), and quizzes you with retrieval practice. Tagline: absorb, retain, review.

## When to Use

- You paste an article, transcript, or note and want the key ideas locked in for later ("save the key points from this")
- You want to run a spaced-repetition review session on facts that are due
- You want a retrieval-practice quiz on a topic or deck you've been studying
- You want to see your retention stats (facts due, lapse rate, streaks)
- You want help organizing facts into coherent decks

## Preloaded Skills

| Skill | What it does |
|-------|-------------|
| `learn-capture` | Extract 1–5 atomic facts from pasted text and save SM-2 cards |
| `learn-review` | Run a spaced-repetition review session (SM-2 algorithm) |
| `learn-quiz` | Generate retrieval-practice questions from saved facts |
| `learn-stats` | Report retention metrics per deck and overall |

## How It Works

Facts live in `workspace/learning/facts/` as markdown files with SM-2 frontmatter (interval, ease, reps, lapses, next_review). Each fact is one atomic, self-testable idea in your workspace language.

- **Capture** — paste text; Lumen extracts at most 5 worth-retaining facts per run. It does not fetch URLs.
- **Review** — one fact at a time; you rate recall 0–5; Lumen updates the SM-2 fields.
- **Quiz** — open-ended questions generated from saved facts (Q&A, fill-in-the-blank, multiple choice).
- **Stats** — counts due, lapses, average ease, deck breakdowns, actionable nudges ("you have 12 facts overdue").

## Example Interactions

```
/lumen-learning save the key points from this article about context windows
/lumen-learning revisar os fatos que estão vencidos
/lumen-learning quiz me on the marketing deck
/lumen-learning how many facts do I have due for review?
```

## Routines

None by default — Lumen is on-demand. It surfaces proactive nudges when you ask what to work on next.

## Memory

Persistent memory at `.claude/agent-memory/lumen-learning/`. Learns your retention patterns: preferred deck sizes, review cadence, and topics with high lapse rates. Has read access to the shared knowledge base at `memory/` and to `workspace/projects/` (never writes there).
