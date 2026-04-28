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

# ════════════════════════════════════════════════════════════════
#  SERVICE COLLECTORS
# ════════════════════════════════════════════════════════════════

def collect_alpaca(keys: dict):
    step_header(1, 5, "Alpaca Markets — Stock Trading API", "📈")
    print(f"""  {C.WHITE}Alpaca provides commission-free stock trading and market data.
  You will need to:{C.RESET}

    1. Create a free account at alpaca.markets
    2. Go to your Dashboard → Paper Trading (for testing) or Live Trading
    3. Navigate to: API Keys → Generate New Key
    4. {C.YELLOW}⚠  IMPORTANT: Copy your Secret Key immediately — it won't show again!{C.RESET}

  {C.DIM}Note: Live trading accounts may require identity verification
  which can take up to a week. Paper trading is instant.{C.RESET}
""")
    open_url("https://app.alpaca.markets/signup")
    pause("  Press ENTER once you have your Alpaca API Key and Secret...")

    keys["ALPACA_KEY"]    = prompt("Alpaca API Key ID")
    keys["ALPACA_SECRET"] = prompt("Alpaca Secret Key")

    # Detect paper vs live
    print(f"\n  {C.WHITE}Are you using Paper Trading (test) or Live Trading?{C.RESET}")
    print(f"    {C.DIM}1{C.RESET} = Paper Trading (recommended to start)")
    print(f"    {C.DIM}2{C.RESET} = Live Trading")
    choice = input(f"  {C.BOLD}{C.WHITE}➜ Enter 1 or 2: {C.RESET}").strip()
    if choice == "2":
        keys["ALPACA_BASE_URL"] = "https://api.alpaca.markets"
        warn("Live trading selected — real money will be used!")
    else:
        keys["ALPACA_BASE_URL"] = "https://paper-api.alpaca.markets"
        success("Paper trading selected — safe for testing.")

    success("Alpaca keys saved!")


def collect_alpha_vantage(keys: dict):
    step_header(2, 5, "Alpha Vantage — Market Data & Stock Info", "📊")
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
    step_header(3, 5, "Pushover — Push Notifications", "🔔")
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
    step_header(4, 5, "Twilio — SMS Text Alerts", "📱")
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


def collect_pushbullet(keys: dict):
    step_header(5, 5, "Pushbullet — Device Sync & Notifications", "🔗")
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
    2. Repeat for your {C.YELLOW}Worker Service{C.RESET}

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

    print(f"""  {C.WHITE}Welcome to the Alien AI Trader Setup Wizard!{C.RESET}

  This wizard will:
    ✦ Open each registration page in your browser
    ✦ Walk you through finding your keys step by step
    ✦ Write your {C.YELLOW}keys.bat{C.RESET} and {C.YELLOW}.env{C.RESET} files automatically
    ✦ Show you exactly what to paste into Render

  {C.DIM}You'll need accounts on 5 services. Most are instant.
  Alpaca live trading may take up to a week for approval
  — use Paper Trading to get started immediately.{C.RESET}

  {C.YELLOW}Have a notepad ready to copy keys as you go!{C.RESET}
""")
    pause("  Press ENTER to begin the setup wizard...")

    keys = {}

    try:
        collect_alpaca(keys)
        collect_alpha_vantage(keys)
        collect_pushover(keys)
        collect_twilio(keys)
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
    print_render_instructions(keys)
    print_gitignore_reminder()

    # ── Final summary ───────────────────────────────────────────
    print(f"""{C.BOLD}{C.GREEN}
  ✦ Setup Complete! Here's what to do next:
{C.RESET}
  {C.WHITE}Local:{C.RESET}
    1. Run {C.YELLOW}SETUP.bat{C.RESET}
    2. Run {C.YELLOW}start-alien-ai-trader.bat{C.RESET}
    3. Open {C.CYAN}http://localhost:5000{C.RESET}

  {C.WHITE}Render:{C.RESET}
    1. Add the environment variables shown above
       to BOTH your web and worker services
    2. Trigger a manual deploy

  {C.WHITE}Your dashboard:{C.RESET}
    {C.CYAN}https://alien-ai-trader-dashboard.onrender.com{C.RESET}

{C.YELLOW}  Good luck trading, Commander! 🛸{C.RESET}
""")


if __name__ == "__main__":
    main()
