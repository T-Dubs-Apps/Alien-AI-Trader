#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║           ALIEN AI TRADER — SETUP WIZARD v1.0                  ║
║           Built by Troy Walker of T-Dub's Apps — 2026          ║
╚══════════════════════════════════════════════════════════════════╝

Run this FIRST before anything else.
This wizard will walk you through registering for each service,
collecting your API keys, and writing them to keys.bat automatically.
"""

import os
import sys
import time
import webbrowser
import re

# Force UTF-8 so the wizard's emoji/box characters can never crash on Windows.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Terminal colors ──────────────────────────────────────────────
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    CYAN    = "\033[96m"
    RED     = "\033[91m"
    MAGENTA = "\033[95m"
    WHITE   = "\033[97m"
    DIM     = "\033[2m"

def banner():
    print(f"""
{C.CYAN}{C.BOLD}
 ▄▄▄       ██▓     ██▓▓█████  ███▄    █     ▄▄▄       ██▓   ████████╗██████╗  █████╗ ██████╗ ███████╗██████╗
{C.MAGENTA} ████▄    ▓██▒    ▓██▒▓█   ▀  ██ ▀█   █    ▒████▄    ▓██▒   ╚══██╔══╝██╔══██╗██╔══██╗██╔══██╗██╔════╝██╔══██╗
{C.CYAN} ██▒ ▀█▒  ▒██░    ▒██▒▒███   ▓██  ▀█ ██▒   ▒██  ▀█▒  ▒██░      ██║   ██████╔╝███████║██║  ██║█████╗  ██████╔╝
{C.MAGENTA} ▒██░▄▄▄░  ▒██░    ░██░▒▓█  ▄ ▓██▒  ▐▌██▒   ▒██░▄▄▄░  ▒██░      ██║   ██╔══██╗██╔══██║██║  ██║██╔══╝  ██╔══██╗
{C.CYAN} ░▓█  ██▓ ░██████▒░██░░▒████▒▒██░   ▓██░   ░▓█  ██▓ ░██████▒   ██║   ██║  ██║██║  ██║██████╔╝███████╗██║  ██║
{C.RESET}
{C.YELLOW}{'─' * 70}
  SETUP WIZARD  —  Get your keys, set your path, launch your ship 🛸
{'─' * 70}{C.RESET}
""")

def step_header(step: int, total: int, title: str, emoji: str):
    print(f"\n{C.BOLD}{C.CYAN}{'═' * 60}{C.RESET}")
    print(f"{C.BOLD}{C.YELLOW}  STEP {step} of {total}  {emoji}  {title}{C.RESET}")
    print(f"{C.CYAN}{'═' * 60}{C.RESET}\n")

def info(msg):    print(f"  {C.CYAN}ℹ  {C.RESET}{msg}")
def success(msg): print(f"  {C.GREEN}✔  {C.RESET}{msg}")
def warn(msg):    print(f"  {C.YELLOW}⚠  {C.RESET}{msg}")
def error(msg):   print(f"  {C.RED}✖  {C.RESET}{msg}")
def tip(msg):     print(f"  {C.MAGENTA}💡 {C.RESET}{msg}")

def prompt(label: str, secret: bool = False, optional: bool = False) -> str:
    tag = f"{C.DIM}(optional){C.RESET} " if optional else ""
    while True:
        val = input(f"  {C.BOLD}{C.WHITE}➜ {label}: {tag}{C.RESET}").strip()
        if val:
            return val
        if optional:
            return ""
        warn("This field is required. Please enter a value.")

def open_url(url: str):
    info(f"Opening: {C.CYAN}{url}{C.RESET}")
    try:
        webbrowser.open(url)
        time.sleep(1)
    except Exception:
        warn(f"Could not auto-open browser. Please visit manually:\n    {url}")

def pause(msg="  Press ENTER when you're ready to continue..."):
    input(f"\n{C.DIM}{msg}{C.RESET}")

def validate_phone(number: str) -> bool:
    """Basic E.164 format check: +1XXXXXXXXXX"""
    return bool(re.match(r"^\+\d{10,15}$", number))

def offer_skip(service: str, why: str) -> bool:
    """Optional services can be skipped — the app works without them.
    Returns True if the user wants to set the service up now."""
    print(f"  {C.DIM}{why}{C.RESET}")
    ans = input(f"  {C.BOLD}{C.WHITE}➜ Set up {service} now? [Y/n] (ENTER = yes, n = skip): {C.RESET}").strip().lower()
    if ans in ("n", "no", "skip"):
        warn(f"{service} skipped — you can add it later via LAUNCH.bat → [3] Setup Keys.")
        return False
    return True

# ════════════════════════════════════════════════════════════════
#  SERVICE COLLECTORS
# ════════════════════════════════════════════════════════════════

def collect_alpaca(keys: dict):
    step_header(1, 6, "Alpaca Markets — Stock Trading API", "📈")
    print(f"""  {C.WHITE}Alpaca provides commission-free stock trading and market data.
  Alpaca gives you TWO separate key pairs — you can set up both here once:{C.RESET}

    {C.GREEN}• PAPER keys{C.RESET}  practice money — instant, free, zero risk.  {C.BOLD}Required.{C.RESET}
    {C.YELLOW}• LIVE keys{C.RESET}   real money — optional now. Needed only when you flip
                    the app to Live trading (after your license activates).

  {C.WHITE}How to get them:{C.RESET}
    1. Create a free account at alpaca.markets
    2. PAPER: Dashboard → switch to "Paper Trading" → API Keys → Generate
    3. LIVE:  Dashboard → switch to "Live Trading"  → API Keys → Generate
    4. {C.YELLOW}⚠  Copy each Secret Key immediately — it is shown only once!{C.RESET}

  {C.DIM}Live accounts may require identity verification (up to a week). You can
  add live keys now or anytime later via LAUNCH.bat → [3] Setup Keys.{C.RESET}
