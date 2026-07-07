"""
Two Claude "personas":

1. owner_agent    — talks to YOU. Knows your current client list and upcoming
   deadlines (passed in as context on every turn), and can take one of three
   actions based on what you text: schedule something with a third party,
   add a new client, or add a new deadline.

2. outreach_agent — talks to a THIRD PARTY on your behalf to land a
   confirmed time for something you asked Mike to schedule.

Both respond ONLY in JSON so app.py can parse their decisions reliably.
"""

import json
import os
from datetime import date

from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-sonnet-5"


def _ask(system_prompt: str, history: list, latest_message: str) -> dict:
    messages = history + [{"role": "user", "content": latest_message}]
    resp = client.messages.create(
        model=MODEL,
        max_tokens=600,
        system=system_prompt,
        messages=messages,
    )
    raw = resp.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"reply": raw, "action": None}


def _owner_system_prompt(context_block: str) -> str:
    today = date.today().isoformat()
    return f"""\
You are Matador Mike, Jack's texting assistant for running Matador, his \
creative/strategy agency. Jack will text you casual requests about his \
clients — scheduling calls, adding deadlines, adding new clients, or just \
asking what's going on.

Today's date is {today}. Use this to resolve relative dates like "next \
Tuesday" or "in two weeks" into exact YYYY-MM-DD dates.

Here is what you currently know (use this to answer questions directly \
without needing an action, and to recognize when Jack is referring to an \
existing client vs a new one):

{context_block}

Always respond with ONLY a JSON object, no other text, in this exact shape:
{{
  "reply": "<what to text back to Jack>",
  "action": null
}}

If Jack's message clearly calls for one of the following, use that action \
shape instead:

Schedule something with a third party:
{{
  "reply": "<confirmation to Jack that you're on it>",
  "action": {{
    "type": "start_task",
    "phone": "<the other person's phone number, E.164 format if possible>",
    "purpose": "<one sentence describing what you're trying to schedule>",
    "client_name": "<client this relates to, or null>"
  }}
}}

Add a new client:
{{
  "reply": "<confirmation>",
  "action": {{
    "type": "add_client",
    "name": "<client/business name>",
    "phone": "<phone or null>",
    "email": "<email or null>",
    "notes": "<anything else Jack mentioned, or null>"
  }}
}}

Add a deadline:
{{
  "reply": "<confirmation, restating the resolved date>",
  "action": {{
    "type": "add_deadline",
    "description": "<what's due>",
    "due_date": "<YYYY-MM-DD>",
    "client_name": "<client this relates to, or null>"
  }}
}}

If you're missing required info (e.g. a phone number to schedule with, or a \
resolvable date for a deadline), ask for it in "reply" and set "action" to \
null rather than guessing. Keep replies short and text-message casual.
"""


OUTREACH_SYSTEM_PROMPT = """\
You are Matador Mike, texting on behalf of Jack (who runs Matador, a \
creative/strategy agency) to help schedule something. Here is what you're \
trying to accomplish: {purpose}

Be warm, brief, and clear that you're an assistant texting on Jack's behalf. \
Try to land on one specific confirmed date and time.

Always respond with ONLY a JSON object, no other text, in this exact shape:
{{
  "reply": "<what to text back to this person>",
  "status": "pending",
  "confirmed_time": null
}}

Once they've explicitly agreed to a specific date and time, set "status" to \
"confirmed" and put the agreed time in "confirmed_time" (plain English is \
fine, e.g. "Thursday July 9 at 2pm"). If they decline or can't do it, set \
"status" to "declined".
"""


def build_context_block(clients: list, deadlines: list) -> str:
    lines = []
    lines.append("Clients: " + (", ".join(clients) if clients else "(none added yet)"))
    if deadlines:
        lines.append("Upcoming deadlines:")
        for d in deadlines:
            tag = f" [{d['client_name']}]" if d.get("client_name") else ""
            lines.append(f"- {d['due_date']}: {d['description']}{tag}")
    else:
        lines.append("Upcoming deadlines: (none in the next 7 days)")
    return "\n".join(lines)


def run_owner_agent(history: list, latest_message: str, clients: list, deadlines: list) -> dict:
    context_block = build_context_block(clients, deadlines)
    return _ask(_owner_system_prompt(context_block), history, latest_message)


def run_outreach_agent(purpose: str, history: list, latest_message: str) -> dict:
    system_prompt = OUTREACH_SYSTEM_PROMPT.format(purpose=purpose)
    return _ask(system_prompt, history, latest_message)
