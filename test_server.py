"""
Plumbing check — confirms your Twilio number, webhook, and tunnel/domain are
wired correctly, with zero dependency on Claude or the database.

Run:
    uvicorn test_server:app --reload --port 8000
"""

from fastapi import FastAPI, Form
from fastapi.responses import Response
from twilio.twiml.messaging_response import MessagingResponse

app = FastAPI()


@app.post("/sms")
async def sms_webhook(Body: str = Form(...)):
    resp = MessagingResponse()
    resp.message(f"Matador Mike plumbing check ✅ — you said: {Body}")
    return Response(content=str(resp), media_type="application/xml")