""")
    open_url("https://app.alpaca.markets/signup")
    pause("  Press ENTER once you have your Alpaca PAPER API Key and Secret...")

    # Paper keys are always required — the app always BOOTS in safe paper mode.
    keys["ALPACA_KEY"]    = prompt("Alpaca PAPER API Key ID")
    keys["ALPACA_SECRET"] = prompt("Alpaca PAPER Secret Key")
    # The in-app Paper↔Live toggle controls the account at runtime, so we always
    # start on the paper endpoint regardless of whether live keys are present.
    keys["ALPACA_BASE_URL"] = "https://paper-api.alpaca.markets"
    success("Paper keys saved — the app starts in safe PAPER mode.")

    # Live keys are optional and collected once so the buyer never returns to Alpaca.
    print(f"\n  {C.WHITE}Add your LIVE (real-money) keys now?{C.RESET}")
    print(f"    {C.DIM}You switch to real money later with the in-app Paper→Live toggle")
    print(f"    (only works once your license is active). Add the keys now so it's a")
    print(f"    single click later, or skip and add them anytime.{C.RESET}")
    ans = input(f"  {C.BOLD}{C.WHITE}➜ Enter live keys now? [y/N] (ENTER = skip): {C.RESET}").strip().lower()
    if ans in ("y", "yes"):
        keys["ALPACA_LIVE_KEY"]    = prompt("Alpaca LIVE API Key ID")
        keys["ALPACA_LIVE_SECRET"] = prompt("Alpaca LIVE Secret Key")
        warn("Live keys saved. The app STILL starts in paper — you flip to live")
        warn("inside the app (Settings), and only with an active license.")
    else:
        info("Skipped live keys — add them anytime via LAUNCH.bat → [3] Setup Keys.")

    success("Alpaca setup complete!")


def collect_alpha_vantage(keys: dict):
    step_header(2, 6, "Alpha Vantage — Market Data & Stock Info", "📊")
    print(f"""  {C.WHITE}Alpha Vantage provides free stock market data, indicators,
  and fundamental data. Registration is instant.{C.RESET}

    1. Visit alphavantage.co
    2. Click "Get Free API Key"
    3. Fill out the short form (name, email, use case)
    4. Your key is shown immediately — copy it

  {C.DIM}Free tier: 25 requests/day, 5 requests/minute{C.RESET}
