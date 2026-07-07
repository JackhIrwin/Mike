# Matador Mike — texting assistant for running Matador

Texts you a daily to-do, tracks clients and deadlines, and can schedule
things with third parties on your behalf — all over SMS.

## What Mike can do

Text him naturally:
- *"New client: Alma Taco, contact is Sarah, sarah@almataco.com"* → adds a client
- *"Alma Taco positioning doc due next Friday"* → adds a deadline (Mike resolves the actual date)
- *"Text Sarah at 555-123-4567 and see if she's free Thursday at 2 for the Alma Taco kickoff"* → opens a scheduling thread with Sarah, and pings you once it's confirmed
- *"What's due this week?"* → answers directly from what he already knows, no action needed

Every morning at `MORNING_DIGEST_HOUR` (your `TIMEZONE`), he proactively texts
you deadlines coming up in the next 7 days plus anything he's still waiting
to hear back on.

## How it works

- `db.py` — Postgres tables: `clients`, `deadlines`, `tasks` (in-progress
  scheduling negotiations), `messages` (conversation history per thread).
- `claude_agent.py` — `run_owner_agent` is given your current client list and
  upcoming deadlines as context on every turn, so it can answer questions
  directly and recognize existing clients by name. It returns one of four
  action types: `start_task`, `add_client`, `add_deadline`, or `null`.
  `run_outreach_agent` runs the separate conversation with whoever you're
  scheduling with.
- `digest.py` — builds the morning text. Deliberately deterministic (no LLM
  call) so the to-do list itself is never paraphrased or hallucinated.
- `app.py` — the Twilio webhook, action handling, and an APScheduler job that
  fires the digest daily.

## Setup

1. Copy `.env.example` to `.env` and fill in Twilio, Anthropic, your phone
   number, and (for local dev) a `DATABASE_URL` — see below.
2. `pip install -r requirements.txt`
3. `uvicorn app:app --reload --port 8000`

### Local database

Easiest path: use the same Postgres instance Railway gives you in production.
In the Railway dashboard, open your Postgres service → **Connect** tab, copy
the connection string, and paste it into `.env` as `DATABASE_URL`. That way
you're developing against the same data Mike uses live.

### Testing the digest without waiting for the scheduled hour

Hit `POST /debug/digest` (e.g. `curl -X POST http://localhost:8000/debug/digest`)
to fire it immediately.

## Deploying (Railway)

See the setup steps from earlier in this project — GitHub Repository deploy,
attach a Postgres service, link `DATABASE_URL`, set the rest of the env vars,
generate a domain, point your Twilio webhook at `<domain>/sms`.

One addition for this version: **Railway free/hobby services can sleep or
restart**, which would silently drop your scheduled digest job since
APScheduler only runs while the process is alive. If the morning text stops
showing up, check Railway's deploy logs for unexpected restarts — moving the
digest to a **Railway Cron Job** service that calls `POST /debug/digest`
on a schedule (instead of relying on in-process APScheduler) is a more
robust alternative once you've confirmed the core flow works.

## What's stubbed out (next steps)

- **Google Calendar**: creating the event on confirmation, and checking your
  real availability before Mike offers times.
- **Editing/removing deadlines and clients** — right now it's add-only; you
  can extend the action schema in `claude_agent.py` the same way `add_deadline`
  was added.
- **Multiple concurrent tasks per contact** — `get_open_task_for` assumes one
  open task per phone number.
# Mike
