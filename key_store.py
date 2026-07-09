"""
key_store.py  --  Runtime store for LIVE trading credentials.

Lets the user paste their live Alpaca keys straight into the app (Settings ->
Trading Mode -> "Add live keys") instead of visiting the Render dashboard. Keys
are saved to live_keys.json next to this file and read by BOTH the dashboard and
the in-process trading engine, so a live switch works without a restart.

Precedence: a value saved in live_keys.json wins; otherwise fall back to the
env var (so a cloud deployment that set ALPACA_LIVE_KEY in Render still works,
and an in-app entry takes effect immediately even when no env var is set).

Security: live_keys.json holds real trading secrets -- it is git-ignored and
never leaves the user's own machine/instance.
"""
import json
import os
import threading

_LOCK = threading.Lock()
_BASE = os.path.dirname(os.path.abspath(__file__))
# Durable state dir (see dashboard.py DATA_DIR). Defaults to the app folder so
# local behavior is unchanged; on Render, point DATA_DIR at a persistent disk so
# in-app live keys survive deploys/restarts/crashes.
_DATA_DIR = os.environ.get("DATA_DIR", _BASE)
try:
    os.makedirs(_DATA_DIR, exist_ok=True)
except Exception:
    _DATA_DIR = _BASE
_STORE = os.path.join(_DATA_DIR, "live_keys.json")


def _read() -> dict:
    try:
        with open(_STORE, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_live_keys():
    """(key, secret) for LIVE Alpaca, from the file first, then env vars."""
    d = _read()
    key = (d.get("ALPACA_LIVE_KEY") or os.environ.get("ALPACA_LIVE_KEY") or "").strip()
    sec = (d.get("ALPACA_LIVE_SECRET") or os.environ.get("ALPACA_LIVE_SECRET") or "").strip()
    return (key or None, sec or None)


def has_live_keys() -> bool:
    key, sec = get_live_keys()
    return bool(key and sec)


def get_alpha_key():
    d = _read()
    return (os.environ.get("ALPHA_VANTAGE_KEY") or d.get("ALPHA_VANTAGE_KEY") or "").strip() or None


def set_keys(alpaca_key=None, alpaca_secret=None, alpha=None) -> bool:
    """Persist any provided keys. Only non-empty values are written."""
    with _LOCK:
        d = _read()
        if alpaca_key:
            d["ALPACA_LIVE_KEY"] = alpaca_key.strip()
        if alpaca_secret:
            d["ALPACA_LIVE_SECRET"] = alpaca_secret.strip()
        if alpha:
            d["ALPHA_VANTAGE_KEY"] = alpha.strip()
        try:
            with open(_STORE, "w") as f:
                json.dump(d, f, indent=2)
            return True
        except Exception:
            return False