""")
    open_url("https://www.alphavantage.co/support/#api-key")
    pause("  Press ENTER once you have your Alpha Vantage key...")

    keys["ALPHA_VANTAGE_KEY"] = prompt("Alpha Vantage API Key")
    success("Alpha Vantage key saved!")


def collect_pushover(keys: dict):
    step_header(3, 6, "Pushover — Push Notifications (Optional)", "🔔")
    if not offer_skip("Pushover", "Optional: phone push alerts. The app trades fine without it."):
        return
    print(f"""  {C.WHITE}Pushover sends real-time push notifications to your phone
  for trade alerts and app events.{C.RESET}

    1. Create an account at pushover.net
    2. Your {C.YELLOW}User Key{C.RESET} is shown on your dashboard (top right)
    3. Scroll down → click "Create an Application/API Token"
    4. Name it "Alien AI Trader", submit
    5. Copy the {C.YELLOW}API Token/Key{C.RESET} from the app page

  {C.DIM}One-time $4.99 app purchase required for long-term use (30-day free trial){C.RESET}
""")
    open_url("https://pushover.net/login")
    pause("  Press ENTER once you have your Pushover User Key and App Token...")

    keys["PUSHOVER_USER"]  = prompt("Pushover User Key")
    keys["PUSHOVER_TOKEN"] = prompt("Pushover App API Token")
    success("Pushover keys saved!")


def collect_twilio(keys: dict):
    step_header(4, 6, "Twilio — SMS Text Alerts (Optional)", "📱")
    if not offer_skip("Twilio", "Optional: SMS/phone-call alerts. The app trades fine without it."):
        return
    print(f"""  {C.WHITE}Twilio sends SMS text message alerts for trades and events.{C.RESET}

    1. Sign up at twilio.com (free trial includes credits)
    2. From the Console Dashboard, copy:
         • {C.YELLOW}Account SID{C.RESET}
         • {C.YELLOW}Auth Token{C.RESET} (click the eye icon to reveal)
    3. Go to Phone Numbers → Manage → Buy a Number
         • Search for a US number, buy it (~$1/month)
         • This is your FROM number
    4. Verify your personal cell number under "Verified Caller IDs"
         • This is your TO number (required for trial accounts)
""")
    open_url("https://www.twilio.com/try-twilio")
    pause("  Press ENTER once you have your Twilio credentials...")

    keys["TWILIO_ACCOUNT_SID"]  = prompt("Twilio Account SID")
    keys["TWILIO_AUTH_TOKEN"]   = prompt("Twilio Auth Token")

    print(f"\n  {C.DIM}Phone numbers must be in E.164 format: +1XXXXXXXXXX{C.RESET}")

    while True:
        from_num = prompt("Twilio FROM Number (your Twilio number, e.g. +15551234567)")
        if validate_phone(from_num):
            keys["TWILIO_FROM_NUMBER"] = from_num
            break
        error("Invalid format. Use E.164 format like +15551234567")

    while True:
        to_num = prompt("Twilio TO Number (your personal cell, e.g. +15559876543)")
        if validate_phone(to_num):
            keys["TWILIO_TO_NUMBER"] = to_num
            break
        error("Invalid format. Use E.164 format like +15559876543")

    success("Twilio credentials saved!")


def collect_render(keys: dict):
    step_header(5, 6, "Render — Cloud Deployment API Key (Optional)", "☁")
    print(f"""  {C.WHITE}Render is the cloud platform that hosts your dashboard
  (the AI trading engine runs inside it) 24/7 without your PC being on.{C.RESET}

  {C.YELLOW}Why you need a Render API key:{C.RESET}
    Without it you can still run Alien AI Trader locally.
    With it, ONE_CLICK_INSTALL.bat automatically pushes your Alpaca,
    Alpha Vantage, and alert keys to Render and triggers a redeploy —
    no manual copy-paste in the Render dashboard required.

    1. Log in at render.com (free account is sufficient)
    2. Click your profile icon (top-right) → Account Settings
    3. Click  {C.YELLOW}API Keys{C.RESET}  →  Create API Key
    4. Name it "Alien AI Trader", click Create
    5. Copy the key that starts with  {C.YELLOW}rnd_{C.RESET}...
       {C.RED}⚠ It only shows once — copy it immediately!{C.RESET}

  {C.DIM}First-time Render setup: after getting the key, go to
  dashboard.render.com/blueprints → New Blueprint Instance →
  connect your GitHub repo → Apply.  This creates the single
  dashboard service from render.yaml automatically.{C.RESET}
