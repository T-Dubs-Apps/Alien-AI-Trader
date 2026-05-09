# crash_notifier.py — Crash notification helpers for Alien AI Trader
import os
import requests

def send_crash_notification(message: str):
    """Send crash alert via Pushbullet, Pushover, and Twilio if configured."""
    # Pushbullet
    pb_token = os.environ.get("PUSHBULLET_API_KEY", "")
    if pb_token:
        try:
            requests.post("https://api.pushbullet.com/v2/pushes",
                          headers={"Access-Token": pb_token, "Content-Type": "application/json"},
                          json={"type": "note", "title": "Alien AI Trader Crash", "body": message}, timeout=5)
        except Exception:
            pass
    # Pushover
    po_token = os.environ.get("PUSHOVER_TOKEN", "")
    po_user  = os.environ.get("PUSHOVER_USER", "")
    if po_token and po_user:
        try:
            requests.post("https://api.pushover.net/1/messages.json",
                          data={"token": po_token, "user": po_user, "message": message}, timeout=5)
        except Exception:
            pass
    # Twilio (call)
    tw_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    tw_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    tw_from = os.environ.get("TWILIO_FROM_NUMBER", "")
    tw_to = os.environ.get("TWILIO_TO_NUMBER", "")
    if all([tw_sid, tw_token, tw_from, tw_to]):
        try:
            from twilio.rest import Client
            client = Client(tw_sid, tw_token)
            client.calls.create(
                to=tw_to,
                from_=tw_from,
                twiml=f'<Response><Say>{message}</Say></Response>'
            )
        except Exception:
            pass
