#!/usr/bin/env python3
"""
deploy_to_render.py — Alien AI Trader
Reads your API keys from the environment (loaded from keys.bat),
finds your Render dashboard service, pushes all keys as environment
variables, and triggers a redeploy. The AI trading engine runs inside
the dashboard service — there is no separate worker service.

Requires:
    RENDER_API_KEY in your environment (add to keys.bat)

Usage:
    python deploy_to_render.py            # full deploy
    python deploy_to_render.py --check    # just show key status, no deploy
    python deploy_to_render.py --status   # show service status on Render

Built by Troy Walker of T-Dub's Apps — 2026
"""

import os
import sys
import json
import time
import requests
import webbrowser

# ── Render API config ────────────────────────────────────────────────────────
RENDER_API      = "https://api.render.com/v1"
DASHBOARD_NAME  = "alien-ai-trader-dashboard"
RENDER_DASH_URL = "https://dashboard.render.com"

# All keys pushed to the dashboard service (the engine runs inside it)
SHARED_KEYS = [
    "ALPACA_KEY",
    "ALPACA_SECRET",
    "ALPACA_BASE_URL",
    "ALPHA_VANTAGE_KEY",
    "PUSHBULLET_API_KEY",
    "PUSHOVER_TOKEN",
    "PUSHOVER_USER",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_FROM_NUMBER",
    "TWILIO_TO_NUMBER",
]

# Dashboard / engine settings
DASHBOARD_ONLY_KEYS = [
    "FLASK_SECRET",
    "ALLOWED_ORIGINS",
    "RUN_SECONDS",
    "HEARTBEAT_EVERY_SECONDS",
]

# No separate worker service anymore — the engine was integrated into the
# dashboard process in 2026-06 to cut Render costs.
WORKER_ONLY_KEYS = []


# ── Terminal colors ──────────────────────────────────────────────────────────
class C:
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    RED    = "\033[91m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RESET  = "\033[0m"

def ok(msg):    print(f"  {C.GREEN}✔{C.RESET}  {msg}")
def info(msg):  print(f"  {C.CYAN}ℹ{C.RESET}  {msg}")
def warn(msg):  print(f"  {C.YELLOW}⚠{C.RESET}  {msg}")
def err(msg):   print(f"  {C.RED}✖{C.RESET}  {msg}")
def dim(msg):   print(f"  {C.DIM}{msg}{C.RESET}")
def head(msg):  print(f"\n{C.BOLD}{C.CYAN}  {'═'*58}\n  {msg}\n  {'═'*58}{C.RESET}\n")
def sub(msg):   print(f"\n  {C.YELLOW}── {msg} ──{C.RESET}")


# ── Render API helpers ───────────────────────────────────────────────────────
def _headers():
    key = os.environ.get("RENDER_API_KEY", "").strip()
    if not key:
        err("RENDER_API_KEY not set.")
        print(f"""
  {C.YELLOW}How to get your Render API key:{C.RESET}
    1. Log in at https://dashboard.render.com
    2. Click your profile icon (top-right) → Account Settings
    3. Click  API Keys  → Create API Key
    4. Copy the key — it starts with  rnd_...
    5. Add this line to your keys.bat file:
         {C.CYAN}set RENDER_API_KEY=rnd_xxxxxxxxxxxxxxxxxxxx{C.RESET}
    6. Re-run ONE_CLICK_INSTALL.bat
""")
        sys.exit(1)
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }


