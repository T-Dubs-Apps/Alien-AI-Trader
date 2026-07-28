"""
key_store.py  --  Runtime store for ALL provider credentials.

Lets the user paste every key the app needs straight into the running app
(Settings -> Setup) instead of setting Render environment variables before the
service will even deploy. This is what allows the Render Blueprint to ask for
almost nothing up front: a fresh deployment boots with no keys at all, shows the
setup panel, and comes alive the moment the user saves their keys -- no redeploy.

Handles:
  PAPER Alpaca   -> ALPACA_KEY / ALPACA_SECRET          (practice money)
  LIVE  Alpaca   -> ALPACA_LIVE_KEY / ALPACA_LIVE_SECRET (real money, license-gated)
  Alpha Vantage  -> ALPHA_VANTAGE_KEY                    (indicator history)

Precedence: a value saved in the store wins; otherwise fall back to the env var.
The user's own in-app entry is the most recent explicit instruction, so it beats
a deployment default. A deployment that only ever sets env vars is unaffected,
because nothing is written to the store until someone saves a key in-app.

Security: this file holds real trading secrets. It is git-ignored and never
leaves the user's own machine/instance. Values are never sent to the browser --
the app only ever reports whether a key is PRESENT, never what it is.
"""
import json
import os
import threading

_LOCK = threading.RLock()
_BASE = os.path.dirname(os.path.abspath(__file__))
# Durable state dir (see dashboard.py DATA_DIR). Defaults to the app folder so
# local behavior is unchanged; on Render, point DATA_DIR at a persistent disk so
# in-app keys survive deploys/restarts/crashes.
_DATA_DIR = os.environ.get("DATA_DIR", _BASE)
try:
    os.makedirs(_DATA_DIR, exist_ok=True)
except Exception:
    _DATA_DIR = _BASE
# Filename kept as-is so existing deployments keep their saved live keys.
_STORE = os.path.join(_DATA_DIR, "live_keys.json")

# Every credential this app understands, and the env var it falls back to.
FIELDS = (
    "ALPACA_KEY",
    "ALPACA_SECRET",
    "ALPACA_LIVE_KEY",
    "ALPACA_LIVE_SECRET",
    "ALPHA_VANTAGE_KEY",
)

# Callbacks fired after any successful save so long-lived clients (dashboard
# REST handles, the engine) can rebuild themselves without a restart.
_listeners = []


def _read() -> dict:
    try:
        with open(_STORE, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _get(name: str) -> str:
    """Stored value first, env var second. Always a stripped string."""
    d = _read()
    return (d.get(name) or os.environ.get(name) or "").strip()


def on_change(callback) -> None:
    """Register a zero-arg callback to run after keys are saved."""
    with _LOCK:
        if callback not in _listeners:
            _listeners.append(callback)


def _notify() -> None:
    for cb in list(_listeners):
        try:
            cb()
        except Exception:
            pass  # a bad listener must never block a key save


# ── Readers ──────────────────────────────────────────────────────────────────

def get_paper_keys():
    """(key, secret) for the PAPER Alpaca account."""
    return (_get("ALPACA_KEY") or None, _get("ALPACA_SECRET") or None)


def has_paper_keys() -> bool:
    k, s = get_paper_keys()
    return bool(k and s)


def get_live_keys():
    """(key, secret) for the LIVE Alpaca account."""
    return (_get("ALPACA_LIVE_KEY") or None, _get("ALPACA_LIVE_SECRET") or None)


def has_live_keys() -> bool:
    k, s = get_live_keys()
    return bool(k and s)


def get_alpha_key():
    return _get("ALPHA_VANTAGE_KEY") or None


def has_alpha_key() -> bool:
    return bool(get_alpha_key())


def needs_setup() -> bool:
    """True when the app cannot trade yet because required keys are missing.

    Paper keys + Alpha Vantage are the minimum to run. Live keys are optional
    and separately license-gated.
    """
    return not (has_paper_keys() and has_alpha_key())


def status() -> dict:
    """Presence-only report, safe to send to the browser. Never returns values."""
    def src(name):
        if (_read().get(name) or "").strip():
            return "in_app"
        if (os.environ.get(name) or "").strip():
            return "env"
        return "missing"

    return {
        "paper_keys": has_paper_keys(),
        "live_keys": has_live_keys(),
        "alpha_key": has_alpha_key(),
        "needs_setup": needs_setup(),
        "sources": {name: src(name) for name in FIELDS},
    }


# ── Writer ───────────────────────────────────────────────────────────────────

def save(values: dict) -> bool:
    """Persist any recognized non-empty credentials from `values`.

    Unknown names are ignored, empty values are skipped (so a blank field in the
    setup form never wipes a working key). Returns True on a successful write.
    """
    incoming = {}
    for name in FIELDS:
        raw = (values or {}).get(name)
        if raw is None:
            continue
        raw = str(raw).strip()
        if raw:
            incoming[name] = raw
    if not incoming:
        return False

    with _LOCK:
        d = _read()
        d.update(incoming)
        try:
            # Write via a temp file so a crash mid-write can't corrupt the store.
            tmp = _STORE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(d, f, indent=2)
            os.replace(tmp, _STORE)
        except Exception:
            return False
    _notify()
    return True


def clear(names=None) -> bool:
    """Remove stored credentials (env fallbacks, if any, take over again)."""
    targets = [n for n in (names or FIELDS) if n in FIELDS]
    if not targets:
        return False
    with _LOCK:
        d = _read()
        for n in targets:
            d.pop(n, None)
        try:
            tmp = _STORE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(d, f, indent=2)
            os.replace(tmp, _STORE)
        except Exception:
            return False
    _notify()
    return True


# ── Back-compat shim ─────────────────────────────────────────────────────────

def set_keys(alpaca_key=None, alpaca_secret=None, alpha=None) -> bool:
    """Legacy signature used by the existing /api/keys/live endpoint and the
    setup wizard: saves LIVE Alpaca keys and/or the Alpha Vantage key."""
    return save({
        "ALPACA_LIVE_KEY": alpaca_key,
        "ALPACA_LIVE_SECRET": alpaca_secret,
        "ALPHA_VANTAGE_KEY": alpha,
    })