""")
    open_url("https://dashboard.render.com/account/api-keys")
    render_key = input(f"  {C.BOLD}{C.WHITE}➜ Render API Key (press ENTER to skip): {C.RESET}").strip()
    if render_key:
        keys["RENDER_API_KEY"] = render_key
        success("Render API key saved!")
    else:
        warn("Skipped — you can add RENDER_API_KEY to keys.bat manually later.")


def collect_pushbullet(keys: dict):
    step_header(6, 6, "Pushbullet — Device Sync & Notifications (Optional)", "🔗")
    if not offer_skip("Pushbullet", "Optional: syncs alerts across devices. The app trades fine without it."):
        return
    print(f"""  {C.WHITE}Pushbullet syncs notifications across your devices.{C.RESET}

    1. Sign in at pushbullet.com (use Google or email)
    2. Go to: Settings → Account
    3. Scroll to "Access Tokens" → click "Create Access Token"
    4. Copy the token shown

  {C.DIM}Free tier is sufficient for this app's usage.{C.RESET}
""")
    open_url("https://www.pushbullet.com/#settings/account")
    pause("  Press ENTER once you have your Pushbullet Access Token...")

    keys["PUSHBULLET_API_KEY"] = prompt("Pushbullet Access Token")
    success("Pushbullet key saved!")


# ════════════════════════════════════════════════════════════════
#  FILE WRITERS
# ════════════════════════════════════════════════════════════════

def write_keys_bat(keys: dict):
    """Write keys.bat for local Windows use."""
    lines = [
        "@echo off",
        "REM --------------------------------------------------------",
        "REM  Alien AI Trader -- Environment Variables",
        "REM  Generated by setup_wizard.py",
        "REM  DO NOT share or commit this file!",
        "REM --------------------------------------------------------",
        "",
    ]
    for k, v in keys.items():
        lines.append(f'set {k}={v}')
    lines.append("")
    lines.append("echo Environment variables loaded successfully.")

    with open("keys.bat", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    success("keys.bat written successfully.")


def write_env_file(keys: dict):
    """Write .env file as a fallback for Python dotenv usage."""
    lines = [
        "# Alien AI Trader -- Environment Variables",
        "# Generated by setup_wizard.py",
        "# DO NOT share or commit this file!",
        "",
    ]
    for k, v in keys.items():
        lines.append(f"{k}={v}")

    with open(".env", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    success(".env file written successfully.")


def print_render_instructions(keys: dict):
    """Print a clean copy-paste block for Render deployment."""
    print(f"""
{C.BOLD}{C.CYAN}{'═' * 60}
  RENDER DEPLOYMENT — Environment Variables
{'═' * 60}{C.RESET}

  In your Render dashboard:
    1. Go to your {C.YELLOW}Web Service{C.RESET} → Environment → Add Secret File
       {C.DIM}OR{C.RESET} use Environment Variables for each key below
       {C.DIM}(One service is all there is — the AI engine runs inside it.){C.RESET}

  {C.WHITE}Copy these key=value pairs:{C.RESET}
