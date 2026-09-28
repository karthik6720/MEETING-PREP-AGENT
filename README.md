# Meeting Prep Agent

A memory-powered agent that briefs you before a meeting with full context
from every past interaction with that contact — built for HackWithHyderabad
3.0 on [Hindsight](https://hindsight.vectorize.io).

> "Sales reps waste hours re-reading CRM notes before calls. An agent with
> deal memory can brief a rep in seconds and suggest winning tactics based
> on past deals." — the problem statement this targets.

## The 60-second demo story

1. Ask for a prep briefing on a brand-new contact → the agent has nothing to
   say. Generic, useless.
2. Log three real meetings over six weeks (objections raised, promises made
   on both sides, a blocker, a resolved blocker).
3. Ask for the *same* prep briefing again → it's now a sharp, specific
   summary: what's changed, what's still owed, what to say to close.
4. Give the agent one line of feedback on briefing style ("keep it under
   150 words, bullets only") → the very next briefing obeys it.

Run it yourself in one command:

```bash
python cli.py demo
```

## Why memory is the star, not a feature

Every other part of this project (Groq calls, the CLI, the contact
registry) is plumbing. The actual product is what's stored in and
retrieved from Hindsight:

- **One Hindsight memory bank per contact** (`contact::<slug>`). Deal
  memory for Rohan at Northwind never bleeds into deal memory for anyone
  else — the same way a rep keeps deals mentally separate.
- **`retain()`** stores *atomic* facts, not raw transcripts: each promise,
  objection, and topic becomes its own tagged, timestamped memory
  (`kind`, `contact`, `slug` metadata). Small self-contained statements
  recall and reflect far better than giant blobs.
- **`reflect()`** is what generates the relationship summary the briefing
  is grounded in — this is Hindsight's disposition-aware synthesis across
  everything retained for that contact, not a prompt we hand-wrote.
- **`recall()`** additionally surfaces the raw matching memories in the
  CLI output (`Raw memories retrieved from Hindsight`), so it's visible
  that the briefing is grounded in real retained facts and not the LLM
  making things up.
- **A second, separate bank (`user-style-preferences`)** stores feedback
  on the agent's own output. This is memory the agent has about *itself*
  — it's how "keep it under 150 words" persists across every future
  briefing for every contact, without retraining or hardcoding.

## Architecture

```
cli.py                 click CLI: contact-add, meeting-log, prep, feedback, demo
agent/
  config.py            env vars, bank-id naming
  contacts.py           local address book (name <-> Hindsight bank slug)
  memory.py             ALL Hindsight calls live here (retain/recall/reflect)
  llm.py                Groq: raw notes -> structured facts, and
                         memory context -> polished briefing
data/
  seed_demo_data.py     synthetic 3-meeting deal history + before/after demo
```

**Agent loop:**

```
raw meeting notes
      │  Groq (function-calling, with a plain-JSON fallback
      │  for when tool-calling flakes on smaller models)
      ▼
structured facts (topics / promises×2 / concerns / sentiment)
      │  Hindsight retain() -- one atomic memory per fact
      ▼
Hindsight memory bank (per contact)
      │  Hindsight recall() + reflect()
      ▼
grounded relationship context + open follow-ups
      │  Groq -- compose_briefing(), honoring style_notes()
      ▼
prep briefing
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in HINDSIGHT_API_KEY (ui.hindsight.vectorize.io -> Connect -> Create API Key)
# and GROQ_API_KEY (console.groq.com)
```

Hindsight Cloud signup: use promo code `MEMHACK99` in the billing section
after registering for $50 in free credits.

## Usage

```bash
# One-command demo with realistic synthetic data (recommended for judges)
python cli.py demo

# Real usage
python cli.py contact-add "Priya Menon" --company "Acme Retail" --role "VP Sales"
python cli.py meeting-log priya-menon --notes "..." --date 2026-09-20
python cli.py prep priya-menon --goal "close the Q4 renewal"
python cli.py feedback "keep briefings under 150 words, bullets only"
python cli.py contacts
```

## Judging-criteria notes

- **Use of Hindsight memory (25%):** memory isn't a side feature — the
  briefing *is* a `reflect()` call, grounded by visible `recall()` output,
  and the agent's own output style is itself stored and recalled memory.
- **Real-world impact:** targets a workflow (deal/relationship memory
  before calls) that sales, account management, and customer success
  teams already pay for in CRM tooling — this is the memory layer they're
  missing.
- **Technical implementation:** Groq function-calling has an explicit
  fallback path for malformed/missing tool calls, per the hackathon's own
  warning that smaller open models can flake on function calling.

## Known limitations / next steps

- Style preferences are recalled per-briefing but not yet A/B tested for
  drift over many feedback rounds.
- No calendar integration yet — meetings are logged manually. A real
  version would pull meeting transcripts (Zoom/Meet) automatically.
- Single-user only; a team version would need per-user auth on top of the
  per-contact bank isolation that already exists.
