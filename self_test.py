#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║         ALIEN AI TRADER — SELF-TEST & DIAGNOSTIC v1.0          ║
║         Built by Troy Walker of T-Dub's Apps — 2026            ║
╚══════════════════════════════════════════════════════════════════╝

Run this script to verify your installation is working correctly.

Usage:
    python self_test.py            # run all tests, show results
    python self_test.py --repair   # run tests and auto-repair issues found
    python self_test.py --quiet    # minimal output (exit code 0=pass, 1=fail)

Exit codes:
    0  All tests passed
    1  One or more tests failed
"""

import os
import sys
import subprocess
import importlib
import traceback
import json
import platform
from pathlib import Path

# ── Terminal colors (ANSI, disabled on Windows if not supported) ──────────────
_IS_WIN = sys.platform == "win32"
if _IS_WIN:
    os.system("color")  # enable ANSI on Windows 10+

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    CYAN    = "\033[96m"
    RED     = "\033[91m"
    MAGENTA = "\033[95m"
    DIM     = "\033[2m"


def _ok(msg):    print(f"  {C.GREEN}✔{C.RESET}  {msg}")
def _fail(msg):  print(f"  {C.RED}✖{C.RESET}  {msg}")
def _warn(msg):  print(f"  {C.YELLOW}⚠{C.RESET}  {msg}")
def _info(msg):  print(f"  {C.CYAN}ℹ{C.RESET}  {msg}")
def _head(msg):  print(f"\n{C.BOLD}{C.CYAN}  {'─'*56}\n  {msg}\n  {'─'*56}{C.RESET}")


# ── Base directory (where self_test.py lives) ─────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)

# ── Test results accumulator ──────────────────────────────────────────────────
RESULTS: list = []   # list of (name, passed: bool, detail: str, fix: callable|None)


def record(name: str, passed: bool, detail: str = "", fix=None):
    RESULTS.append((name, passed, detail, fix))
    if passed:
        _ok(name)
    else:
        _fail(f"{name}" + (f"  →  {detail}" if detail else ""))


# ══════════════════════════════════════════════════════════════════
#  SECTION 1 — PYTHON & RUNTIME
# ══════════════════════════════════════════════════════════════════

def test_python_version():
    major, minor = sys.version_info[:2]
    ok = major == 3 and minor >= 10
    detail = f"Python {major}.{minor} (need 3.10+)"

    def fix_python():
        print()
        _warn("Python 3.10+ is required. Install it from https://python.org")
        if _IS_WIN:
            _info("On Windows: run INSTALL.ps1 — it installs Python 3.12 automatically.")
        else:
            _info("On Mac: brew install python@3.12")
            _info("On Linux: sudo apt install python3.12 python3.12-venv")

    record("Python version (3.10+)", ok, detail, None if ok else fix_python)


def test_required_files():
    required = [
        "dashboard.py",
        "trading_engine.py",
        "worker.py",
        "portfolio_ladder.py",
        "forecasting.py",
        "config_loader.py",
        "setup_wizard.py",
        "crash_notifier.py",
        "ai_model.py",
        "news_sentiment.py",
        "dynamic_position.py",
        "license_api.py",
        "requirements.txt",
        "requirements-local.txt",
        "templates/dashboard.html",
        "LAUNCH.bat",
        "START.bat",
        "INSTALL.ps1",
    ]
    missing = [f for f in required if not (BASE_DIR / f).exists()]
    ok = len(missing) == 0
    detail = f"Missing: {', '.join(missing)}" if missing else f"All {len(required)} required files present"

    def fix_files():
        _warn("Some files are missing. Re-download the ZIP from GitHub:")
        _info("https://github.com/T-Dubs-Apps/Alien-AI-Trader/archive/refs/heads/main.zip")
        _info("Extract and re-run INSTALL.ps1 (Windows) or 'pip install -r requirements.txt' (Mac/Linux).")

    record("Required files present", ok, detail if not ok else "", None if ok else fix_files)


# ══════════════════════════════════════════════════════════════════
#  SECTION 2 — PYTHON PACKAGES
# ══════════════════════════════════════════════════════════════════

REQUIRED_PACKAGES = [
    ("flask",               "flask"),
    ("flask_cors",          "flask-cors"),
    ("flask_socketio",      "flask-socketio"),
    ("gevent",              "gevent"),
    ("requests",            "requests"),
    ("pandas",              "pandas"),
    ("numpy",               "numpy"),
    ("alpaca_trade_api",    "alpaca-trade-api"),
    ("alpha_vantage",       "alpha_vantage"),
    ("pushbullet",          "pushbullet.py"),
    ("twilio",              "twilio"),
    ("stripe",              "stripe"),
    ("gunicorn",            "gunicorn"),
]


def test_packages():
    missing_pkgs = []
    for import_name, pip_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing_pkgs.append(pip_name)

    ok = len(missing_pkgs) == 0
    detail = f"Missing: {', '.join(missing_pkgs)}" if missing_pkgs else f"All {len(REQUIRED_PACKAGES)} packages installed"

    def fix_packages():
        _info("Installing missing packages...")
        req = BASE_DIR / "requirements.txt"
        req_local = BASE_DIR / "requirements-local.txt"
        req_file = str(req_local) if req_local.exists() else str(req)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req_file, "--quiet"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            _ok("Packages installed successfully. Re-run self_test.py to verify.")
        else:
            _fail("Package install failed:")
            print(result.stderr[-1000:] if result.stderr else "(no output)")

    record("Python packages installed", ok, detail if not ok else "", None if ok else fix_packages)


# ══════════════════════════════════════════════════════════════════
#  SECTION 3 — MODULE IMPORTS & LOGIC
# ══════════════════════════════════════════════════════════════════

def test_module_imports():
    modules_to_test = [
        "config_loader",
        "forecasting",
        "ai_model",
        "news_sentiment",
        "dynamic_position",
        "crash_notifier",
    ]
    failed = []
    for mod in modules_to_test:
        try:
            importlib.import_module(mod)
        except Exception as e:
            failed.append(f"{mod}: {e}")

    ok = len(failed) == 0
    detail = "; ".join(failed) if failed else f"All {len(modules_to_test)} modules import cleanly"
    record("Core module imports", ok, detail if not ok else "")


def test_forecasting_logic():
    try:
        import pandas as pd
        from forecasting import get_forecast, linear_forecast, momentum_forecast

        # Upward trend: expect direction='up'
        up_closes = pd.Series([100.0 + i * 1.5 for i in range(35)])
        lf_up = linear_forecast(up_closes)
        assert isinstance(lf_up, dict), "linear_forecast must return dict"
        assert "direction" in lf_up and "confidence" in lf_up, "missing keys in linear_forecast"
        assert lf_up["direction"] == "up", f"rising series should forecast 'up', got '{lf_up['direction']}'"
        assert lf_up["confidence"] > 0.8, f"clean trend should have high confidence, got {lf_up['confidence']}"

        # Downward trend: expect direction='down'
        down_closes = pd.Series([200.0 - i * 1.5 for i in range(35)])
        lf_down = linear_forecast(down_closes)
        assert lf_down["direction"] == "down", \
            f"falling series should forecast 'down', got '{lf_down['direction']}'"

        # momentum_forecast on upward stacked series
        mf = momentum_forecast(up_closes)
        assert isinstance(mf, dict), "momentum_forecast must return dict"
        assert mf["phase"] in ("climbing", "falling", "consolidating", "unknown")
        assert mf["phase"] == "climbing", \
            f"strong uptrend should be 'climbing', got '{mf['phase']}'"

        # get_forecast (combined) — upward trend should score > 0
        gf = get_forecast(up_closes)
        assert isinstance(gf, dict), "get_forecast must return dict"
        assert "score" in gf, "missing 'score' key"
        assert 0.0 <= gf["score"] <= 25.0, f"score out of range: {gf['score']}"
        assert gf["score"] > 0, f"upward trend should score > 0, got {gf['score']}"
        assert gf["forecast_direction"] == "up", \
            f"upward trend should forecast 'up', got '{gf['forecast_direction']}'"

        # get_forecast — too few bars should return safe neutral defaults
        short_closes = pd.Series([100.0, 101.0, 102.0])
        gf_short = get_forecast(short_closes)
        assert 0.0 <= gf_short["score"] <= 25.0, "short series should return valid score"

        record("Forecasting logic", True)
    except Exception as e:
        record("Forecasting logic", False, str(e))


def test_dynamic_position_logic():
    try:
        import pandas as pd
        from dynamic_position import calc_volatility, adjust_risk_for_streak, adjust_risk_for_volatility

        # Normal volatility
        closes = pd.Series([100.0 + i * 0.3 + (i % 5) * 0.1 for i in range(26)])
        vol = calc_volatility(closes)
        assert isinstance(vol, float), "calc_volatility must return float"
        assert vol >= 0, "volatility must be non-negative"

        # Fallback when insufficient data
        short_closes = pd.Series([100.0, 101.0])
        fallback_vol = calc_volatility(short_closes)
        assert fallback_vol == 0.02, f"short series should use 2% fallback, got {fallback_vol}"

        # High volatility → risk reduced
        high_vol_risk = adjust_risk_for_volatility(2.0, 0.05)  # vol > 4%
        assert high_vol_risk < 2.0, f"high vol should reduce risk below 2.0, got {high_vol_risk}"
        assert high_vol_risk >= 0.5, f"high vol risk should not go below min (0.5), got {high_vol_risk}"

        # Low volatility → risk may increase
        low_vol_risk = adjust_risk_for_volatility(2.0, 0.005)  # vol < 1%
        assert low_vol_risk > 2.0, f"low vol should increase risk above 2.0, got {low_vol_risk}"
        assert low_vol_risk <= 5.0, f"low vol risk should not exceed max (5.0), got {low_vol_risk}"

        # Normal volatility → no change
        normal_vol_risk = adjust_risk_for_volatility(2.0, 0.02)
        assert normal_vol_risk == 2.0, f"normal vol should keep base risk, got {normal_vol_risk}"

        # Streak: all wins → risk increases
        win_log = [{"action": "SELL", "profit": 5.0}] * 5
        win_risk = adjust_risk_for_streak(2.0, win_log)
        assert win_risk >= 2.0, f"win streak should keep or increase risk, got {win_risk}"
        assert win_risk <= 5.0, f"win risk should not exceed max (5.0), got {win_risk}"

        # Streak: all losses → risk decreases
        loss_log = [{"action": "SELL", "profit": -3.0}] * 5
        loss_risk = adjust_risk_for_streak(2.0, loss_log)
        assert loss_risk <= 2.0, f"loss streak should reduce risk, got {loss_risk}"
        assert loss_risk >= 0.5, f"loss risk should not go below min (0.5), got {loss_risk}"

        # Empty trade log → base risk unchanged
        empty_risk = adjust_risk_for_streak(2.0, [])
        assert empty_risk == 2.0, f"empty log should return base risk, got {empty_risk}"

        record("Dynamic position sizing", True)
    except Exception as e:
        record("Dynamic position sizing", False, str(e))


def test_news_sentiment_logic():
    try:
        from news_sentiment import compute_sentiment_score

        positive_news = ["Company beats earnings expectations", "Stock surges to record high"]
        negative_news = ["Company reports major loss", "CEO scandal rocks stock"]
        mixed_news = positive_news + negative_news

        pos_score = compute_sentiment_score(positive_news)
        neg_score = compute_sentiment_score(negative_news)
        mixed_score = compute_sentiment_score(mixed_news)

        assert isinstance(pos_score, int), "sentiment score must be int"
        assert pos_score > 0, f"positive news should score > 0, got {pos_score}"
        assert neg_score < 0, f"negative news should score < 0, got {neg_score}"

        record("News sentiment logic", True)
    except Exception as e:
        record("News sentiment logic", False, str(e))


def test_config_loader():
    try:
        from config_loader import load_config
        cfg = load_config()
        assert isinstance(cfg, dict), "config must be a dict"
        record("Config loader", True)
    except Exception as e:
        record("Config loader", False, str(e))


def test_license_api_helpers():
    try:
        from license_api import generate_license_key, hash_code
        key = generate_license_key()
        assert key.startswith("LIC-"), f"expected LIC- prefix, got: {key}"
        h = hash_code("123456")
        assert len(h) == 64, f"expected 64-char SHA-256, got: {len(h)}"
        record("License API helpers", True)
    except Exception as e:
        record("License API helpers", False, str(e))


# ══════════════════════════════════════════════════════════════════
#  SECTION 4 — CONFIGURATION & KEYS
# ══════════════════════════════════════════════════════════════════

def test_keys_configured():
    alpaca_key    = os.environ.get("ALPACA_KEY", "")
    alpaca_secret = os.environ.get("ALPACA_SECRET", "")
    av_key        = os.environ.get("ALPHA_VANTAGE_KEY", "")

    # Also check keys.bat on disk as a fallback indicator
    keys_bat = BASE_DIR / "keys.bat"
    keys_bat_exists = keys_bat.exists()

    if alpaca_key and alpaca_secret and av_key:
        record("API keys (env vars set)", True, "ALPACA_KEY, ALPACA_SECRET, ALPHA_VANTAGE_KEY ✔")
    elif keys_bat_exists:
        _warn("API keys are in keys.bat but not loaded into this shell session.")
        _info("On Windows: run this test from START.bat or LAUNCH.bat which loads keys.bat.")
        _info("On Mac/Linux: run 'source keys.sh' before running self_test.py.")
        record("API keys (keys.bat present)", True,
               "keys.bat found — load it before running the app", None)
    else:
        def fix_keys():
            _warn("No API keys found. Running setup wizard...")
            result = subprocess.run([sys.executable, "setup_wizard.py"])
            if result.returncode == 0:
                _ok("Setup wizard completed. Re-run self_test.py to verify.")
            else:
                _fail("Setup wizard exited with an error.")

        record("API keys configured", False,
               "ALPACA_KEY/ALPACA_SECRET not set and keys.bat not found", fix_keys)


def test_config_json_valid():
    cfg_path = BASE_DIR / "config.json"
    if not cfg_path.exists():
        record("config.json (optional)", True, "Not present — using env vars (OK)")
        return
    try:
        with open(cfg_path) as f:
            data = json.load(f)
        assert isinstance(data, dict)
        record("config.json valid JSON", True)
    except json.JSONDecodeError as e:
        def fix_config():
            _warn(f"config.json has invalid JSON: {e}")
            _info("Delete or re-create config.json using the setup wizard.")
        record("config.json valid JSON", False, str(e), fix_config)
    except Exception as e:
        record("config.json valid JSON", False, str(e))


def test_template_exists():
    tpl = BASE_DIR / "templates" / "dashboard.html"
    ok = tpl.exists()

    def fix_template():
        _warn("dashboard.html is missing — the web UI will not work.")
        _info("Re-download the ZIP from GitHub and re-extract all files.")

    record("Dashboard template (dashboard.html)", ok,
           "" if ok else "templates/dashboard.html not found",
           None if ok else fix_template)


# ══════════════════════════════════════════════════════════════════
#  SECTION 5 — VIRTUAL ENVIRONMENT (Windows only)
# ══════════════════════════════════════════════════════════════════

def test_venv():
    if not _IS_WIN:
        record("Virtual environment (Windows only)", True, "Skipped on non-Windows — use system Python")
        return

    venv = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    ok = venv.exists()

    def fix_venv():
        _info("Creating virtual environment...")
        result = subprocess.run([sys.executable, "-m", "venv", str(BASE_DIR / ".venv")],
                                capture_output=True, text=True)
        if result.returncode == 0:
            _ok(".venv created. Run LAUNCH.bat → [1] Install to finish setup.")
        else:
            _fail("venv creation failed:")
            print(result.stderr[-500:])

    record("Virtual environment (.venv)", ok,
           "" if ok else ".venv not found — run LAUNCH.bat → [1] Install",
           None if ok else fix_venv)


# ══════════════════════════════════════════════════════════════════
#  MAIN RUNNER
# ══════════════════════════════════════════════════════════════════

def run_all_tests():
    print()
    print(f"{C.BOLD}{C.CYAN}")
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║          👽  ALIEN AI TRADER — SELF-TEST               ║")
    print("  ║          Checking installation health                   ║")
    print(f"  ╚══════════════════════════════════════════════════════════╝{C.RESET}")
    print()
    print(f"  {C.DIM}Python:   {sys.version.split()[0]}{C.RESET}")
    print(f"  {C.DIM}Platform: {platform.system()} {platform.release()}{C.RESET}")
    print(f"  {C.DIM}Dir:      {BASE_DIR}{C.RESET}")

    _head("SECTION 1 — Runtime & Files")
    test_python_version()
    test_required_files()

    _head("SECTION 2 — Python Packages")
    test_packages()

    _head("SECTION 3 — Module Logic")
    test_module_imports()
    test_forecasting_logic()
    test_dynamic_position_logic()
    test_news_sentiment_logic()
    test_config_loader()
    test_license_api_helpers()

    _head("SECTION 4 — Configuration & Keys")
    test_keys_configured()
    test_config_json_valid()
    test_template_exists()

    _head("SECTION 5 — Environment")
    test_venv()


def print_summary(repair_mode: bool):
    passed = [r for r in RESULTS if r[1]]
    failed = [r for r in RESULTS if not r[1]]

    print()
    print(f"{C.BOLD}  ╔══════════════════════════════════════════════════════════╗{C.RESET}")
    if not failed:
        print(f"{C.BOLD}{C.GREEN}  ║   ✦  ALL TESTS PASSED — Installation looks healthy! ✦  ║{C.RESET}")
    else:
        print(f"{C.BOLD}{C.YELLOW}  ║   ⚠  SOME TESTS FAILED — See issues below              ║{C.RESET}")
    print(f"{C.BOLD}  ╚══════════════════════════════════════════════════════════╝{C.RESET}")
    print()
    print(f"  Passed: {C.GREEN}{len(passed)}{C.RESET}  |  Failed: {C.RED}{len(failed)}{C.RESET}  |  Total: {len(RESULTS)}")
    print()

    if not failed:
        print(f"  {C.GREEN}Your Alien AI Trader installation is ready to go!{C.RESET}")
        print()
        if _IS_WIN:
            print(f"  Next step: double-click {C.CYAN}START.bat{C.RESET} (or the Desktop shortcut)")
        else:
            print(f"  Next step: {C.CYAN}source keys.sh && python dashboard.py{C.RESET}")
        print()
        return 0

    # Show failed tests and fixes
    print(f"  {C.YELLOW}Issues found:{C.RESET}")
    fixable = [(name, detail, fix) for name, passed, detail, fix in RESULTS
               if not passed and fix is not None]
    unfixable = [(name, detail) for name, passed, detail, fix in RESULTS
                 if not passed and fix is None]

    for name, detail, _ in fixable:
        print(f"    {C.RED}✖{C.RESET}  {name}" + (f": {detail}" if detail else ""))
    for name, detail in unfixable:
        print(f"    {C.RED}✖{C.RESET}  {name}" + (f": {detail}" if detail else ""))

    print()

    if fixable and repair_mode:
        _head("AUTO-REPAIR")
        for name, detail, fix in fixable:
            print(f"\n  {C.YELLOW}Repairing: {name}{C.RESET}")
            try:
                fix()
            except Exception as e:
                _fail(f"Repair failed: {e}")
        print()
        print(f"  {C.CYAN}Re-run self_test.py to confirm repairs were successful.{C.RESET}")
        print()

    elif fixable and not repair_mode:
        print(f"  {C.CYAN}Run with --repair to automatically fix the issues above:{C.RESET}")
        print(f"    {C.DIM}python self_test.py --repair{C.RESET}")
        if _IS_WIN:
            print(f"    {C.DIM}(or double-click SELF_TEST.bat and choose Repair){C.RESET}")
        print()

    if unfixable:
        print(f"  {C.YELLOW}The following issues require manual attention:{C.RESET}")
        for name, detail in unfixable:
            print(f"    • {name}: {detail}")
        print()

    return 1


def main():
    args = sys.argv[1:]
    quiet = "--quiet" in args
    repair = "--repair" in args

    if not quiet:
        run_all_tests()
    else:
        # Run silently
        old_stdout = sys.stdout
        sys.stdout = open(os.devnull, "w")
        try:
            run_all_tests()
        finally:
            sys.stdout = old_stdout

    failed = [r for r in RESULTS if not r[1]]

    if quiet:
        sys.exit(0 if not failed else 1)

    exit_code = print_summary(repair_mode=repair)

    # Interactive repair prompt if not already in repair mode
    if failed and not repair and not quiet:
        fixable = [(name, detail, fix) for name, passed, detail, fix in RESULTS
                   if not passed and fix is not None]
        if fixable:
            try:
                answer = input(f"  {C.BOLD}Would you like to auto-repair the fixable issues now? (y/N): {C.RESET}").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
            if answer in ("y", "yes"):
                print()
                _head("AUTO-REPAIR")
                for name, detail, fix in fixable:
                    print(f"\n  {C.YELLOW}Repairing: {name}{C.RESET}")
                    try:
                        fix()
                    except Exception as e:
                        _fail(f"Repair failed: {e}")
                print()
                _info("Re-run self_test.py to confirm all repairs were successful.")
                print()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