def render_get(path):
    try:
        r = requests.get(f"{RENDER_API}{path}", headers=_headers(), timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as e:
        warn(f"Render API error {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        warn(f"Network error: {e}")
        return None


def render_put(path, payload):
    try:
        r = requests.put(f"{RENDER_API}{path}", headers=_headers(), json=payload, timeout=30)
        return r.status_code == 200, r
    except Exception as e:
        return False, None


def render_post(path, payload=None):
    try:
        r = requests.post(f"{RENDER_API}{path}", headers=_headers(), json=payload or {}, timeout=30)
        return r.status_code in [200, 201], r
    except Exception as e:
        return False, None


# ── Service discovery ────────────────────────────────────────────────────────
def find_service(name):
    """Returns (service_id, service_url) or (None, None)."""
    data = render_get(f"/services?name={requests.utils.quote(name)}&limit=20")
    if not data:
        return None, None
    for item in data:
        svc = item.get("service", item)
        if svc.get("name") == name:
            url = svc.get("serviceDetails", {}).get("url", "")
            return svc.get("id"), url
    return None, None


def get_service_status(service_id):
    data = render_get(f"/services/{service_id}")
    if data:
        svc = data.get("service", data)
        return svc.get("suspended", "unknown"), svc.get("serviceDetails", {}).get("url", "")
    return "unknown", ""


# ── Env-var management ───────────────────────────────────────────────────────
def get_existing_env_vars(service_id):
    """Returns {key: value} dict of current env vars on the service."""
    data = render_get(f"/services/{service_id}/env-vars")
    if not data:
        return {}
    result = {}
    for item in data:
        ev = item.get("envVar", item)
        if "key" in ev:
            result[ev["key"]] = ev.get("value", "")
    return result


def push_env_vars(service_id, new_keys: dict, service_label: str):
    """
    Merges new_keys into the existing env vars on the service
    and PUTs the merged set back (Render's PUT replaces ALL env vars).
    Only non-empty values are pushed to avoid wiping existing settings.
    """
    existing = get_existing_env_vars(service_id)
    info(f"  {service_label}: {len(existing)} existing env vars on Render")

    merged = dict(existing)
    pushed = 0
    for k, v in new_keys.items():
        if v:
            if merged.get(k) != v:
                merged[k] = v
                pushed += 1
            # else: value unchanged, no-op

    if pushed == 0:
        ok(f"  {service_label}: all keys already up to date — no changes needed")
        return True

    payload = [{"key": k, "value": v} for k, v in merged.items()]
    success, resp = render_put(f"/services/{service_id}/env-vars", payload)
    if success:
        ok(f"  {service_label}: {pushed} key(s) updated ({len(merged)} total)")
    else:
        warn(f"  {service_label}: env var update failed")
        if resp:
            dim(f"  HTTP {resp.status_code}: {resp.text[:200]}")
    return success


# ── Deploy trigger ───────────────────────────────────────────────────────────
def trigger_deploy(service_id, service_label):
    success, resp = render_post(f"/services/{service_id}/deploys",
                                {"clearCache": "do_not_clear"})
    if success:
        deploy_id = ""
        try:
            deploy_id = resp.json().get("id", "")[:14]
        except Exception:
            pass
        ok(f"  {service_label}: deploy triggered  {C.DIM}(id: {deploy_id}){C.RESET}")
    else:
        warn(f"  {service_label}: deploy trigger failed — redeploy manually in Render dashboard")
    return success


# ── Check mode ───────────────────────────────────────────────────────────────
def check_keys():
    head("Key Status Check")
    all_keys = SHARED_KEYS + DASHBOARD_ONLY_KEYS + WORKER_ONLY_KEYS
    missing = []
    for k in all_keys:
        v = os.environ.get(k, "")
        if v:
            masked = v[:4] + "****" + v[-2:] if len(v) > 8 else "****"
            print(f"    {C.GREEN}✔{C.RESET}  {k:<30} {C.DIM}{masked}{C.RESET}")
        else:
            print(f"    {C.YELLOW}⚠{C.RESET}  {k:<30} {C.DIM}(not set){C.RESET}")
            missing.append(k)
    print()
    if missing:
        warn(f"{len(missing)} key(s) not set. Run the setup wizard to add them:")
        dim("  Double-click RUN-SETUP-WIZARD.bat")
    else:
        ok("All keys are set!")
    print()


# ── Status mode ──────────────────────────────────────────────────────────────
def show_status():
    head("Render Service Status")
    for name in [DASHBOARD_NAME]:
        sid, url = find_service(name)
        if sid:
            status, _ = get_service_status(sid)
            status_str = f"{C.GREEN}active{C.RESET}" if status == "not_suspended" else f"{C.YELLOW}{status}{C.RESET}"
            print(f"    {C.CYAN}{name}{C.RESET}")
            print(f"      ID:     {sid}")
            print(f"      URL:    {url or '(no URL yet)'}")
            print(f"      State:  {status_str}")
        else:
            print(f"    {C.YELLOW}⚠  {name}: not found on Render{C.RESET}")
        print()


# ── First-time setup guidance ─────────────────────────────────────────────────
def first_time_setup_guide():
    print(f"""
  {C.YELLOW}No Render services found yet. First-time setup is needed:{C.RESET}

  {C.BOLD}Step 1: Connect your GitHub repo to Render{C.RESET}
    1. Log in at  https://dashboard.render.com
    2. Click  "New +"  →  "Blueprint"
    3. Connect your GitHub account if prompted
    4. Select the repo:  T-Dubs-Apps/Alien-AI-Trader
    5. Click  "Apply"  — Render reads render.yaml and creates the service:
         • alien-ai-trader-dashboard  (web service — AI engine runs inside it)

  {C.BOLD}Step 2: Re-run ONE_CLICK_INSTALL.bat{C.RESET}
    After the services are created, this script will automatically
    push your API keys and trigger the first deploy.

  {C.DIM}Note: You only do this once. After setup, every run of
  ONE_CLICK_INSTALL.bat pushes fresh keys and re-deploys automatically.{C.RESET}
""")
    open_render = input("  Open Render Blueprints page now? (Y/n): ").strip().lower()
    if open_render not in ("n", "no"):
        webbrowser.open("https://dashboard.render.com/blueprints")


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    if sys.platform == "win32":
        os.system("color")  # enable ANSI color on Windows

    args = sys.argv[1:]

    if "--check" in args:
        check_keys()
        return

    head("Alien AI Trader — Render Deployment")

    # Validate RENDER_API_KEY (will exit with instructions if missing)
    key = os.environ.get("RENDER_API_KEY", "").strip()
    masked = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
    ok(f"RENDER_API_KEY loaded  {C.DIM}({masked}){C.RESET}")

    if "--status" in args:
        show_status()
        return

    # ── Collect user's API keys from environment ─────────────────────────────
    sub("Reading your API keys from environment")
    all_user_keys = {}
    for k in SHARED_KEYS + DASHBOARD_ONLY_KEYS + WORKER_ONLY_KEYS:
        v = os.environ.get(k, "")
        if v:
            all_user_keys[k] = v

    info(f"Found {len(all_user_keys)} key(s) to push")

    # ── Find the dashboard service on Render ─────────────────────────────────
    sub("Locating Render service")
    dash_id, dash_url = find_service(DASHBOARD_NAME)

    if not dash_id:
        err("No service found on Render.")
        first_time_setup_guide()
        sys.exit(0)

    ok(f"Dashboard:  {DASHBOARD_NAME}")
    if dash_url:
        dim(f"            {dash_url}")

    # ── Push environment variables ────────────────────────────────────────────
    sub("Pushing API keys to Render")
    dash_keys = {k: all_user_keys[k] for k in SHARED_KEYS + DASHBOARD_ONLY_KEYS if k in all_user_keys}
    push_env_vars(dash_id, dash_keys, "Dashboard")

    # ── Trigger deploy ────────────────────────────────────────────────────────
    sub("Triggering redeploy")
    trigger_deploy(dash_id, "Dashboard")

    # ── Summary ───────────────────────────────────────────────────────────────
    live_url = dash_url or "https://alien-ai-trader-dashboard.onrender.com"
    print(f"""
  {C.BOLD}{C.GREEN}  ╔══════════════════════════════════════════════════════════╗
  ║  ✦  Deployment triggered! Your service is rebuilding.    ║
  ╚══════════════════════════════════════════════════════════╝{C.RESET}

  {C.CYAN}Dashboard URL:   {live_url}{C.RESET}
  {C.CYAN}Render console:  https://dashboard.render.com{C.RESET}

  {C.YELLOW}Build time: ~3–5 minutes (first deploy) or ~1 min (redeploy){C.RESET}
  {C.YELLOW}Free tier services spin down after 15 min of inactivity.{C.RESET}
  {C.DIM}First page load after spin-down takes ~30 seconds — that's normal.{C.RESET}
""")


if __name__ == "__main__":
    main()
