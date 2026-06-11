# AGENTS.md — Alien AI Trader

This file provides essential instructions and conventions for AI coding agents working in this codebase. It summarizes build, setup, and architecture details that are not easily discoverable from code alone. For full documentation, see [README.md](README.md).

---

## Quick Start
- **Install:** Run `INSTALL.ps1` with PowerShell (auto-installs Python 3.10+, creates `.venv`, installs dependencies)
- **Configure API Keys:** Run `LAUNCH.bat` and choose **[3] SETUP KEYS** (or run `python setup_wizard.py` directly) — writes `keys.bat`
- **Launch:** Run `START.bat` (activates venv, loads keys, starts the dashboard — the AI trading engine runs inside it)

## Build/Test/Run Commands
- **Install dependencies:** `INSTALL.ps1` (preferred) or manually: `python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt`
- **Run main app:** `START.bat` (preferred)
- **Run everything (dashboard + integrated engine):** `python dashboard.py`
- **Run trading engine only:** `python trading_engine.py`

## Project Structure
- **dashboard.py** — Flask web dashboard + integrated AI trading engine (single process)
- **trading_engine.py** — Main trading logic
- **legacy/worker.py** — Old standalone engine process (no longer used; engine was integrated into dashboard.py in 2026-06 to cut Render costs)
- **portfolio_ladder.py** — Portfolio scoring logic
- **config_loader.py** — Loads config from JSON/YAML
- **setup_wizard.py** — Interactive setup for API keys
- **render.yaml** — Render.com deployment blueprint
- **templates/dashboard.html** — Dashboard UI template

## Key Conventions
- **All settings are live-editable via dashboard UI** (no restart needed)
- **Paper trading is default**; live trading requires both `TRADING_MODE=live` and `LIVE_TRADING_ENABLED=true`
- **API keys are loaded from `keys.bat`** (auto-generated)
- **Environment variables** are required for cloud deployment (see README)
- **Trailing stop, stop-loss, and position sizing** are all configurable

## Common Pitfalls
- Missing or invalid API keys will prevent startup (use Setup Wizard)
- Python 3.10+ required (auto-installed by `INSTALL.ps1`)
- For Render deployment, set all required environment variables (see README)
- Do not edit `keys.bat` manually; always use the Setup Wizard

## Links
- [README.md](README.md) — Full documentation, setup, and architecture
- [QUICK SETUP.txt](QUICK%20SETUP.txt) — Short setup guide
- [Install istructions for Alien AI Trader.txt](Install%20istructions%20for%20Alien%20AI%20Trader.txt) — Additional install notes

---

This file is maintained for AI agent productivity. Update if conventions or architecture change.