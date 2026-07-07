#!/usr/bin/env python3
"""
grant.py -- Central license grant/revoke/status helper.

This tool calls your deployed license API so grants are created on the same
server that validates subscriptions. It is designed for owner/admin use.

Examples:
  python grant.py grant --email user@example.com --tier monthly
  python grant.py revoke --email user@example.com
  python grant.py status --email user@example.com
  python grant.py debug --email user@example.com

Auth:
  - Reads LICENSE_SECRET from env by default
  - Or pass --secret explicitly

Server:
  - Reads LICENSE_SERVER_URL from env by default
  - Falls back to production URL
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


def _auth_headers(secret: str) -> dict:
    return {"Authorization": f"Bearer {secret}"}


def _pretty(obj) -> str:
    try:
        return json.dumps(obj, indent=2, sort_keys=True)
    except Exception:
        return str(obj)


def _request_json(method: str, url: str, **kwargs):
    r = requests.request(method, url, timeout=30, **kwargs)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    return r.status_code, data


def cmd_grant(args):
    secret = _secret(args)
    if not secret:
        raise SystemExit("Missing LICENSE_SECRET. Set env or pass --secret.")

    body = {
        "email": args.email,
        "appId": args.app_id,
        "tier": args.tier,
    }
    status, data = _request_json(
        "POST",
        f"{_server(args)}/api/license/admin/grant",
        headers=_auth_headers(secret),
        json=body,
    )
    print(_pretty(data))
    if status >= 300:
        raise SystemExit(f"Grant failed with HTTP {status}")


def cmd_revoke(args):
    secret = _secret(args)
    if not secret:
        raise SystemExit("Missing LICENSE_SECRET. Set env or pass --secret.")

    body = {
        "email": args.email,
        "appId": args.app_id,
    }
    status, data = _request_json(
        "POST",
        f"{_server(args)}/api/license/admin/revoke",
        headers=_auth_headers(secret),
        json=body,
    )
    print(_pretty(data))
    if status >= 300:
        raise SystemExit(f"Revoke failed with HTTP {status}")


def cmd_status(args):
    body = {
        "email": args.email,
        "appId": args.app_id,
    }
    status, data = _request_json(
        "POST",
        f"{_server(args)}/api/license/status",
        json=body,
    )
    print(_pretty(data))
    if status >= 300:
        raise SystemExit(f"Status lookup failed with HTTP {status}")


def cmd_debug(args):
    body = {
        "email": args.email,
        "appId": args.app_id,
    }
    status, data = _request_json(
        "POST",
        f"{_server(args)}/api/license/debug",
        json=body,
    )
    print(_pretty(data))
    if status >= 300:
        raise SystemExit(f"Debug lookup failed with HTTP {status}")


def main():
    parser = argparse.ArgumentParser(description="Admin helper for license grant/revoke/status.")
    parser.add_argument("--server", default=None, help="License server base URL")
    parser.add_argument("--secret", default=None, help="Admin bearer secret (LICENSE_SECRET)")

    sub = parser.add_subparsers(dest="cmd", required=True)

    grant = sub.add_parser("grant", help="Grant a license to an email")
    grant.add_argument("--email", required=True)
    grant.add_argument("--tier", default="monthly", choices=["monthly", "annual", "pro_monthly", "pro_annual"])
    grant.add_argument("--app-id", default=DEFAULT_APP_ID)
    grant.set_defaults(func=cmd_grant)

    revoke = sub.add_parser("revoke", help="Revoke a license from an email")
    revoke.add_argument("--email", required=True)
    revoke.add_argument("--app-id", default=DEFAULT_APP_ID)
    revoke.set_defaults(func=cmd_revoke)

    status = sub.add_parser("status", help="Check license status for an email")
    status.add_argument("--email", required=True)
    status.add_argument("--app-id", default=DEFAULT_APP_ID)
    status.set_defaults(func=cmd_status)

    debug = sub.add_parser("debug", help="Run deep activation debug for an email")
    debug.add_argument("--email", required=True)
    debug.add_argument("--app-id", default=DEFAULT_APP_ID)
    debug.set_defaults(func=cmd_debug)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