""")
    for k, v in keys.items():
        print(f"    {C.YELLOW}{k}{C.RESET}={C.GREEN}{v}{C.RESET}")

    print(f"""
  {C.DIM}Tip: In Render, use "Secret Files" with a .env file
  for cleaner management of multiple keys.{C.RESET}
""")


def print_gitignore_reminder():
    print(f"""
{C.BOLD}{C.RED}  ⚠  SECURITY REMINDER{C.RESET}
{C.DIM}  Make sure these files are in your .gitignore:{C.RESET}

    keys.bat
    .env

  {C.DIM}Never commit API keys to GitHub!{C.RESET}
""")


# ════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════

def main():
    # Windows color support
    if sys.platform == "win32":
        os.system("color")

    banner()

    print(f"""  {C.WHITE}Welcome! Let's get you trading in about 2 minutes.{C.RESET}

  You only need {C.YELLOW}ONE free account: Alpaca{C.RESET} (your brokerage).
  We'll also grab a {C.YELLOW}free market-data key{C.RESET} — it takes about
  60 seconds and the page opens for you automatically.

    {C.GREEN}Step 1{C.RESET}  Your Alpaca keys  (Paper = practice money, or Live)
    {C.GREEN}Step 2{C.RESET}  A free Alpha Vantage data key  (one click)

  {C.DIM}That's it — everything else is optional and can be skipped.
  Tip: choose Paper Trading to start instantly with practice money.{C.RESET}
""")
    pause("  Press ENTER to begin...")

    keys = {}

    try:
        collect_alpaca(keys)
        collect_alpha_vantage(keys)

        # Everything below is OPTIONAL — text/push alerts and cloud deploy.
        # Regular users should just press ENTER to skip it.
        ans = input(
            f"\n  {C.BOLD}{C.WHITE}➜ Set up optional text/push alerts? "
            f"(most users press ENTER to skip) [y/N]: {C.RESET}"
        ).strip().lower()
        if ans == "y":
            collect_pushover(keys)
            collect_twilio(keys)
            collect_render(keys)
            collect_pushbullet(keys)
    except KeyboardInterrupt:
        print(f"\n\n{C.YELLOW}  Setup interrupted. Saving what we have so far...{C.RESET}\n")

    if not keys:
        error("No keys were entered. Exiting without saving.")
        sys.exit(1)

    # ── Write output files ──────────────────────────────────────
    print(f"\n{C.BOLD}{C.CYAN}{'═' * 60}")
    print(f"  SAVING YOUR CONFIGURATION")
    print(f"{'═' * 60}{C.RESET}\n")

    write_keys_bat(keys)
    write_env_file(keys)
    # Render deploy block is only relevant if the user set up a Render key (advanced).
    if keys.get("RENDER_API_KEY"):
        print_render_instructions(keys)
    print_gitignore_reminder()

    # ── Final summary (end-user friendly) ───────────────────────
    base = keys.get("ALPACA_BASE_URL", "")
    mode = "PAPER (practice money)" if ("paper" in base or not base) else "LIVE (real money)"
    print(f"""{C.BOLD}{C.GREEN}
  ✦ All set! You're ready to trade in {C.YELLOW}{mode}{C.GREEN}.
{C.RESET}
  {C.WHITE}To start the app:{C.RESET}
    1. Double-click {C.YELLOW}START.bat{C.RESET}
    2. Your dashboard opens at {C.CYAN}http://localhost:5000{C.RESET}

  {C.DIM}You can switch between Paper and Live anytime in Settings.
  Reminder: trading carries real risk — only trade what you can afford to lose.{C.RESET}

{C.YELLOW}  Good luck, Commander! 🛸{C.RESET}
""")


if __name__ == "__main__":
    main()
