#!/usr/bin/env python3
"""
update_agent.py -- Owner automation helper for update campaigns.

Creates update campaigns and dispatches to active licensed users through the
central license server. Users receive an accept link per update.

Examples:
  python update_agent.py run --version 1.2.3 --title "Engine improvements" --message "Safer live-mode startup"
  python update_agent.py create --version 1.2.3 --title "Patch" --message "Bug fixes"
  python update_agent.py send --campaign-id 12
"""

import argparse
import json
import os
import sys

import requests

DEFAULT_SERVER = "https://alien-ai-trader-dashboard.onrender.com"
DEFAULT_APP_ID = "alien-ai-trader"


def _server(args) -> str:
    return (args.server or os.environ.get("LICENSE_SERVER_URL") or DEFAULT_SERVER).rstrip("/")


def _secret(args) -> str:
    return (args.secret or os.environ.get("LICENSE_SECRET") or "").strip()


def _headers(secret: str) -> dict:
    return {"Authorization": f"Bearer {secret}"}


def _request(method: str, url: str, **kwargs):
    r = requests.request(method, url, timeout=45, **kwargs)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    return r.status_code, data


def _must_secret(args) -> str:
    secret = _secret(args)
    if not secret:
        raise SystemExit("Missing LICENSE_SECRET. Set env LICENSE_SECRET or pass --secret.")
    return secret


def cmd_create(args):
    secret = _must_secret(args)
    body = {
        "appId": args.app_id,
        "version": args.version,
        "title": args.title,
        "message": args.message,
        "updateUrl": args.update_url,
        "createdBy": args.created_by,
    }
    status, data = _request(
        "POST",
        f"{_server(args)}/api/updates/admin/create",
        headers=_headers(secret),
        json=body,
    )
    print(json.dumps(data, indent=2))
    if status >= 300:
        raise SystemExit(f"Create failed with HTTP {status}")


def cmd_send(args):
    secret = _must_secret(args)
    body = {
        "appId": args.app_id,
        "campaignId": args.campaign_id,
    }
    if args.emails:
        body["emails"] = [e.strip() for e in args.emails.split(",") if e.strip()]
    status, data = _request(
        "POST",
        f"{_server(args)}/api/updates/admin/send",
        headers=_headers(secret),
        json=body,
    )
    print(json.dumps(data, indent=2))
    if status >= 300:
        raise SystemExit(f"Send failed with HTTP {status}")


def cmd_run(args):
    secret = _must_secret(args)
    create_body = {
        "appId": args.app_id,
        "version": args.version,
        "title": args.title,
        "message": args.message,
        "updateUrl": args.update_url,
        "createdBy": args.created_by,
    }
    s1, d1 = _request(
        "POST",
        f"{_server(args)}/api/updates/admin/create",
        headers=_headers(secret),
        json=create_body,
    )
    print("Create result:")
    print(json.dumps(d1, indent=2))
    if s1 >= 300:
        raise SystemExit(f"Create failed with HTTP {s1}")

    campaign = d1.get("campaign") or {}
    cid = campaign.get("id")
    if not cid:
        raise SystemExit("Create succeeded but campaign id is missing.")

    send_body = {
        "appId": args.app_id,
        "campaignId": cid,
    }
    if args.emails:
        send_body["emails"] = [e.strip() for e in args.emails.split(",") if e.strip()]
    s2, d2 = _request(
        "POST",
        f"{_server(args)}/api/updates/admin/send",
        headers=_headers(secret),
        json=send_body,
    )
    print("Send result:")
    print(json.dumps(d2, indent=2))
    if s2 >= 300:
        raise SystemExit(f"Send failed with HTTP {s2}")


def main():
    p = argparse.ArgumentParser(description="Autonomous update campaign helper")
    p.add_argument("--server", default=None, help="License server base URL")
    p.add_argument("--secret", default=None, help="Admin secret (LICENSE_SECRET)")

    sub = p.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create", help="Create an update campaign")
    create.add_argument("--app-id", default=DEFAULT_APP_ID)
    create.add_argument("--version", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--message", required=True)
    create.add_argument("--update-url", default="")
    create.add_argument("--created-by", default="owner")
    create.set_defaults(func=cmd_create)

    send = sub.add_parser("send", help="Send an existing campaign")
    send.add_argument("--app-id", default=DEFAULT_APP_ID)
    send.add_argument("--campaign-id", required=True, type=int)
    send.add_argument("--emails", default="", help="Optional comma-separated target emails")
    send.set_defaults(func=cmd_send)

    run = sub.add_parser("run", help="Create then send a campaign")
    run.add_argument("--app-id", default=DEFAULT_APP_ID)
    run.add_argument("--version", required=True)
    run.add_argument("--title", required=True)
    run.add_argument("--message", required=True)
    run.add_argument("--update-url", default="")
    run.add_argument("--created-by", default="owner")
    run.add_argument("--emails", default="", help="Optional comma-separated target emails")
    run.set_defaults(func=cmd_run)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
