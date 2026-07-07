"""
Matador Mike — texting assistant for running Matador.

Flow:
- You text Mike. He can reply directly, answer questions using his current
  client/deadline context, schedule something with a third party, add a
  client, or add a deadline.
- Third-party replies continue that scheduling negotiation until confirmed
  or declined, at which point Mike pings you.
- Every morning at MORNING_DIGEST_HOUR (your local TIMEZONE), Mike texts you
  a to-do list: deadlines coming up + anything he's still waiting to hear
  back on.

Run locally:
    uvicorn app:app --reload --port 8000
"""

import os
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, Form
from fastapi.responses import PlainTextResponse
from twilio.rest import Client as TwilioClient

import db
from claude_agent import run_owner_agent, run_outreach_agent
from digest import build_digest_text

load_dotenv()

app = FastAPI()
db.init_db()

twilio_client = TwilioClient(
    os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]
)
TWILIO_NUMBER = os.environ["TWILIO_PHONE_NUMBER"]
OWNER_NUMBER = os.environ["OWNER_PHONE_NUMBER"]
TIMEZONE = os.environ.get("TIMEZONE", "America/Los_Angeles")
MORNING_DIGEST_HOUR = int(os.environ.get("MORNING_DIGEST_HOUR", "7"))


def send_sms(to: str, body: str):
    twilio_client.messages.create(to=to, from_=TWILIO_NUMBER, body=body)


def send_morning_digest():
    send_sms(OWNER_NUMBER, build_digest_text())


scheduler = BackgroundScheduler(timezone=ZoneInfo(TIMEZONE))
scheduler.add_job(send_morning_digest, "cron", hour=MORNING_DIGEST_HOUR, minute=0)


@app.on_event("startup")
def start_scheduler():
    scheduler.start()


@app.on_event("shutdown")
def stop_scheduler():
    scheduler.shutdown()


@app.post("/sms")
async def sms_webhook(From: str = Form(...), Body: str = Form(...)):
    """Twilio POSTs here on every inbound SMS to your Twilio number."""
    if From == OWNER_NUMBER:
        _handle_owner_message(Body)
    else:
        _handle_third_party_message(From, Body)
    return PlainTextResponse("<Response></Response>", media_type="application/xml")


@app.post("/debug/digest")
def debug_digest():
    """Manually trigger the morning digest early, for testing."""
    send_morning_digest()
    return {"sent": True}


def _handle_owner_message(body: str):
    history = db.get_history(OWNER_NUMBER)
    clients = db.list_clients()
    deadlines = db.get_upcoming_deadlines(days_ahead=7)

    result = run_owner_agent(history, body, clients, deadlines)

    db.add_message(OWNER_NUMBER, "user", body)
    db.add_message(OWNER_NUMBER, "assistant", result["reply"])
    send_sms(OWNER_NUMBER, result["reply"])

    action = result.get("action")
    if not action:
        return

    action_type = action.get("type")

    if action_type == "start_task":
        party_phone = action["phone"]
        purpose = action["purpose"]
        client_name = action.get("client_name")
        db.create_task(party_phone, purpose, client_name)

        opening = run_outreach_agent(purpose, [], "(start the conversation)")
        db.add_message(party_phone, "assistant", opening["reply"])
        send_sms(party_phone, opening["reply"])

    elif action_type == "add_client":
        db.add_client(
            name=action["name"],
            phone=action.get("phone"),
            email=action.get("email"),
            notes=action.get("notes"),
        )

    elif action_type == "add_deadline":
        db.add_deadline(
            description=action["description"],
            due_date=action["due_date"],
            client_name=action.get("client_name"),
        )


def _handle_third_party_message(from_number: str, body: str):
    task = db.get_open_task_for(from_number)
    if not task:
        return  # unknown number with no open task

    history = db.get_history(from_number)
    result = run_outreach_agent(task["purpose"], history, body)

    db.add_message(from_number, "user", body)
    db.add_message(from_number, "assistant", result["reply"])
    send_sms(from_number, result["reply"])

    if result["status"] in ("confirmed", "declined"):
        db.update_task_status(task["id"], result["status"], result.get("confirmed_time"))
        client_tag = f' for {task["client_name"]}' if task.get("client_name") else ""
        if result["status"] == "confirmed":
            notice = f'Mike here — confirmed with {from_number}{client_tag}: {result["confirmed_time"]} for "{task["purpose"]}".'
        else:
            notice = f'Mike here — {from_number} couldn\'t make "{task["purpose"]}"{client_tag} work. Want me to try a different time?'
        send_sms(OWNER_NUMBER, notice)
        # TODO: on confirmed, this is where you'd call the Google Calendar API
        # to actually create the event.
