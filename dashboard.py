# CRITICAL: gevent monkey patch MUST be first -- before ANY other imports.
# This patches Python's standard library to work with gevent's async model.
# Required for Socket.IO WebSocket support on Render/gunicorn with gevent worker.
from gevent import monkey
monkey.patch_all()

import json
import os
import random
import secrets
import sys
import threading
import time
import requests
from threading import Lock
from typing import Dict, Any, List

# Force UTF-8 console/log output so emoji or special characters in any log line
# can never crash a trading session on Windows. Without this, stdout defaults to
# cp1252 and printing a character like an emoji raises UnicodeEncodeError, which
# was killing every engine session right after startup (before stops/exits ran).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from flask import Flask, render_template, request, jsonify, session, redirect
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from license_api import register_license_routes
from trading_engine import TradingEngine
from portfolio_ladder import PortfolioLadderScanner, integrate_ladder_with_engine, DEFAULT_PORTFOLIO
from crash_notifier import send_crash_notification

# Market data providers (quotes + basic lookup)
from alpaca_trade_api.rest import REST
from alpha_vantage.timeseries import TimeSeries

# SMART PATHING: This finds 'templates' relative to where this script is sitting
base_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(base_dir, "templates")


def _bootstrap_local_env() -> None:
    """Fill missing env vars from local key files when running outside START.bat.

    Local users often launch dashboard.py directly, which skips keys.bat loading
    done by START.bat. That leaves required vars empty and the engine reports
    offline. We only hydrate empty env vars and never overwrite already-set
    process/deployment values.
    """
    wanted = {
        "ALPACA_KEY",
        "ALPACA_SECRET",
        "ALPACA_LIVE_KEY",
        "ALPACA_LIVE_SECRET",
        "ALPHA_VANTAGE_KEY",
        "PUSHBULLET_TOKEN",
        "PUSHOVER_TOKEN",
        "PUSHOVER_USER",
        "FLASK_SECRET",
        "DASHBOARD_PASSWORD",
        "LICENSE_EMAIL",
        "LICENSE_SERVER_URL",
        "TRADING_MODE",
        "LIVE_TRADING_ENABLED",
    }

    loaded_from_bat = 0
    keys_bat = os.path.join(base_dir, "keys.bat")
    try:
        if os.path.exists(keys_bat):
            with open(keys_bat, "r", encoding="utf-8", errors="replace") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.lower().startswith("rem") or line.startswith("::"):
                        continue
                    lo = line.lower()
                    if lo.startswith("@echo"):
                        continue
                    if not lo.startswith("set "):
                        continue
                    body = line[4:].strip()
                    # Support both: set KEY=VAL and set "KEY=VAL"
                    if len(body) >= 2 and body[0] == '"' and body[-1] == '"':
                        body = body[1:-1]
                    if "=" not in body:
                        continue
                    key, val = body.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    if key in wanted and not os.environ.get(key) and val:
                        os.environ[key] = val
                        loaded_from_bat += 1
    except Exception:
        pass

    loaded_from_json = 0
    config_json = os.path.join(base_dir, "config.json")
    try:
        if os.path.exists(config_json):
            with open(config_json, "r", encoding="utf-8", errors="replace") as f:
                raw = f.read().strip()
            if raw:
                if not raw.lstrip().startswith("{"):
                    raw = "{" + raw
                if not raw.rstrip().endswith("}"):
                    raw = raw + "}"
                cfg = json.loads(raw)
                if isinstance(cfg, dict):
                    for key in wanted:
                        val = cfg.get(key)
                        if isinstance(val, str) and val.strip() and not os.environ.get(key):
                            os.environ[key] = val.strip()
                            loaded_from_json += 1
    except Exception:
        pass

    if loaded_from_bat or loaded_from_json:
        print(
            f"[BOOT] Loaded {loaded_from_bat} env var(s) from keys.bat and "
            f"{loaded_from_json} from config.json."
        )


_bootstrap_local_env()

# ── Durable state directory ───────────────────────────────────────────────────
# All runtime state (license cache, settings, live keys, grants DB) is written
# here. On Render the container filesystem is EPHEMERAL — wiped on every deploy,
# restart, and crash — so pointing DATA_DIR at a mounted persistent disk (e.g.
# /var/data) makes state survive verbatim: the app returns to the exact place it
# was before the incident. Unset → falls back to base_dir (unchanged local
# behavior). key_store.py and license_api.py read the same DATA_DIR.
DATA_DIR = os.environ.get("DATA_DIR", base_dir)
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception:
    DATA_DIR = base_dir  # unwritable mount → fail safe to the app folder

# Settings are persisted here so they survive restarts
SETTINGS_FILE = os.path.join(DATA_DIR, "trading_settings.json")

app = Flask(__name__, template_folder=template_dir)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET", os.urandom(24).hex())

# CORS
allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*")
origins = [o.strip() for o in allowed_origins.split(",")] if allowed_origins else ["*"]
CORS(app, resources={r"/api/*": {"origins": origins}})

# WebSocket via SocketIO
# gevent mode required for Render/gunicorn production deployment.
# Uses gevent which is already in requirements.txt.
_async_mode = os.environ.get("SOCKETIO_ASYNC_MODE", "gevent")
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode=_async_mode,
    logger=False,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25,
)

# License routes (server side — only does anything on the central deployment
# that holds the Stripe keys; inert on user machines)
register_license_routes(app)

# ── License client (every installed copy) ────────────────────────────────
# Paper trading is free forever. Live trading requires an active license,
# validated against the central license server below.
APP_ID = "alien-ai-trader"
LICENSE_SERVER_URL = os.environ.get(
    "LICENSE_SERVER_URL", "https://alien-ai-trader-dashboard.onrender.com"
).rstrip("/")
LICENSE_FILE = os.path.join(DATA_DIR, "license.json")
TRUSTED_DEVICES_FILE = os.path.join(DATA_DIR, "trusted_devices.json")
OWNER_FREEZE_FILE = os.path.join(DATA_DIR, "owner_freeze.json")


def _clean_env_value(name: str, default: str = "") -> str:
    """Read an env var and normalize common copy/paste formatting slips.

    Render env values are sometimes pasted with surrounding quotes. Stripping a
    single matching wrapper quote pair prevents false mismatches (for example,
    dashboard password appears correct but compares against a quoted value).
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    s = str(raw).strip()
    if len(s) >= 2 and s[0] in ("'", '"') and s[-1] == s[0]:
        s = s[1:-1].strip()
    return s


def _normalize_dashboard_password(value: str) -> str:
    """Normalize password text from env/forms for reliable comparison.

    Handles common Render/dashboard paste artifacts without weakening auth:
    wrapper quotes, stray CR/LF, non-breaking/zero-width spaces, and edge
    whitespace. Content inside the password remains unchanged.
    """
    s = str(value or "")
    s = s.replace("\r", "").replace("\n", "")
    # Remove invisible separators that can sneak in during copy/paste.
    for ch in ("\u200b", "\u200c", "\u200d", "\ufeff", "\u00a0"):
        s = s.replace(ch, "")
    s = s.strip()
    # Unwrap accidental wrapper quotes repeatedly ("..." or '...').
    while len(s) >= 2 and s[0] in ("'", '"') and s[-1] == s[0]:
        s = s[1:-1].strip()
    return s


def _dashboard_password_candidates() -> list[str]:
    """Return accepted dashboard passwords (normalized), from common env names.

    DASHBOARD_PASSWORD remains the primary key; alternates are accepted only as
    a compatibility bridge for deployments that set an older variable name.
    """
    names = (
        "DASHBOARD_PASSWORD",
        "ADMIN_PASSWORD",
        "TRADER_PASSWORD",
        "PASSWORD",
    )
    vals: list[str] = []
    for name in names:
        raw = os.environ.get(name)
        if raw is None:
            continue
        norm = _normalize_dashboard_password(raw)
        if norm and norm not in vals:
            vals.append(norm)
    return vals


# Normalize once at boot so every endpoint reads one canonical value.
LICENSE_SERVER_URL = _clean_env_value(
    "LICENSE_SERVER_URL",
    "https://alien-ai-trader-dashboard.onrender.com",
).rstrip("/")

# ── Dashboard access gate (per-deployment password) ───────────────────────────
# Each owner sets their OWN password on their OWN Render service via the
# DASHBOARD_PASSWORD env var. When set, the trading dashboard and every control
# endpoint (place order, change settings, save live keys, toggle trading) require
# logging in first, so a public .onrender.com URL can't be driven by a stranger.
# When UNSET the gate is off (nothing to lock), and we print a loud boot warning
# urging the owner to set one. The public store/landing pages and the central
# license/Stripe endpoints always stay open so buyers and Stripe can reach them.
import hmac
DASHBOARD_PASSWORD = _clean_env_value("DASHBOARD_PASSWORD", "")
TRUSTED_OWNER_EMAILS_ENV = _clean_env_value("TRUSTED_OWNER_EMAILS", "")
OWNER_FREEZE_TOKEN = _clean_env_value("OWNER_FREEZE_TOKEN", "")
TRUSTED_DEVICE_COOKIE = "aat_trusted_device"
OWNER_REAUTH_DAYS_MIN = int(os.environ.get("OWNER_REAUTH_DAYS_MIN", "120"))
OWNER_REAUTH_DAYS_MAX = int(os.environ.get("OWNER_REAUTH_DAYS_MAX", "180"))
_trusted_devices_lock = Lock()
_owner_freeze_lock = Lock()

# Path prefixes that must stay reachable WITHOUT logging in.
_PUBLIC_PATH_PREFIXES = (
    "/login", "/logout", "/health", "/favicon", "/static",
    "/get", "/store", "/thankyou",
    "/api/license/",   # license server + in-app activation (validate/pricing/checkout/admin)
    "/api/stripe/",    # Stripe webhook
)


def _path_is_public(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in _PUBLIC_PATH_PREFIXES)


def _dashboard_authed() -> bool:
    """True when access is allowed: either no password is configured (gate off)
    or the visitor has logged in this session."""
    return (not DASHBOARD_PASSWORD) or bool(session.get("dash_authed"))


def _norm_email(value: str) -> str:
    return str(value or "").strip().lower()


def _trusted_owner_emails() -> set[str]:
    emails = set()
    for raw in TRUSTED_OWNER_EMAILS_ENV.split(","):
        e = _norm_email(raw)
        if e:
            emails.add(e)
    return emails


def _load_trusted_devices() -> dict:
    try:
        with open(TRUSTED_DEVICES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_trusted_devices(data: dict) -> None:
    try:
        with open(TRUSTED_DEVICES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _get_device_id_from_cookie() -> str:
    raw = str(request.cookies.get(TRUSTED_DEVICE_COOKIE, "") or "").strip()
    if not raw or len(raw) > 120:
        return ""
    return raw


def _new_device_id() -> str:
    return secrets.token_urlsafe(24)


def _next_reauth_ts() -> int:
    lo = max(30, OWNER_REAUTH_DAYS_MIN)
    hi = max(lo, OWNER_REAUTH_DAYS_MAX)
    days = random.randint(lo, hi)
    return int(time.time()) + (days * 86400)


def _get_trusted_record(device_id: str) -> dict:
    if not device_id:
        return {}
    with _trusted_devices_lock:
        data = _load_trusted_devices()
        rec = data.get(device_id)
        return rec if isinstance(rec, dict) else {}


def _mark_trusted_device(device_id: str, owner_email: str) -> None:
    if not device_id or not owner_email:
        return
    with _trusted_devices_lock:
        data = _load_trusted_devices()
        data[device_id] = {
            "email": _norm_email(owner_email),
            "last_full_login": int(time.time()),
            "next_reauth_ts": _next_reauth_ts(),
        }
        # Keep file bounded in case many devices touched this deployment.
        if len(data) > 200:
            items = sorted(
                data.items(),
                key=lambda kv: int((kv[1] or {}).get("last_full_login", 0)),
                reverse=True,
            )[:200]
            data = dict(items)
        _save_trusted_devices(data)


def _trusted_device_allows_bypass(device_id: str) -> tuple[bool, str]:
    """Return (allowed, email) when this device can skip full login."""
    rec = _get_trusted_record(device_id)
    if not rec:
        return False, ""
    email = _norm_email(rec.get("email", ""))
    if not email or email not in _trusted_owner_emails():
        return False, ""
    due = int(rec.get("next_reauth_ts", 0) or 0)
    if due and int(time.time()) >= due:
        return False, ""
    return True, email


def _trusted_device_reauth_due(device_id: str) -> bool:
    rec = _get_trusted_record(device_id)
    if not rec:
        return False
    email = _norm_email(rec.get("email", ""))
    if not email or email not in _trusted_owner_emails():
        return False
    due = int(rec.get("next_reauth_ts", 0) or 0)
    return bool(due and int(time.time()) >= due)


def _owner_freeze_enabled() -> bool:
    return bool(OWNER_FREEZE_TOKEN)


def _load_owner_freeze_state() -> dict:
    try:
        with open(OWNER_FREEZE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"locked": False, "updated_at": 0, "updated_by": ""}


def _save_owner_freeze_state(data: dict) -> None:
    try:
        with open(OWNER_FREEZE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _owner_freeze_is_locked() -> bool:
    if not _owner_freeze_enabled():
        return False
    with _owner_freeze_lock:
        state = _load_owner_freeze_state()
        return bool(state.get("locked", False))


def _owner_freeze_block(action: str):
    if not _owner_freeze_is_locked():
        return None
    return jsonify({
        "status": "locked",
        "message": f"Owner Lockdown Freeze is enabled. '{action}' is blocked until owner unlocks.",
    }), 423


def _owner_freeze_token_ok(supplied: str) -> bool:
    candidate = _normalize_dashboard_password(supplied or "")
    expected = _normalize_dashboard_password(OWNER_FREEZE_TOKEN)
    if not candidate or not expected:
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))

# -- Distribution URLs (used by the shareable Render landing page /get) --------
# The public repo IS the installation package. The GitHub archive link always
# serves the latest build, so buyers always download an up-to-date copy.
GITHUB_REPO_URL   = os.environ.get("GITHUB_REPO_URL", "https://github.com/T-Dubs-Apps/Alien-AI-Trader")
DOWNLOAD_ZIP_URL  = os.environ.get("DOWNLOAD_ZIP_URL", GITHUB_REPO_URL + "/archive/refs/heads/main.zip")
# One-click "Deploy to Render" — Render reads render.yaml from the repo and
# stands up the buyer's OWN private cloud instance (their keys, their trades).
RENDER_DEPLOY_URL = os.environ.get("RENDER_DEPLOY_URL", "https://render.com/deploy?repo=" + GITHUB_REPO_URL)

# App icon — an alien clutching a wad of cash. Served at /favicon.svg and linked
# from every page, so it shows in the browser tab on any device (works on the
# cloud deploy too, where no local .ico is generated). The desktop-shortcut .ico
# is drawn separately by make_icon.py to match.
FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
<defs>
<radialGradient id="bg" cx="50%" cy="34%" r="78%"><stop offset="0%" stop-color="#132340"/><stop offset="100%" stop-color="#060c18"/></radialGradient>
<linearGradient id="bill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#8cf0b4"/><stop offset="100%" stop-color="#5fd68f"/></linearGradient>
</defs>
<rect x="8" y="8" width="240" height="240" rx="54" fill="url(#bg)"/>
<circle cx="128" cy="108" r="94" fill="none" stroke="#22c55e" stroke-opacity=".16" stroke-width="6"/>
<!-- flying banknotes -->
<g stroke="#14532d" stroke-width="1" font-family="Arial,Helvetica,sans-serif" font-weight="bold">
<g transform="translate(202,50) rotate(18)"><rect x="-17" y="-11" width="34" height="22" rx="3" fill="url(#bill)"/><ellipse cx="0" cy="0" rx="6" ry="5" fill="#ecfdf5"/><text x="-13" y="-3" font-size="7" fill="#14532d" stroke="none">$</text></g>
<g transform="translate(52,56) rotate(-20)"><rect x="-15" y="-10" width="30" height="20" rx="3" fill="url(#bill)"/><ellipse cx="0" cy="0" rx="5" ry="4" fill="#ecfdf5"/><text x="-11" y="-2" font-size="6" fill="#14532d" stroke="none">$</text></g>
</g>
<!-- antenna -->
<line x1="128" y1="34" x2="128" y2="12" stroke="#22c55e" stroke-width="4.5" stroke-linecap="round"/>
<circle cx="128" cy="9" r="14" fill="#4ade80" opacity=".22"/><circle cx="128" cy="9" r="8" fill="#4ade80"/>
<!-- arms (behind head; hands hold the wad) -->
<path d="M96 152 Q82 192 118 204" fill="none" stroke="#22c55e" stroke-width="13" stroke-linecap="round"/>
<path d="M160 152 Q194 192 138 204" fill="none" stroke="#22c55e" stroke-width="13" stroke-linecap="round"/>
<!-- head (matches landing-page alien face) -->
<ellipse cx="128" cy="108" rx="60" ry="78" fill="#22c55e" stroke="#16a34a" stroke-width="3"/>
<!-- eyes: black, tilted, with shine -->
<g fill="#000000"><ellipse cx="99" cy="97" rx="22" ry="15" transform="rotate(-18 99 97)"/><ellipse cx="157" cy="97" rx="22" ry="15" transform="rotate(18 157 97)"/></g>
<ellipse cx="90" cy="90" rx="6.5" ry="4.5" fill="#fff" opacity=".8"/><ellipse cx="148" cy="90" rx="6.5" ry="4.5" fill="#fff" opacity=".8"/>
<!-- nostrils + wide smile -->
<circle cx="115" cy="140" r="5" fill="#16a34a"/><circle cx="141" cy="140" r="5" fill="#16a34a"/>
<path d="M101 150 Q128 176 155 150" fill="none" stroke="#16a34a" stroke-width="4" stroke-linecap="round"/>
<!-- realistic banded wad of cash -->
<g font-family="Arial,Helvetica,sans-serif">
<rect x="76" y="188" width="104" height="48" rx="4" fill="#38bd78"/>
<rect x="76" y="184" width="104" height="48" rx="4" fill="#4fd18a"/>
<rect x="76" y="180" width="104" height="48" rx="4" fill="url(#bill)" stroke="#14532d" stroke-width="1.5"/>
<rect x="82" y="186" width="92" height="36" rx="3" fill="none" stroke="#22c55e" stroke-opacity=".5" stroke-width="1.3"/>
<ellipse cx="128" cy="202" rx="16" ry="13" fill="#ecfdf5" stroke="#14532d" stroke-width="1"/>
<circle cx="128" cy="199" r="5.5" fill="#5fd68f"/><path d="M120 210 Q128 202 136 210 Z" fill="#5fd68f"/>
<text x="90" y="195" font-size="9" font-weight="bold" fill="#14532d">$</text>
<text x="166" y="219" font-size="9" font-weight="bold" fill="#14532d" text-anchor="end">$</text>
<text x="163" y="195" font-size="7" fill="#14532d" text-anchor="end">100</text>
<text x="93" y="219" font-size="7" fill="#14532d">100</text>
<rect x="114" y="176" width="28" height="56" fill="#ffffff" stroke="#cbd5e1" stroke-width="1"/>
<rect x="114" y="182" width="28" height="2" fill="#000000"/>
<rect x="114" y="224" width="28" height="2" fill="#000000"/>
<text x="128" y="197" font-size="8" font-weight="bold" fill="#000000" text-anchor="middle">$100</text>
<text x="128" y="217" font-size="15" font-weight="bold" fill="#000000" text-anchor="middle">$</text>
</g>
</svg>"""

import key_store
from license_signing import verify_license


def _load_local_license() -> dict:
    try:
        with open(LICENSE_FILE, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_local_license(data: dict) -> None:
    try:
        with open(LICENSE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _license_is_active(lic: dict | None = None) -> bool:
    lic = lic if lic is not None else _load_local_license()
    try:
        # Reject any license not cryptographically signed by the owner key — this is
        # what stops a hand-written license.json from unlocking live trading.
        if not verify_license(lic):
            return False
        return lic.get("status") == "active" and int(lic.get("expiresAt", 0)) > int(time.time() * 1000)
    except Exception:
        return False


def _delete_local_license() -> None:
    """Remove the cached license so the app drops back to paper."""
    try:
        if os.path.exists(LICENSE_FILE):
            os.remove(LICENSE_FILE)
    except Exception:
        pass


_last_revalidation = 0.0
_REVALIDATE_INTERVAL = int(os.environ.get("LICENSE_REVALIDATE_SECONDS", "3600"))  # 1h


def _revalidate_local_license(force: bool = False) -> None:
    """Re-check the stored license against the central server so cancellations
    and refunds reach this installed copy.

    Fails OPEN on a network error (never punishes a paying user for a Render
    cold-start); fails CLOSED only when the server is reachable and definitively
    reports no active license — then the local cache is deleted (live → paper)."""
    global _last_revalidation
    lic = _load_local_license()
    # Offline owner/comp grants (installed via LICENSE_GRANT) are authoritative
    # for this deployment and have no Stripe record to check — never let a
    # server 'none' response revoke them. Expiry is still enforced separately by
    # _license_is_active, so an expired grant still drops to free on its own.
    if LICENSE_GRANT or lic.get("billingType") == "comp" or lic.get("grantedBy") == "owner":
        return
    # Fall back to the purchase email from the environment so re-checks keep
    # working even if the local cache was wiped between boots.
    email = lic.get("email") or (os.environ.get("LICENSE_EMAIL") or "").strip()
    if not email:
        return  # nothing activated locally — nothing to re-check
    now = time.time()
    if not force and (now - _last_revalidation) < _REVALIDATE_INTERVAL:
        return
    _last_revalidation = now
    try:
        r = requests.post(
            f"{LICENSE_SERVER_URL}/api/license/validate",
            json={"email": email, "appId": APP_ID},
            timeout=15,
        )
        data = r.json()
    except Exception:
        return  # server unreachable → keep current license (fail open)
    if data.get("status") == "active":
        _save_local_license(data)   # refresh expiry/signature
    else:
        _delete_local_license()     # cancelled/refunded → revoke locally


# ── Autonomous license recovery ───────────────────────────────────────────────
# Render's filesystem is ephemeral: a deploy/restart/crash wipes license.json.
# These env vars let the app re-activate ITSELF on boot with no manual step, so a
# customer's subscription (free or paid) is never interrupted by an update.
#   LICENSE_EMAIL — the email used at purchase. On boot we re-validate it against
#     the central server, which re-derives an active paid sub straight from Stripe
#     (survives any wipe until cancel / expiry / refund / declined renewal).
#   LICENSE_GRANT — an optional signed license JSON blob (as minted by the owner
#     grant tool). Verified by the owner signature and honored directly, so
#     comp/admin grants survive with zero dependency on the server or Stripe.
LICENSE_EMAIL = (os.environ.get("LICENSE_EMAIL") or "").strip()
LICENSE_GRANT = (os.environ.get("LICENSE_GRANT") or "").strip()


def _parse_grant_blob(raw: str):
    """Parse a LICENSE_GRANT value, tolerating common copy/paste slips. Returns
    the license dict or None. Auto-repair is SAFE: the signature is verified
    afterwards, so a wrongly-repaired blob simply fails that check and is
    ignored — it can never forge a license."""
    if not raw:
        return None
    s = raw.strip()
    # Strip surrounding quotes some UIs add around env values.
    if len(s) >= 2 and s[0] in "\"'" and s[-1] == s[0]:
        s = s[1:-1].strip()

    # A) Paste-proof form: base64-encoded JSON. Preferred, because base64 has no
    #    quotes/braces to drop or "smart-quote", so it survives any copy/paste.
    #    Strip ANY internal whitespace first — a wrapped paste can inject spaces
    #    or newlines that would otherwise fail the strict decoder.
    try:
        import base64, re
        b64s = re.sub(r"\s+", "", s)
        decoded = base64.b64decode(b64s, validate=True).decode("utf-8").strip()
        if decoded.startswith("{"):
            obj = json.loads(decoded)
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass

    # B) Raw JSON (with healing). Kept for backward compatibility.
    candidates = [s]
    # Heal a dropped leading '{' and/or trailing '}' (the classic paste slip).
    if s and not s.startswith("{"):
        candidates.append("{" + s)
    if s and not s.endswith("}"):
        candidates.append(s + "}")
    if s and not s.startswith("{") and not s.endswith("}"):
        candidates.append("{" + s + "}")
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


def _recover_license_on_boot() -> None:
    """Restore license.json after an ephemeral-disk wipe so the user is
    recognized automatically on every startup. Idempotent and safe to call every
    boot: it only acts when there is no already-active local license, never
    downgrades a good license, and never raises."""
    try:
        if _license_is_active():
            return  # already valid (e.g. restored from a persistent disk)

        # 1) Signed grant blob in env — trust it directly if it verifies + is live.
        if LICENSE_GRANT:
            grant = _parse_grant_blob(LICENSE_GRANT)
            if grant is None:
                print("[LICENSE] LICENSE_GRANT could not be parsed even after cleanup — "
                      "re-copy the ENTIRE line, including the leading '{' and trailing '}'.")
            elif _license_is_active(grant):
                _save_local_license(grant)
                print("[LICENSE] Recovered signed grant from LICENSE_GRANT env.")
                return
            else:
                print("[LICENSE] LICENSE_GRANT parsed but is invalid/expired — ignoring.")

        # 2) Re-validate the purchase email against the central server (Stripe is
        #    the source of truth, so an active paid sub is re-derived after a wipe).
        if LICENSE_EMAIL:
            try:
                r = requests.post(
                    f"{LICENSE_SERVER_URL}/api/license/validate",
                    json={"email": LICENSE_EMAIL, "appId": APP_ID},
                    timeout=20,
                )
                data = r.json()
            except Exception as e:
                print(f"[LICENSE] Boot recovery: server unreachable ({e}) — "
                      "staying on free tier until the next re-check.")
                return
            if data.get("status") == "active":
                _save_local_license(data)
                print(f"[LICENSE] Auto-reactivated {LICENSE_EMAIL} on boot "
                      f"(tier={data.get('tier')}).")
            else:
                print(f"[LICENSE] Boot recovery: no active subscription for "
                      f"{LICENSE_EMAIL} — running free tier.")
    except Exception as e:
        print(f"[LICENSE] Boot recovery unexpected error (non-fatal): {e}")

# In-memory warehouse for ticker/market data sent to the dashboard
market_data = []

# In-memory engine status (updated in-process by the integrated engine heartbeat).
# "state" is one of: starting | trading | paused | offline
_worker_status: Dict[str, Any] = {
    "running": False,
    "state": "starting",
    "mode": os.environ.get("TRADING_MODE", "paper"),
    "stocks": [s.strip().upper() for s in os.environ.get("STOCK_LIST", "AAPL,GOOG,TSLA,MSFT,AMZN").split(",") if s.strip()],
    "last_heartbeat": int(time.time()),
    "message": "Engine starting up..."
}

# In-memory ladder top 20 (updated every heartbeat)
_ladder_top20: List[Dict[str, Any]] = []

# In-memory AI trader toggle (can be overridden by worker via heartbeat)
_ai_trader_enabled = True

# ── Integrated engine globals ────────────────────────────────────────────
_engine: "TradingEngine | None" = None
_ladder: "PortfolioLadderScanner | None" = None
_supervisor_thread: "threading.Thread | None" = None
_RUN_SECONDS     = int(os.environ.get("RUN_SECONDS",             "21540"))
_LADDER_INTERVAL = int(os.environ.get("LADDER_INTERVAL",         "120"))
_HEARTBEAT_SECS  = int(os.environ.get("HEARTBEAT_EVERY_SECONDS", "10"))

# In-memory live trading settings — the engine polls this endpoint every cycle
_trading_settings: dict = {
    # ── Auto-trade master switch (toggled from UI) ───────────────────────────
    "auto_trade":          True,   # True = engine executes buys/sells autonomously
    # ── Core scan / execution settings ──────────────────────────────────────
    "poll_seconds":        int(os.environ.get("POLL_SECONDS",        "15")),
    "trailing_stop_pct":   float(os.environ.get("TRAILING_STOP_PCT", "3.0")),
    "loss_threshold":      float(os.environ.get("LOSS_THRESHOLD",    "5.0")),
    "max_trades_per_hour": int(os.environ.get("MAX_TRADES_PER_HOUR", "30")),
    "scan_all_market":     os.environ.get("SCAN_ALL_MARKET", "false").lower() == "true",
    "max_positions":       int(os.environ.get("MAX_POSITIONS",       "5")),
    "initial_capital":     float(os.environ.get("INITIAL_CAPITAL",   "0")),
    # ── Position sizing / risk controls ─────────────────────────────────────
    "risk_per_trade_pct":  float(os.environ.get("RISK_PER_TRADE_PCT",  "2.0")),
    "max_position_pct":    float(os.environ.get("MAX_POSITION_PCT",    "20.0")),
    "min_positions":       int(os.environ.get("MIN_POSITIONS",         "5")),
    "risk_per_trade_usd":  float(os.environ.get("RISK_PER_TRADE_USD",  "0")),
    # ── Signal quality filters ───────────────────────────────────────────────
    "rsi_buy_max":         float(os.environ.get("RSI_BUY_MAX",    "50.0")),
    "rsi_sell_min":        float(os.environ.get("RSI_SELL_MIN",   "70.0")),
    "sma_spread_min":      float(os.environ.get("SMA_SPREAD_MIN", "0.1")),
    # ── Forecast exit (sell before climb peaks) ──────────────────────────────
    "forecast_exit_enabled": True,
    # ── Portfolio Safety Shield ─────────────────────────────────────────
    "portfolio_stop_loss":   float(os.environ.get("PORTFOLIO_STOP_LOSS",   "0")),   # 0 = off
    "portfolio_stop_buffer": float(os.environ.get("PORTFOLIO_STOP_BUFFER", "200")),  # recovery gap
    "shield_enabled":        True,
    # ── 5hr 59min minimum hold rule ───────────────────────────────────────────
    "min_hold_seconds":      int(os.environ.get("MIN_HOLD_SECONDS", "21540")),  # 5h 59m
    # ── Paper / Live account (buyer-toggled; live is license-gated) ───────────
    # Stored value is the REQUESTED mode. The engine is handed the EFFECTIVE mode
    # via GET /api/settings/trading, which downgrades to paper unless live is
    # currently allowed. Always defaults to paper — real money is opt-in.
    "trading_mode":          os.environ.get("TRADING_MODE", "paper").lower(),
}


def _load_saved_settings() -> None:
    """Merge persisted settings from trading_settings.json into _trading_settings."""
    global _trading_settings
    if not os.path.exists(SETTINGS_FILE):
        return
    try:
        with open(SETTINGS_FILE, "r") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            _trading_settings.update(saved)
    except Exception:
        pass  # corrupted file — keep defaults


def _save_settings() -> None:
    """Write current _trading_settings to disk so they survive restarts."""
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(_trading_settings, f, indent=2)
    except Exception:
        pass


# Load any previously saved settings (overrides env var defaults)
_load_saved_settings()

# In-memory notifications log
_notifications: List[Dict[str, Any]] = []

# ---- Providers (server-side only) ----
# These are safe because values come from Render env vars; never sent to browser.
ALPACA_KEY = _clean_env_value("ALPACA_KEY", "")
ALPACA_SECRET = _clean_env_value("ALPACA_SECRET", "")
ALPACA_BASE_URL = _clean_env_value("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
ALPACA_DATA_FEED = (_clean_env_value("ALPACA_DATA_FEED", "iex") or "iex").lower()
if ALPACA_DATA_FEED not in ("iex", "sip"):
    ALPACA_DATA_FEED = "iex"
ALPHA_VANTAGE_KEY = _clean_env_value("ALPHA_VANTAGE_KEY", "")
# Separate LIVE credentials so the licensed Paper↔Live toggle can switch accounts
# without the buyer ever regenerating keys. Paper keys above stay paper; these
# stay live. Absent live keys = live simply cannot be enabled (fail safe).
ALPACA_LIVE_KEY    = _clean_env_value("ALPACA_LIVE_KEY", "")
ALPACA_LIVE_SECRET = _clean_env_value("ALPACA_LIVE_SECRET", "")

_alpaca = None        # paper client (always paper endpoint)
_alpaca_live = None   # live client, built lazily only when live is used
_alpha = None

if ALPACA_KEY and ALPACA_SECRET:
    _alpaca = REST(ALPACA_KEY, ALPACA_SECRET, base_url="https://paper-api.alpaca.markets")

if ALPHA_VANTAGE_KEY:
    _alpha = TimeSeries(key=ALPHA_VANTAGE_KEY, output_format="json")


def _live_keys_present() -> bool:
    return key_store.has_live_keys()


def _live_allowed():
    """(allowed, reason) — LIVE requires a valid signed license AND live keys.
    This is the single gate that enforces 'no real-money trading without paying'."""
    if not _license_is_active():
        return False, "No active license — subscribe to unlock live trading."
    if not _live_keys_present():
        return False, "Live Alpaca keys are not configured — add them in the Setup Wizard."
    return True, ""


def _requested_mode() -> str:
    m = str(_trading_settings.get("trading_mode", "paper")).lower()
    return "live" if m == "live" else "paper"


def _effective_mode() -> str:
    """What the engine/orders should ACTUALLY use. 'live' only when requested
    AND currently allowed; otherwise always 'paper'."""
    return "live" if (_requested_mode() == "live" and _live_allowed()[0]) else "paper"


def _get_live_client():
    global _alpaca_live
    if _alpaca_live is None and _live_keys_present():
        lk, ls = key_store.get_live_keys()
        _alpaca_live = REST(lk, ls, base_url="https://api.alpaca.markets")
    return _alpaca_live


def _active_alpaca():
    """The Alpaca client matching the current effective mode."""
    if _effective_mode() == "live":
        return _get_live_client()
    return _alpaca


# ── Tier / plan gating (Trader vs Pro) ────────────────────────────────────────
# The license carries a 'tier' (the price_map key it was bought under). Any tier
# starting with 'pro' is the Pro plan. Pro unlocks power features; the Safety
# Shield is intentionally NOT gated — loss protection is free for everyone.
TRADER_MAX_POSITIONS = 5
PRO_MAX_POSITIONS    = 15
PRO_ONLY_FEATURES    = ("scan_all_market", "forecast_exit_enabled")


def _license_tier() -> str:
    lic = _load_local_license()
    return str(lic.get("tier", "")) if _license_is_active(lic) else ""


def _is_pro() -> bool:
    return _license_tier().startswith("pro")


def _license_plan() -> str:
    tier = _license_tier()
    if not tier:
        return "Free"
    return "Pro" if tier.startswith("pro") else "Trader"


def _apply_pro_gating(resp: dict) -> None:
    """Force Pro-only features off (and cap positions) unless a Pro license is
    active. Applied to the settings the ENGINE reads, so gating holds no matter
    what the UI shows."""
    pro = _is_pro()
    resp["is_pro"] = pro
    resp["plan"]   = _license_plan()
    try:
        cur_pos = int(resp.get("max_positions", TRADER_MAX_POSITIONS) or TRADER_MAX_POSITIONS)
    except (TypeError, ValueError):
        cur_pos = TRADER_MAX_POSITIONS
    if pro:
        resp["max_positions"] = min(cur_pos, PRO_MAX_POSITIONS)
        resp["pro_locked"] = []
    else:
        for feat in PRO_ONLY_FEATURES:
            resp[feat] = False
        resp["max_positions"] = min(cur_pos, TRADER_MAX_POSITIONS)
        resp["pro_locked"] = list(PRO_ONLY_FEATURES) + ["max_positions"]

# ---- Quote cache (prevents hammering APIs) ----
_quote_cache: Dict[str, Dict[str, Any]] = {}   # sym -> {data, fetched_at}
_quote_cache_lock = Lock()
QUOTE_CACHE_TTL = int(os.environ.get("QUOTE_CACHE_TTL", "8"))  # seconds


@app.before_request
def _require_dashboard_login():
    """Gate the trading dashboard + control endpoints behind DASHBOARD_PASSWORD.
    No-op when no password is set (gate off) or the path is public."""
    if not DASHBOARD_PASSWORD:
        return None
    if _path_is_public(request.path):
        return None
    device_id = _get_device_id_from_cookie()
    allow_bypass, owner_email = _trusted_device_allows_bypass(device_id)
    if allow_bypass:
        session["dash_authed"] = True
        session["owner_email"] = owner_email
        session.permanent = True
        return None
    if _trusted_device_reauth_due(device_id):
        session.pop("dash_authed", None)
        session.pop("owner_email", None)
    if session.get("dash_authed"):
        return None
    # The in-process trading engine authenticates its OWN calls (heartbeat,
    # settings poll, notifications) with a shared token = FLASK_SECRET, so the
    # gate never blocks the engine ↔ dashboard link. Public visitors don't have
    # this token; it's never exposed to the browser.
    tok = request.headers.get("X-Internal-Token", "")
    if tok and hmac.compare_digest(tok.encode("utf-8"), str(app.config["SECRET_KEY"]).encode("utf-8")):
        return None
    # Not logged in: API callers get 401 JSON; browsers get the login page.
    if request.path.startswith("/api/"):
        return jsonify({"status": "error", "message": "Authentication required. Log in first."}), 401
    return redirect("/login")


def _login_page(error: str = "") -> str:
    note = (f'<p class="err">&#9888;&#65039; {error}</p>' if error else "")
    owner_hint = ""
    if _trusted_owner_emails():
        owner_hint = (
            '<p class="sub">New device for owner accounts: enter owner email '
            'plus dashboard password. Trusted devices are re-verified every few months.</p>'
        )
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sign in — Alien AI Trader</title><link rel="icon" href="/favicon.svg">
<style>body{{background:#060c18;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;
display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:16px}}
.card{{background:#0d1626;border:1px solid #1e3058;border-radius:14px;max-width:380px;width:100%;padding:32px;text-align:center}}
h1{{font-size:1.35rem;margin:.2rem 0 1rem;background:linear-gradient(135deg,#4ade80,#60a5fa);
-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
input{{width:100%;box-sizing:border-box;padding:12px;margin:8px 0;border-radius:8px;
border:1px solid #1e3058;background:#0a1220;color:#e2e8f0;font-size:1rem}}
button{{width:100%;padding:12px;margin-top:10px;border:0;border-radius:8px;cursor:pointer;
background:linear-gradient(135deg,#22c55e,#16a34a);color:#fff;font-weight:700;font-size:1rem}}
.err{{color:#fbbf24;font-size:.9rem}} .sub{{color:#94a3b8;font-size:.85rem;margin-top:0}}</style>
</head><body><div class="card">
<h1>&#128123; Alien AI Trader</h1>
<p class="sub">Enter your dashboard password to continue.</p>
{owner_hint}
{note}
<form method="POST" action="/login">
<input type="email" name="owner_email" placeholder="Owner email (required on new owner devices)">
<input type="password" name="password" placeholder="Dashboard password" autofocus required>
<button type="submit">Sign in</button>
</form></div></body></html>"""


@app.route("/login", methods=["GET", "POST"])
def dashboard_login():
    if not DASHBOARD_PASSWORD:
        return redirect("/")   # nothing to log into
    if request.method == "POST":
        supplied = _normalize_dashboard_password(request.form.get("password") or "")
        owner_email = _norm_email(request.form.get("owner_email") or "")
        accepted = _dashboard_password_candidates()
        trusted_emails = _trusted_owner_emails()
        device_id = _get_device_id_from_cookie()
        known_rec = _get_trusted_record(device_id) if device_id else {}
        known_email = _norm_email(known_rec.get("email", "")) if known_rec else ""
        known_is_owner = bool(known_email and known_email in trusted_emails)
        reauth_due = _trusted_device_reauth_due(device_id)
        # Constant-time compare (on bytes, so a non-ASCII password never errors).
        ok = any(
            hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))
            for expected in accepted
        )
        if ok:
            # For owner accounts, a new device must provide owner email once.
            if trusted_emails and (not known_is_owner or reauth_due) and owner_email not in trusted_emails:
                return _login_page("Enter owner email plus password for new or re-verification login."), 401

            if owner_email in trusted_emails:
                known_email = owner_email

            if known_email in trusted_emails:
                if not device_id:
                    device_id = _new_device_id()
                _mark_trusted_device(device_id, known_email)
                session["owner_email"] = known_email

            session["dash_authed"] = True
            session.permanent = True
            resp = redirect("/")
            if device_id:
                resp.set_cookie(
                    TRUSTED_DEVICE_COOKIE,
                    device_id,
                    max_age=60 * 60 * 24 * 400,
                    httponly=True,
                    samesite="Lax",
                    secure=request.is_secure,
                )
            return resp
        return _login_page("Incorrect password."), 401
    return _login_page(), 200


@app.route("/logout", methods=["GET", "POST"])
def dashboard_logout():
    session.pop("dash_authed", None)
    return redirect("/login")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/api/owner/freeze/status", methods=["GET"])
def owner_freeze_status():
    with _owner_freeze_lock:
        state = _load_owner_freeze_state()
    return jsonify({
        "enabled": _owner_freeze_enabled(),
        "locked": bool(state.get("locked", False)) if _owner_freeze_enabled() else False,
        "updated_at": int(state.get("updated_at", 0) or 0),
        "updated_by": state.get("updated_by", ""),
    }), 200


@app.route("/api/owner/freeze", methods=["POST"])
def owner_freeze_set():
    if not _owner_freeze_enabled():
        return jsonify({
            "status": "error",
            "message": "OWNER_FREEZE_TOKEN is not configured for this deployment.",
        }), 400

    payload = request.json or {}
    token = payload.get("token") or ""
    if not _owner_freeze_token_ok(token):
        return jsonify({"status": "error", "message": "Invalid owner freeze token."}), 403

    lock_value = bool(payload.get("locked", True))
    actor = _norm_email(session.get("owner_email") or "") or "owner"
    with _owner_freeze_lock:
        state = {
            "locked": lock_value,
            "updated_at": int(time.time()),
            "updated_by": actor,
        }
        _save_owner_freeze_state(state)
    return jsonify({"status": "ok", **state}), 200


def _alpaca_auth_probe(key, secret, base_url):
    """Lightweight credential check — returns (ok, detail). Makes one read-only
    get_account() call. NEVER returns secret values, only the pass/fail and the
    broker's error text (e.g. 'request is not authorized')."""
    if not key or not secret:
        return False, "keys not set"
    last_err = "unknown error"
    for attempt in range(3):
        try:
            acct = REST(key, secret, base_url=base_url).get_account()
            return True, f"authorized (account status: {getattr(acct, 'status', 'unknown')})"
        except Exception as e:
            last_err = str(e)
            if attempt < 2 and _is_transient_broker_error(last_err):
                time.sleep(1.0 + (attempt * 1.0))
                continue
            break
    return False, last_err


def _is_transient_broker_error(detail: str) -> bool:
    txt = (detail or "").strip().lower()
    if not txt:
        return False
    transient_tokens = (
        "connection aborted",
        "remotedisconnected",
        "remote end closed connection",
        "connection reset",
        "max retries exceeded",
        "timed out",
        "timeout",
        "temporarily unavailable",
        "bad gateway",
        "service unavailable",
        "502",
        "503",
        "504",
        "ssl eof",
        "name or service not known",
        "temporary failure in name resolution",
    )
    return any(token in txt for token in transient_tokens)


@app.route("/api/engine/diag", methods=["GET"])
def engine_diag():
    """Config self-check (no secrets exposed). Confirms the data key is present
    and whether each Alpaca key pair actually authorizes against its endpoint —
    so a deployment can be verified from a browser instead of digging through
    logs. Mirrors the two failures the engine hits at startup: a missing
    ALPHA_VANTAGE_KEY and an unauthorized Alpaca login."""
    alpha_present = bool(key_store.get_alpha_key())

    paper_ok, paper_detail = _alpaca_auth_probe(
        ALPACA_KEY, ALPACA_SECRET, "https://paper-api.alpaca.markets")

    live_key, live_secret = key_store.get_live_keys()
    if live_key and live_secret:
        live_ok, live_detail = _alpaca_auth_probe(
            live_key, live_secret, "https://api.alpaca.markets")
    else:
        live_ok, live_detail = False, "live keys not set (optional)"

    return jsonify({
        # True only when the engine could actually boot and trade paper.
        "engine_can_start": alpha_present and paper_ok,
        "alpha_vantage_key": {
            "present": alpha_present,
            "from_env": bool(os.environ.get("ALPHA_VANTAGE_KEY")),
            "hint": None if alpha_present else
                    "Set ALPHA_VANTAGE_KEY in Render env vars (exact name), then redeploy.",
        },
        "alpaca_paper": {
            "keys_present": bool(ALPACA_KEY and ALPACA_SECRET),
            "authorized": paper_ok,
            "detail": paper_detail,
            "hint": None if paper_ok else
                    "Paper keys must be generated in Alpaca's PAPER dashboard and go in "
                    "ALPACA_KEY / ALPACA_SECRET. LIVE keys do NOT authorize on the paper "
                    "endpoint. Re-copy both key and secret together; check for stray spaces.",
        },
        "alpaca_live": {
            "keys_present": bool(live_key and live_secret),
            "authorized": live_ok,
            "detail": live_detail,
        },
        "requested_mode": _requested_mode(),
        "effective_mode": _effective_mode(),
    }), 200


@app.route("/api/support/snapshot", methods=["GET"])
def support_snapshot():
    """Non-secret runtime snapshot to troubleshoot customer blueprints quickly."""
    alpha_present = bool(key_store.get_alpha_key())
    paper_ok, paper_detail = _alpaca_auth_probe(
        ALPACA_KEY, ALPACA_SECRET, "https://paper-api.alpaca.markets")
    live_key, live_secret = key_store.get_live_keys()
    live_ok, live_detail = _alpaca_auth_probe(
        live_key, live_secret, "https://api.alpaca.markets") if (live_key and live_secret) else (False, "live keys not set")

    status = dict(_worker_status)
    last = status.get("last_heartbeat")
    stale = (int(time.time()) - int(last)) if last is not None else None

    return jsonify({
        "timestamp": int(time.time()),
        "app": {
            "version": os.environ.get("APP_VERSION", "unknown"),
            "render_service": os.environ.get("RENDER_SERVICE_NAME", "local"),
            "render_commit": os.environ.get("RENDER_GIT_COMMIT", "local"),
            "python": sys.version.split()[0],
        },
        "engine": {
            "state": status.get("state"),
            "running": bool(status.get("running")),
            "message": status.get("message"),
            "stale_seconds": stale,
            "requested_mode": _requested_mode(),
            "effective_mode": _effective_mode(),
        },
        "license": {
            "active": _license_is_active(),
            "live_allowed": _live_allowed()[0],
            "live_block_reason": _live_allowed()[1],
        },
        "keys": {
            "alpha_vantage_present": alpha_present,
            "paper_keys_present": bool(ALPACA_KEY and ALPACA_SECRET),
            "paper_authorized": paper_ok,
            "paper_detail": paper_detail,
            "live_keys_present": bool(live_key and live_secret),
            "live_authorized": live_ok,
            "live_detail": live_detail,
        },
        "settings": {
            "market_hours_only": _MARKET_HOURS_ONLY,
            "heartbeat_seconds": _HEARTBEAT_SECS,
            "poll_seconds": _trading_settings.get("poll_seconds"),
            "scan_all_market": _trading_settings.get("scan_all_market"),
            "max_positions": _trading_settings.get("max_positions"),
        }
    }), 200


@app.route("/api/support/payload", methods=["GET"])
def support_payload():
    """One-shot support bundle (non-secret) for customer troubleshooting."""
    alpha_present = bool(key_store.get_alpha_key())
    paper_ok, paper_detail = _alpaca_auth_probe(
        ALPACA_KEY, ALPACA_SECRET, "https://paper-api.alpaca.markets")
    live_key, live_secret = key_store.get_live_keys()
    live_ok, live_detail = _alpaca_auth_probe(
        live_key, live_secret, "https://api.alpaca.markets") if (live_key and live_secret) else (False, "live keys not set")

    status = dict(_worker_status)
    last = status.get("last_heartbeat")
    stale = (int(time.time()) - int(last)) if last is not None else None

    # Include compact quote diagnostics so support can see exactly where
    # market-data retrieval succeeds/fails without requiring extra API calls.
    quote_symbols = []
    try:
        from_positions = list((status.get("positions") or {}).keys())
        from_watchlist = list(status.get("stocks") or [])
        quote_symbols = list(dict.fromkeys([
            *(str(s).upper() for s in from_positions),
            *(str(s).upper() for s in from_watchlist),
        ]))[:10]
    except Exception:
        quote_symbols = []

    quote_diag = {
        "configured_feed": ALPACA_DATA_FEED,
        "effective_mode": _effective_mode(),
        "symbols": quote_symbols,
        "results": [],
    }
    try:
        active_client = _active_alpaca()
        feed_order = [ALPACA_DATA_FEED]
        if ALPACA_DATA_FEED != "iex":
            feed_order.append("iex")
        for sym in quote_symbols:
            d = _quote_diag_symbol(sym, active_client, feed_order)
            quote_diag["results"].append({
                "symbol": d.get("symbol"),
                "provider": (d.get("result") or {}).get("provider"),
                "price": (d.get("result") or {}).get("price"),
                "change_percent": (d.get("result") or {}).get("change_percent"),
                "attempts": d.get("attempts", []),
            })
    except Exception as e:
        quote_diag["error"] = str(e)

    payload = {
        "timestamp": int(time.time()),
        "capture": {
            "requested_by": "dashboard_ui",
            "schema": "support-payload-v1",
        },
        "app": {
            "version": os.environ.get("APP_VERSION", "unknown"),
            "render_service": os.environ.get("RENDER_SERVICE_NAME", "local"),
            "render_commit": os.environ.get("RENDER_GIT_COMMIT", "local"),
            "python": sys.version.split()[0],
        },
        "engine_status": {
            "state": status.get("state"),
            "running": bool(status.get("running")),
            "message": status.get("message"),
            "stale_seconds": stale,
            "requested_mode": _requested_mode(),
            "effective_mode": _effective_mode(),
        },
        "engine_diag": {
            "engine_can_start": alpha_present and (live_ok if _effective_mode() == "live" else paper_ok),
            "alpha_vantage_key": {
                "present": alpha_present,
                "from_env": bool(os.environ.get("ALPHA_VANTAGE_KEY")),
            },
            "alpaca_paper": {
                "keys_present": bool(ALPACA_KEY and ALPACA_SECRET),
                "authorized": paper_ok,
                "detail": paper_detail,
            },
            "alpaca_live": {
                "keys_present": bool(live_key and live_secret),
                "authorized": live_ok,
                "detail": live_detail,
            },
            "requested_mode": _requested_mode(),
            "effective_mode": _effective_mode(),
        },
        "license": {
            "active": _license_is_active(),
            "live_allowed": _live_allowed()[0],
            "live_block_reason": _live_allowed()[1],
        },
        "settings": {
            "trading_mode_requested": _requested_mode(),
            "trading_mode_effective": _effective_mode(),
            "market_hours_only": _MARKET_HOURS_ONLY,
            "heartbeat_seconds": _HEARTBEAT_SECS,
            "poll_seconds": _trading_settings.get("poll_seconds"),
            "scan_all_market": _trading_settings.get("scan_all_market"),
            "max_positions": _trading_settings.get("max_positions"),
            "max_trades_per_hour": _trading_settings.get("max_trades_per_hour"),
            "auto_trade": bool(_trading_settings.get("auto_trade", True)),
        },
        "quotes_diag": quote_diag,
        "notes": [
            "No secrets are included in this payload.",
            "Share this JSON with support to diagnose offline/live issues quickly.",
            "quotes_diag shows per-symbol quote provider/feed attempts.",
        ],
    }
    return jsonify(payload), 200


@app.route("/favicon.svg", methods=["GET"])
def favicon_svg():
    resp = app.make_response(FAVICON_SVG)
    resp.headers["Content-Type"] = "image/svg+xml"
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.route("/thankyou", methods=["GET"])
def thankyou():
    """Post-purchase landing page — Stripe payment links redirect here so
    buyers know exactly how to activate. No payment data touches this page."""
    return """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Payment received — Alien AI Trader</title>
<style>body{background:#060c18;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;
display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:16px}
.card{background:#0d1626;border:1px solid #1e3058;border-radius:14px;max-width:560px;padding:32px}
h1{font-size:1.5rem;background:linear-gradient(135deg,#4ade80,#60a5fa);
-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.step{display:flex;gap:12px;margin:14px 0;align-items:flex-start}
.n{background:#22c55e;color:#fff;border-radius:50%;width:26px;height:26px;flex-shrink:0;
display:flex;align-items:center;justify-content:center;font-weight:700;font-size:.85rem}
p,li{color:#94a3b8;line-height:1.6;font-size:.95rem}
.hl{color:#4ade80;font-weight:600}
.note{background:rgba(245,158,11,.08);border:1px solid rgba(245,158,11,.3);
border-radius:8px;padding:10px 14px;font-size:.85rem;color:#fbbf24;margin-top:18px}</style>
</head><body><div class="card">
<h1>&#128640; Payment received — let's unlock live trading</h1>
<p>Your subscription is active. Three steps to switch on live trading:</p>
<div class="step"><div class="n">1</div><p>Open <span class="hl">Alien AI Trader</span> on your computer
(double-click the desktop shortcut).</p></div>
<div class="step"><div class="n">2</div><p>Go to the <span class="hl">Settings</span> tab →
<span class="hl">License — Live Trading</span> card.</p></div>
<div class="step"><div class="n">3</div><p>Enter <span class="hl">the email you just used at checkout</span>
and click <span class="hl">Activate</span>. The badge flips to &#128994; Licensed.</p></div>
<div class="note">&#9888; Use the exact checkout email. If Stripe auto-filled your saved details
(“Link”), that saved email is the one to use. Find it on your receipt from Stripe.</div>
<p style="margin-top:18px;font-size:.8rem">Need help? Reply to your receipt email.
— T-Dub's Apps</p>
</div></body></html>""", 200


@app.route("/get", methods=["GET"])
@app.route("/store", methods=["GET"])
def get_your_trader():
    """Shareable landing page. THIS is the URL Troy hands out. A visitor lands
    here, downloads the installer (free), and can subscribe to unlock live
    trading or deploy their own private cloud copy. No trading dashboard is
    exposed here — that lives at '/'. Prices load live from the price map so a
    price change (e.g. annual $199) shows here with no redeploy."""
    html = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Get Alien AI Trader</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<style>
:root{--green:#22c55e;--green2:#4ade80;--blue:#2563eb;--bg:#060c18;--card:#0d1626;
--border:#1e3058;--text:#e2e8f0;--muted:#94a3b8;--gold:#fbbf24}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;
line-height:1.6;padding:24px 16px}
.wrap{max-width:640px;margin:0 auto;display:flex;flex-direction:column;gap:22px}
.hero{text-align:center}
.hero h1{font-size:clamp(1.8rem,5vw,2.6rem);font-weight:900;letter-spacing:.03em;
background:linear-gradient(135deg,#4ade80,#60a5fa);-webkit-background-clip:text;
-webkit-text-fill-color:transparent;background-clip:text}
.hero .sub{color:var(--muted);font-size:.95rem}
.dl-btn{display:block;text-align:center;text-decoration:none;font-weight:900;
font-size:clamp(1.15rem,3.5vw,1.6rem);letter-spacing:.02em;color:#04120a;
background:linear-gradient(135deg,#4ade80,#22c55e);border-radius:14px;
padding:20px 24px;box-shadow:0 8px 30px rgba(34,197,94,.35);
border:1px solid #16a34a;transition:transform .12s,box-shadow .2s}
.dl-btn:hover{transform:translateY(-2px);box-shadow:0 12px 40px rgba(34,197,94,.5)}
.dl-sub{text-align:center;color:var(--muted);font-size:.82rem;margin-top:-10px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px 20px}
.card h2{font-size:1.05rem;margin-bottom:10px;color:var(--green2)}
.steps{list-style:none;counter-reset:s;display:flex;flex-direction:column;gap:10px}
.steps li{counter-increment:s;padding-left:38px;position:relative;color:var(--muted);font-size:.92rem}
.steps li::before{content:counter(s);position:absolute;left:0;top:0;width:26px;height:26px;
background:var(--green);color:#04120a;border-radius:50%;font-weight:700;font-size:.85rem;
display:flex;align-items:center;justify-content:center}
.steps li b{color:var(--text)}
.price-grid{display:flex;flex-wrap:wrap;gap:12px}
.price{flex:1 1 200px;background:#0a1220;border:1px solid var(--border);border-radius:10px;
padding:16px;text-align:center}
.price .amt{font-size:1.6rem;font-weight:900;color:var(--text)}
.price .per{color:var(--muted);font-size:.8rem}
.price a{display:block;margin-top:10px;text-decoration:none;background:rgba(37,99,235,.25);
border:1px solid var(--blue);color:#93c5fd;border-radius:8px;padding:10px;font-weight:700}
.price a:hover{background:rgba(37,99,235,.45)}
.secondary{display:flex;flex-wrap:wrap;gap:12px}
.secondary a{flex:1 1 200px;text-align:center;text-decoration:none;color:var(--text);
background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px;font-weight:600}
.secondary a:hover{border-color:#2e4a7a;background:#162039}
.note{background:rgba(245,158,11,.08);border:1px solid rgba(245,158,11,.3);border-radius:8px;
padding:10px 14px;font-size:.85rem;color:var(--gold)}
footer{text-align:center;color:var(--muted);font-size:.78rem;padding-top:8px}
footer a{color:#60a5fa;text-decoration:none}
</style></head><body><div class="wrap">
  <div class="hero">
    <h1>&#128123; Alien AI Trader</h1>
    <div class="sub">AI-powered stock trading on autopilot &mdash; scans, buys the climb, sells the peak.</div>
  </div>

  <a class="dl-btn" href="__DEPLOY__" target="_blank" rel="noopener">&#9729;&#65039; Deploy Your Personal Trader on Render</a>
  <div class="dl-sub">Free &middot; runs in the cloud 24/7 (no PC needed) &middot; starts in safe <b>paper mode</b> (practice money)</div>

  <div class="card">
    <h2>How it works &mdash; 4 easy steps</h2>
    <ol class="steps">
      <li><b>Click "Deploy on Render" above</b> and sign in to a free Render account. You get your <b>own private copy</b> &mdash; nothing shared.</li>
      <li><b>Paste 2 free keys when Render asks:</b> your <b>Alpaca</b> keys (your broker) and an <b>Alpha Vantage</b> key (market data). Both free &mdash; links below. Leave the other boxes blank.</li>
      <li><b>Click Deploy and wait a few minutes.</b> Your app opens at its own web address, already trading on <b>paper (practice money) &mdash; free, zero risk</b>.</li>
      <li><b>Subscribe to unlock live trading</b>, add your live Alpaca keys, then flip the in-app <b>Paper &harr; Live</b> switch for real money.</li>
    </ol>
    <div class="secondary" style="margin-top:12px">
      <a href="https://app.alpaca.markets/signup" target="_blank" rel="noopener">Get free Alpaca keys</a>
      <a href="https://www.alphavantage.co/support/#api-key" target="_blank" rel="noopener">Get free Alpha Vantage key</a>
      <a href="__REPO__#-render-cloud-deployment-advanced" target="_blank" rel="noopener">Cloud setup guide</a>
    </div>
  </div>

  <div class="card">
    <h2>Unlock Live (Real-Money) Trading</h2>
    <p style="color:var(--muted);font-size:.9rem;margin-bottom:12px">Paper trading is free forever. A subscription unlocks the licensed live-trading switch inside the app.</p>
    <div class="price-grid" id="priceGrid">Loading prices&hellip;</div>
  </div>

  <div class="card">
    <h2>Prefer to Run It on Your Home PC?</h2>
    <p style="color:var(--muted);font-size:.9rem;margin-bottom:12px">The same download runs 100% locally &mdash; no cloud, no account with us. Paper trading is free; a subscription unlocks live.</p>
    <div class="secondary">
      <a href="__ZIP__">&#128190; Download for Home Use</a>
      <a href="__REPO__#readme" target="_blank" rel="noopener">&#128214; Full README</a>
    </div>
  </div>

  <div class="note">&#9888;&#65039; Live trading needs your own Alpaca account (the wizard sets it up in minutes) and a subscription. The app always starts in paper mode &mdash; you choose when to go live.</div>

  <footer>&#128123; Alien AI Trader &middot; T-Dub's Apps &middot; 2026<br>
    <a href="/">Open the live dashboard</a> &nbsp;|&nbsp; <a href="__REPO__" target="_blank" rel="noopener">GitHub</a></footer>
</div>
<script>
(function(){
  var repo="__REPO__";
  fetch('/api/license/pricing-proxy').then(function(r){return r.json();}).then(function(tiers){
    var grid=document.getElementById('priceGrid');
    if(!tiers||!tiers.length){grid.innerHTML='<p style="color:var(--muted)">Subscription options are loading &mdash; refresh in a moment.</p>';return;}
    grid.innerHTML='';
    tiers.forEach(function(t){
      if(!t.buyUrl||t.buyUrl.indexOf('REPLACE')!==-1)return;
      var plan=t.plan||((''+t.tier).indexOf('pro')===0?'Pro':'Trader');
      var per=(t.billingType==='annual')?'per year':(t.billingType==='monthly')?'per month':'one-time';
      var el=document.createElement('div');el.className='price';
      el.innerHTML='<div class="per" style="font-weight:700;color:var(--text)">'+plan+'</div>'+
        '<div class="amt">$'+t.price+'</div><div class="per">'+per+'</div>'+
        '<a href="'+t.buyUrl+'" target="_blank" rel="noopener">Subscribe</a>';
      grid.appendChild(el);
    });
    if(!grid.children.length){grid.innerHTML='<p style="color:var(--muted)">Live checkout links are being finalized.</p>';}
  }).catch(function(){
    document.getElementById('priceGrid').innerHTML='<p style="color:var(--muted)">Could not load prices &mdash; please refresh.</p>';
  });
})();
</script>
</body></html>"""
    html = (html.replace("__ZIP__", DOWNLOAD_ZIP_URL)
                .replace("__DEPLOY__", RENDER_DEPLOY_URL)
                .replace("__REPO__", GITHUB_REPO_URL))
    response = app.make_response(html)
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    return response


ADMIN_PATH = os.environ.get("ADMIN_PATH", "").strip()


@app.route("/admin/<token>", methods=["GET"])
def admin_panel(token):
    """Owner console, reachable ONLY at /admin/<ADMIN_PATH>, where ADMIN_PATH is a
    secret slug you set as a Render env var. Every other path returns 404, so the
    console is not publicly discoverable. Actions still require LICENSE_SECRET
    (which is brute-force locked in license_api). Unset ADMIN_PATH = page disabled."""
    if not ADMIN_PATH or token != ADMIN_PATH:
        return "Not Found", 404
    html = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Alien AI Trader — Admin</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<style>
:root{--bg:#060c18;--card:#0d1626;--border:#1e3058;--text:#e2e8f0;--muted:#94a3b8;
--green:#22c55e;--green2:#4ade80;--blue:#2563eb;--red:#ef4444;--gold:#fbbf24}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;
padding:18px 14px;line-height:1.5}
.wrap{max-width:460px;margin:0 auto;display:flex;flex-direction:column;gap:16px}
h1{font-size:1.3rem;text-align:center;background:linear-gradient(135deg,#4ade80,#60a5fa);
-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.sub{text-align:center;color:var(--muted);font-size:.8rem;margin-top:-8px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px}
.card h2{font-size:.95rem;color:var(--green2);margin-bottom:10px}
label{display:block;font-size:.78rem;color:var(--muted);margin:8px 0 4px}
input,select{width:100%;padding:11px;border-radius:9px;border:1px solid var(--border);
background:#0a1220;color:var(--text);font-size:1rem}
.row{display:flex;gap:8px;align-items:center}
.row input[type=checkbox]{width:auto}
button{width:100%;padding:12px;border-radius:9px;border:0;font-weight:700;font-size:.95rem;
cursor:pointer;margin-top:12px;color:#04120a}
.b-green{background:var(--green2)} .b-blue{background:#60a5fa} .b-red{background:var(--red);color:#fff}
.small{font-size:.72rem;color:var(--muted);margin-top:8px}
#result{white-space:pre-wrap;word-break:break-word;font-family:ui-monospace,Menlo,monospace;
font-size:.8rem;background:#0a1220;border:1px solid var(--border);border-radius:9px;
padding:12px;min-height:44px;color:var(--text)}
.ok{color:var(--green2)} .err{color:#fca5a5}
</style></head><body><div class="wrap">
  <div><h1>&#128123; Admin Console</h1><div class="sub">Grant &amp; manage licenses from any device</div></div>

  <div class="card">
    <h2>&#128273; Admin Secret</h2>
    <input id="secret" type="password" placeholder="Your LICENSE_SECRET" autocomplete="off">
    <div class="row" style="margin-top:8px"><input id="remember" type="checkbox"><label style="margin:0">Remember on this device</label></div>
    <div class="small">Required for grant/revoke. Stored only in this browser if you check the box. <a href="#" onclick="forget();return false;" style="color:#60a5fa">Forget</a></div>
  </div>

  <div class="card">
    <h2>&#127873; Grant / Comp a License</h2>
    <label>Customer email</label>
    <input id="g_email" type="email" placeholder="person@example.com" autocomplete="off">
    <label>Plan</label>
    <select id="g_tier">
      <option value="monthly">Trader &middot; Monthly (30 days)</option>
      <option value="annual">Trader &middot; Annual (365 days)</option>
      <option value="pro_monthly">Pro &middot; Monthly (30 days)</option>
      <option value="pro_annual">Pro &middot; Annual (365 days)</option>
    </select>
    <button class="b-green" onclick="grant()">Grant License</button>
    <div class="small">They activate in the app by entering this exact email.</div>
  </div>

  <div class="card">
    <h2>&#128269; Look Up</h2>
    <label>Email</label>
    <input id="l_email" type="email" placeholder="person@example.com" autocomplete="off">
    <button class="b-blue" onclick="lookup()">Check Status</button>
  </div>

  <div class="card">
    <h2>&#9940; Revoke</h2>
    <label>Email</label>
    <input id="r_email" type="email" placeholder="person@example.com" autocomplete="off">
    <button class="b-red" onclick="revoke()">Revoke License</button>
  </div>

  <div class="card"><h2>Result</h2><div id="result">Ready.</div></div>
  <div class="small" style="text-align:center">&#128123; Alien AI Trader &middot; T-Dub's Apps</div>
</div>
<script>
var APP_ID='alien-ai-trader';
var R=document.getElementById('result');
function show(msg,cls){R.className=cls||'';R.textContent=msg;}
(function(){var s=localStorage.getItem('aat_admin_secret');if(s){document.getElementById('secret').value=s;document.getElementById('remember').checked=true;}})();
function forget(){localStorage.removeItem('aat_admin_secret');document.getElementById('secret').value='';document.getElementById('remember').checked=false;show('Secret forgotten on this device.');}
function secret(){var s=document.getElementById('secret').value.trim();
  if(document.getElementById('remember').checked&&s)localStorage.setItem('aat_admin_secret',s);
  else localStorage.removeItem('aat_admin_secret');
  return s;}
function fmt(ms){try{return new Date(+ms).toLocaleString();}catch(e){return ms;}}
function pretty(d){
  if(d.status==='granted')return 'GRANTED\\n'+d.tier+' to '+d.email+'\\nkey '+d.licenseKey+'\\nexpires '+fmt(d.expiresAt);
  if(d.status==='revoked')return 'REVOKED\\n'+d.email;
  if(d.status==='active'||d.status==='expired')return d.status.toUpperCase()+'\\n'+(d.tier||'')+' · '+d.email+'\\nexpires '+fmt(d.expiresAt);
  if(d.status==='none')return 'No license found for that email.';
  return JSON.stringify(d,null,2);
}
async function call(url,opts){
  try{var r=await fetch(url,opts);var d=await r.json();
    if(!r.ok){show((d.error||('HTTP '+r.status)),'err');return null;}
    return d;
  }catch(e){show('Network error — is the server awake? '+e,'err');return null;}
}
async function grant(){
  var s=secret();if(!s)return show('Enter your admin secret first.','err');
  var email=document.getElementById('g_email').value.trim();if(!email)return show('Enter an email.','err');
  var tier=document.getElementById('g_tier').value;
  show('Granting…');
  var d=await call('/api/license/admin/grant',{method:'POST',
    headers:{'Content-Type':'application/json','Authorization':'Bearer '+s},
    body:JSON.stringify({email:email,appId:APP_ID,tier:tier})});
  if(d)show(pretty(d),'ok');
}
async function revoke(){
  var s=secret();if(!s)return show('Enter your admin secret first.','err');
  var email=document.getElementById('r_email').value.trim();if(!email)return show('Enter an email.','err');
  if(!confirm('Revoke the license for '+email+'? They drop to free paper mode.'))return;
  show('Revoking…');
  var d=await call('/api/license/admin/revoke',{method:'POST',
    headers:{'Content-Type':'application/json','Authorization':'Bearer '+s},
    body:JSON.stringify({email:email,appId:APP_ID})});
  if(d)show(pretty(d),'ok');
}
async function lookup(){
  var email=document.getElementById('l_email').value.trim();if(!email)return show('Enter an email.','err');
  show('Checking…');
  var d=await call('/api/license/status',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({email:email,appId:APP_ID})});
  if(d)show(pretty(d), d.status==='active'?'ok':'');
}
</script></body></html>"""
    response = app.make_response(html)
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@app.route("/")
def index():
    mode = "VIP" if request.args.get("access") == "SOVEREIGN_TESTER" else "GUEST"
    try:
        resp = render_template("dashboard.html", mode=mode)
        response = app.make_response(resp)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as e:
        return f"❌ TEMPLATE ERROR: Looking in {template_dir}. Details: {e}", 500


@app.route("/api/tickers", methods=["GET"])
def get_tickers():
    return jsonify(market_data if market_data else []), 200


@app.route("/api/update_market", methods=["POST"])
def receive_data():
    global market_data
    try:
        data = request.json
        if data:
            market_data = data
            # Push to all connected browser clients immediately via WebSocket
            socketio.emit("market_update", {"tickers": market_data})
            return jsonify({"status": "Success", "count": len(market_data)}), 200
    except Exception as e:
        return jsonify({"status": "Error", "message": str(e)}), 400
    return jsonify({"status": "No Data"}), 200


# --- Engine heartbeat ingest ---
# The integrated engine updates _worker_status in-process; this HTTP route is
# kept so an external engine process (legacy/worker.py) can still report in.

@app.route("/api/worker/heartbeat", methods=["POST"])
def worker_heartbeat():
    global _worker_status, _ladder_top20
    try:
        payload = request.json or {}
        _worker_status.update({
            "running":      bool(payload.get("running", True)),
            "mode":         payload.get("mode",        _worker_status.get("mode")),
            "stocks":       payload.get("stock_list",  payload.get("stocks", _worker_status.get("stocks"))),
            "profit":       payload.get("profit",      _worker_status.get("profit")),
            "positions":    payload.get("positions",   _worker_status.get("positions")),
            "signals":      payload.get("signals",     _worker_status.get("signals")),
            "trade_count":  payload.get("trade_count", _worker_status.get("trade_count")),
            "capital":      payload.get("capital",     _worker_status.get("capital")),
            "trailing_stop_pct":    payload.get("trailing_stop_pct",    _worker_status.get("trailing_stop_pct")),
            "loss_threshold":       payload.get("loss_threshold",       _worker_status.get("loss_threshold")),
            "scan_all_market":      payload.get("scan_all_market",      _worker_status.get("scan_all_market")),
            "max_positions":        payload.get("max_positions",        _worker_status.get("max_positions")),
            "min_positions":        payload.get("min_positions",        _worker_status.get("min_positions")),
            "trading_mode":         payload.get("trading_mode",         _worker_status.get("trading_mode")),
            "live_trading_enabled": payload.get("live_trading_enabled", _worker_status.get("live_trading_enabled", False)),
            "risk_settings":        payload.get("risk_settings",        _worker_status.get("risk_settings", {})),
            "message":      payload.get("message", "ok"),
            "last_heartbeat": int(time.time()),
        })
        if payload.get("ladder_top20"):
            _ladder_top20 = payload["ladder_top20"]
            socketio.emit("ladder_update", {"ladder": _ladder_top20})
        # Push live worker status to all browser clients
        socketio.emit("worker_status", _worker_status)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/api/ladder", methods=["GET"])
def get_ladder():
    return jsonify(_ladder_top20), 200


@app.route("/api/worker/status", methods=["GET"])   # legacy path, kept for compatibility
@app.route("/api/engine/status", methods=["GET"])
def worker_status():
    status = dict(_worker_status)
    last = status.get("last_heartbeat")
    if last is None:
        status["running"] = False
        status["state"] = "offline"
        status["stale_seconds"] = None
    else:
        stale = int(time.time()) - int(last)
        status["stale_seconds"] = stale
        # A paused engine refreshes its heartbeat while sleeping, so a truly
        # stale heartbeat means the engine thread is gone — report offline.
        if stale > int(os.environ.get("WORKER_STALE_AFTER_SECONDS", "60")):
            status["running"] = False
            status["state"] = "offline"
            status["message"] = "Engine heartbeat is stale — it may be restarting."
    return jsonify(status), 200


# -----------------------------
# Smart Search + Quotes API
# -----------------------------

SYMBOL_CATALOG = [
    {"symbol": "AAPL",  "name": "Apple Inc."},
    {"symbol": "AMZN",  "name": "Amazon.com, Inc."},
    {"symbol": "GOOG",  "name": "Alphabet Inc. (Google)"},
    {"symbol": "MSFT",  "name": "Microsoft Corporation"},
    {"symbol": "TSLA",  "name": "Tesla, Inc."},
    {"symbol": "NVDA",  "name": "NVIDIA Corporation"},
    {"symbol": "META",  "name": "Meta Platforms, Inc."},
    {"symbol": "NFLX",  "name": "Netflix, Inc."},
    {"symbol": "SPY",   "name": "SPDR S&P 500 ETF Trust"},
    {"symbol": "QQQ",   "name": "Invesco QQQ Trust"},
    {"symbol": "AMD",   "name": "Advanced Micro Devices, Inc."},
    {"symbol": "INTC",  "name": "Intel Corporation"},
    {"symbol": "BABA",  "name": "Alibaba Group Holding"},
    {"symbol": "PYPL",  "name": "PayPal Holdings, Inc."},
    {"symbol": "DIS",   "name": "The Walt Disney Company"},
    {"symbol": "BA",    "name": "Boeing Company"},
    {"symbol": "JPM",   "name": "JPMorgan Chase & Co."},
    {"symbol": "GS",    "name": "Goldman Sachs Group, Inc."},
    {"symbol": "V",     "name": "Visa Inc."},
    {"symbol": "MA",    "name": "Mastercard Incorporated"},
    {"symbol": "XOM",   "name": "Exxon Mobil Corporation"},
    {"symbol": "CVX",   "name": "Chevron Corporation"},
    {"symbol": "COIN",  "name": "Coinbase Global, Inc."},
    {"symbol": "HOOD",  "name": "Robinhood Markets, Inc."},
    {"symbol": "SOFI",  "name": "SoFi Technologies, Inc."},
    {"symbol": "PLTR",  "name": "Palantir Technologies Inc."},
    {"symbol": "RIVN",  "name": "Rivian Automotive, Inc."},
    {"symbol": "LCID",  "name": "Lucid Group, Inc."},
    {"symbol": "RBLX",  "name": "Roblox Corporation"},
    {"symbol": "SNAP",  "name": "Snap Inc."},
    {"symbol": "TWTR",  "name": "Twitter / X Corp"},
    {"symbol": "UBER",  "name": "Uber Technologies, Inc."},
    {"symbol": "LYFT",  "name": "Lyft, Inc."},
    {"symbol": "SHOP",  "name": "Shopify Inc."},
    {"symbol": "SQ",    "name": "Block, Inc. (Square)"},
    {"symbol": "ROKU",  "name": "Roku, Inc."},
    {"symbol": "ZM",    "name": "Zoom Video Communications"},
    {"symbol": "CRWD",  "name": "CrowdStrike Holdings, Inc."},
    {"symbol": "NET",   "name": "Cloudflare, Inc."},
    {"symbol": "SNOW",  "name": "Snowflake Inc."},
    {"symbol": "DDOG",  "name": "Datadog, Inc."},
    {"symbol": "MDB",   "name": "MongoDB, Inc."},
    {"symbol": "ASTS",  "name": "AST SpaceMobile, Inc."},
    {"symbol": "IONQ",  "name": "IonQ, Inc."},
    {"symbol": "QBTS",  "name": "D-Wave Quantum Inc."},
    {"symbol": "SMCI",  "name": "Super Micro Computer, Inc."},
    {"symbol": "ARM",   "name": "Arm Holdings plc"},
    {"symbol": "AVGO",  "name": "Broadcom Inc."},
    {"symbol": "TSM",   "name": "Taiwan Semiconductor Mfg."},
    {"symbol": "IWM",   "name": "iShares Russell 2000 ETF"},
    {"symbol": "VTI",   "name": "Vanguard Total Stock Market ETF"},
    {"symbol": "GLD",   "name": "SPDR Gold Shares ETF"},
    {"symbol": "TLT",   "name": "iShares 20+ Year Treasury Bond ETF"},
]

@app.route("/api/search", methods=["GET"])
def api_search():
    q = (request.args.get("q", "") or "").strip().lower()
    if not q:
        return jsonify([]), 200
    results = [
        item for item in SYMBOL_CATALOG
        if q in item["symbol"].lower() or q in item["name"].lower()
    ]
    return jsonify(results[:15]), 200


def _safe_float(x):
    try:
        return float(x)
    except Exception:
        return None


def _symbol_name(sym: str) -> str:
    return next((i["name"] for i in SYMBOL_CATALOG if i["symbol"] == sym), sym)


def _quote_diag_symbol(sym: str, active_client, feed_order: List[str]) -> Dict[str, Any]:
    """Best-effort diagnostics for a single symbol quote path."""
    diag: Dict[str, Any] = {
        "symbol": sym,
        "name": _symbol_name(sym),
        "attempts": [],
        "result": {
            "price": None,
            "open": None,
            "change": None,
            "change_percent": None,
            "provider": None,
        },
    }

    price = None
    open_px = None

    if active_client:
        for feed in feed_order:
            try:
                try:
                    snap = active_client.get_snapshot(sym, feed=feed)
                except TypeError:
                    snap = active_client.get_snapshot(sym)
                latest = getattr(snap, "latest_trade", None)
                daily = getattr(snap, "daily_bar", None)
                p = _safe_float(getattr(latest, "price", None)) if latest else None
                o = _safe_float(getattr(daily, "o", None)) if daily else None
                diag["attempts"].append({
                    "step": "alpaca_snapshot",
                    "feed": feed,
                    "ok": True,
                    "price": p,
                    "open": o,
                })
                if price is None and p is not None:
                    price = p
                if open_px is None and o is not None:
                    open_px = o
                if price is not None and open_px is not None:
                    break
            except Exception as e:
                diag["attempts"].append({
                    "step": "alpaca_snapshot",
                    "feed": feed,
                    "ok": False,
                    "error": str(e)[:180],
                })

        if price is None:
            for feed in feed_order:
                try:
                    try:
                        t = active_client.get_latest_trade(sym, feed=feed)
                    except TypeError:
                        t = active_client.get_latest_trade(sym)
                    p = _safe_float(getattr(t, "price", None))
                    diag["attempts"].append({
                        "step": "alpaca_latest_trade",
                        "feed": feed,
                        "ok": True,
                        "price": p,
                    })
                    if p is not None:
                        price = p
                        break
                except Exception as e:
                    diag["attempts"].append({
                        "step": "alpaca_latest_trade",
                        "feed": feed,
                        "ok": False,
                        "error": str(e)[:180],
                    })

        if price is None:
            for feed in feed_order:
                try:
                    try:
                        q = active_client.get_latest_quote(sym, feed=feed)
                    except TypeError:
                        q = active_client.get_latest_quote(sym)
                    bid = _safe_float(getattr(q, "bidprice", None))
                    ask = _safe_float(getattr(q, "askprice", None))
                    p = (bid + ask) / 2.0 if (bid and ask) else (ask or bid)
                    diag["attempts"].append({
                        "step": "alpaca_latest_quote",
                        "feed": feed,
                        "ok": True,
                        "bid": bid,
                        "ask": ask,
                        "price": p,
                    })
                    if p is not None:
                        price = p
                        break
                except Exception as e:
                    diag["attempts"].append({
                        "step": "alpaca_latest_quote",
                        "feed": feed,
                        "ok": False,
                        "error": str(e)[:180],
                    })

        if open_px is None:
            for feed in feed_order:
                try:
                    try:
                        bars = active_client.get_bars(sym, "1Day", limit=1, feed=feed)
                    except TypeError:
                        bars = active_client.get_bars(sym, "1Day", limit=1)
                    bar_list = list(bars) if bars else []
                    o = _safe_float(getattr(bar_list[-1], "o", None)) if bar_list else None
                    diag["attempts"].append({
                        "step": "alpaca_daily_bar_open",
                        "feed": feed,
                        "ok": True,
                        "open": o,
                    })
                    if o is not None:
                        open_px = o
                        break
                except Exception as e:
                    diag["attempts"].append({
                        "step": "alpaca_daily_bar_open",
                        "feed": feed,
                        "ok": False,
                        "error": str(e)[:180],
                    })

    if price is None and _alpha:
        try:
            data, _ = _alpha.get_quote_endpoint(sym)
            p = _safe_float(data.get("05. price"))
            ch = _safe_float(data.get("09. change"))
            chp = _safe_float(str(data.get("10. change percent", "")).replace("%", "").strip())
            diag["attempts"].append({
                "step": "alpha_vantage_quote",
                "ok": True,
                "price": p,
                "change": ch,
                "change_percent": chp,
            })
            if p is not None:
                price = p
                if open_px is None and ch is not None:
                    open_px = p - ch
        except Exception as e:
            diag["attempts"].append({
                "step": "alpha_vantage_quote",
                "ok": False,
                "error": str(e)[:180],
            })

    change = change_pct = None
    if price is not None and open_px:
        change = round(price - open_px, 4)
        change_pct = round(change / open_px * 100, 4)

    provider = None
    for step in diag["attempts"]:
        if step.get("ok") and step.get("price") is not None:
            provider = step.get("step")
            break

    diag["result"] = {
        "price": price,
        "open": open_px,
        "change": change,
        "change_percent": change_pct,
        "provider": provider,
    }
    return diag


def _fetch_quotes_uncached(symbols: List[str]) -> Dict[str, Any]:
    """Internal: hits Alpaca then Alpha Vantage without cache."""
    out: Dict[str, Any] = {}
    active_client = _active_alpaca()

    feed_order = [ALPACA_DATA_FEED]
    if ALPACA_DATA_FEED != "iex":
        feed_order.append("iex")

    if active_client:
        for sym in symbols:
            try:
                price = None
                open_px = None

                # 1) Try snapshot first (single call includes trade + daily bar).
                for feed in feed_order:
                    try:
                        snap = active_client.get_snapshot(sym, feed=feed)
                    except TypeError:
                        snap = active_client.get_snapshot(sym)
                    except Exception:
                        continue
                    latest = getattr(snap, "latest_trade", None)
                    daily = getattr(snap, "daily_bar", None)
                    if price is None and latest is not None:
                        price = _safe_float(getattr(latest, "price", None))
                    if open_px is None and daily is not None:
                        open_px = _safe_float(getattr(daily, "o", None))
                    if price is not None and open_px is not None:
                        break

                # 2) Fallback to latest trade if snapshot did not provide price.
                if price is None:
                    for feed in feed_order:
                        try:
                            try:
                                t = active_client.get_latest_trade(sym, feed=feed)
                            except TypeError:
                                t = active_client.get_latest_trade(sym)
                            price = _safe_float(getattr(t, "price", None))
                            if price is not None:
                                break
                        except Exception:
                            continue

                # 3) Fallback to latest quote midpoint.
                if price is None:
                    for feed in feed_order:
                        try:
                            try:
                                q = active_client.get_latest_quote(sym, feed=feed)
                            except TypeError:
                                q = active_client.get_latest_quote(sym)
                            bid = _safe_float(getattr(q, "bidprice", None))
                            ask = _safe_float(getattr(q, "askprice", None))
                            if bid and ask:
                                price = (bid + ask) / 2.0
                                break
                            if ask:
                                price = ask
                                break
                            if bid:
                                price = bid
                                break
                        except Exception:
                            continue

                # 4) If open is missing, fetch latest daily bar.
                if open_px is None:
                    for feed in feed_order:
                        try:
                            try:
                                bars = active_client.get_bars(sym, "1Day", limit=1, feed=feed)
                            except TypeError:
                                bars = active_client.get_bars(sym, "1Day", limit=1)
                            bar_list = list(bars) if bars else []
                            if bar_list:
                                open_px = _safe_float(getattr(bar_list[-1], "o", None))
                                if open_px is not None:
                                    break
                        except Exception:
                            continue

                change = change_pct = None
                if price is not None and open_px:
                    change = round(price - open_px, 4)
                    change_pct = round(change / open_px * 100, 4)
                out[sym] = {
                    "symbol": sym,
                    "name": _symbol_name(sym),
                    "price": price,
                    "change": change,
                    "change_percent": change_pct,
                }
            except Exception:
                pass

    if _alpha:
        for sym in symbols:
            if sym in out and out[sym].get("price") is not None:
                continue
            try:
                data, _ = _alpha.get_quote_endpoint(sym)
                price = _safe_float(data.get("05. price"))
                change = _safe_float(data.get("09. change"))
                change_pct_raw = data.get("10. change percent", "")
                change_pct = _safe_float(str(change_pct_raw).replace("%", "").strip())
                out[sym] = {
                    "symbol": sym,
                    "name": _symbol_name(sym),
                    "price": price,
                    "change": change,
                    "change_percent": change_pct,
                }
            except Exception:
                pass

    for sym in symbols:
        if sym not in out:
            out[sym] = {
                "symbol": sym,
                "name": _symbol_name(sym),
                "price": None, "change": None, "change_percent": None,
            }

    return out


@app.route("/api/quotes", methods=["GET"])
def api_quotes():
    symbols_raw = (request.args.get("symbols", "") or "").strip()
    if not symbols_raw:
        return jsonify({}), 200

    symbols = list(dict.fromkeys(
        s.strip().upper() for s in symbols_raw.split(",") if s.strip()
    ))

    now = time.time()
    out: Dict[str, Any] = {}
    need_fetch: List[str] = []

    with _quote_cache_lock:
        for sym in symbols:
            cached = _quote_cache.get(sym)
            if cached and (now - cached["fetched_at"]) < QUOTE_CACHE_TTL:
                out[sym] = cached["data"]
            else:
                need_fetch.append(sym)

    if need_fetch:
        fresh = _fetch_quotes_uncached(need_fetch)
        with _quote_cache_lock:
            for sym, data in fresh.items():
                _quote_cache[sym] = {"data": data, "fetched_at": time.time()}
                out[sym] = data

    # Attach per-symbol signals from worker if available
    signals = _worker_status.get("signals") or {}
    for sym in symbols:
        if sym in out and sym in signals:
            out[sym]["rsi"]    = signals[sym].get("rsi")
            out[sym]["sma20"]  = signals[sym].get("sma20")
            out[sym]["sma50"]  = signals[sym].get("sma50")
            out[sym]["verdict"] = signals[sym].get("verdict")

    return jsonify(out), 200


@app.route("/api/quotes/diag", methods=["GET"])
def api_quotes_diag():
    """Diagnostic quote probe for support. No secrets included."""
    symbols_raw = (request.args.get("symbols", "") or "").strip()
    if symbols_raw:
        symbols = list(dict.fromkeys(
            s.strip().upper() for s in symbols_raw.split(",") if s.strip()
        ))
    else:
        from_worker = list(_worker_status.get("stocks") or [])
        from_positions = list((_worker_status.get("positions") or {}).keys())
        symbols = list(dict.fromkeys([*(s.upper() for s in from_worker), *(s.upper() for s in from_positions)]))
        symbols = symbols[:10]

    active_client = _active_alpaca()
    feed_order = [ALPACA_DATA_FEED]
    if ALPACA_DATA_FEED != "iex":
        feed_order.append("iex")

    results = []
    for sym in symbols:
        results.append(_quote_diag_symbol(sym, active_client, feed_order))

    return jsonify({
        "timestamp": int(time.time()),
        "effective_mode": _effective_mode(),
        "requested_mode": _requested_mode(),
        "alpaca_client_present": bool(active_client),
        "alpha_vantage_present": bool(_alpha),
        "configured_feed": ALPACA_DATA_FEED,
        "feed_probe_order": feed_order,
        "symbols": symbols,
        "results": results,
        "note": "No secrets are included in this diagnostic payload.",
    }), 200


# -----------------------------------------------
# License (client side — talks to the central license server)
# -----------------------------------------------
@app.route("/api/license/local", methods=["GET"])
def license_local():
    _revalidate_local_license()  # throttled re-check so cancel/refund propagate
    lic = _load_local_license()
    return jsonify({
        "licensed":  _license_is_active(lic),
        "tier":      lic.get("tier"),
        "email":     lic.get("email"),
        "expiresAt": lic.get("expiresAt"),
    }), 200


@app.route("/api/license/activate", methods=["POST"])
def license_activate():
    blocked = _owner_freeze_block("license activation")
    if blocked:
        return blocked
    payload = request.json or {}
    email = _norm_email(payload.get("email") or "")
    if not email:
        return jsonify({"status": "error", "message": "Enter the email address you used at purchase."}), 400
    try:
        r = requests.post(
            f"{LICENSE_SERVER_URL}/api/license/validate",
            json={"email": email, "appId": APP_ID,
                  "licenseKey": (payload.get("licenseKey") or "").strip()},
            timeout=20,
        )
        data = r.json()
    except Exception:
        return jsonify({"status": "error",
                        "message": "Could not reach the license server. Check your internet connection and try again."}), 502

    if data.get("status") == "active":
        _save_local_license(data)
        resp = jsonify({"status": "ok", "licensed": True, "tier": data.get("tier"),
                        "expiresAt": data.get("expiresAt"),
                        "message": "License activated — live trading is unlocked. Restart the app to trade live."})

        # Owner convenience: if activation email is one of the trusted owner
        # emails, bind this browser as a trusted device automatically.
        if email in _trusted_owner_emails():
            device_id = _get_device_id_from_cookie() or _new_device_id()
            _mark_trusted_device(device_id, email)
            session["owner_email"] = email
            resp.set_cookie(
                TRUSTED_DEVICE_COOKIE,
                device_id,
                max_age=60 * 60 * 24 * 400,
                httponly=True,
                samesite="Lax",
                secure=request.is_secure,
            )
        return resp, 200

    return jsonify({"status": "error", "licensed": False,
                    "message": "No active purchase found for that email. "
                               "Use the exact email you entered at checkout, or buy a license below."}), 200


def _local_pricing() -> list:
    """Read the price list shipped with this copy so Buy buttons always
    appear, even when the central store server is asleep (Render free tier
    spins down after inactivity)."""
    try:
        with open(os.path.join(base_dir, "price_map.json")) as f:
            tiers = json.load(f).get(APP_ID, {})
        out = []
        for tier, info in tiers.items():
            if isinstance(info, dict):
                url = info.get("buyUrl", "")
                if url and "REPLACE" not in url:
                    out.append({"tier": tier, "price": info.get("price"),
                                "billingType": info.get("billingType", "one_time"),
                                "plan": info.get("plan") or ("Pro" if str(tier).startswith("pro") else "Trader"),
                                "buyUrl": url})
        return out
    except Exception:
        return []


@app.route("/api/license/pricing-proxy", methods=["GET"])
def license_pricing_proxy():
    # Authoritative prices come from the central store, but it may be asleep
    # (cold start) - fall back to the local list so buttons never vanish.
    try:
        r = requests.get(f"{LICENSE_SERVER_URL}/api/license/pricing",
                         params={"appId": APP_ID}, timeout=8)
        data = r.json()
        if data:
            return jsonify(data), 200
    except Exception:
        pass
    return jsonify(_local_pricing()), 200


# -----------------------------------------------
# Manual Orders (Trade tab Buy/Sell buttons)
# -----------------------------------------------
@app.route("/api/order", methods=["POST"])
def submit_order():
    """Submit a real order through Alpaca. Paper or live follows the current
    license-gated effective mode (same account the AI engine is trading)."""
    blocked = _owner_freeze_block("manual orders")
    if blocked:
        return blocked
    client = _active_alpaca()
    if not client:
        return jsonify({
            "status": "error",
            "message": "Alpaca keys are not configured. Run the Setup Wizard (LAUNCH.bat → option 3) first.",
        }), 503

    payload = request.json or {}
    symbol = str(payload.get("symbol", "")).strip().upper()
    side   = str(payload.get("side", "")).strip().lower()
    otype  = str(payload.get("type", "market")).strip().lower()
    tif    = str(payload.get("tif", "day")).strip().lower()

    try:
        qty = float(payload.get("qty", 0))
    except (TypeError, ValueError):
        qty = 0

    if not symbol or side not in ("buy", "sell") or qty <= 0:
        return jsonify({"status": "error", "message": "Symbol, side (buy/sell) and a positive quantity are required."}), 400
    if otype not in ("market", "limit"):
        return jsonify({"status": "error", "message": "Order type must be 'market' or 'limit'."}), 400

    order_kwargs = {
        "symbol": symbol,
        "qty": qty,
        "side": side,
        "type": otype,
        "time_in_force": tif,
    }
    if otype == "limit":
        try:
            limit_price = float(payload.get("limit_price", 0))
        except (TypeError, ValueError):
            limit_price = 0
        if limit_price <= 0:
            return jsonify({"status": "error", "message": "A positive limit price is required for limit orders."}), 400
        order_kwargs["limit_price"] = limit_price

    is_paper = _effective_mode() != "live"
    try:
        order = client.submit_order(**order_kwargs)
        note = {
            "time": int(time.time()),
            "level": "trade",
            "symbol": symbol,
            "message": f"Manual {side.upper()} {qty:g}x {symbol} ({otype}) submitted — {'PAPER' if is_paper else 'LIVE'} account.",
        }
        _notifications.append(note)
        socketio.emit("notification", note)
        return jsonify({
            "status": "ok",
            "paper": is_paper,
            "order_id": getattr(order, "id", None),
            "order_status": getattr(order, "status", None),
            "message": f"{side.upper()} order for {qty:g}x {symbol} accepted by Alpaca ({'paper' if is_paper else 'LIVE'} account).",
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "paper": is_paper, "message": f"Alpaca rejected the order: {e}"}), 400


# -----------------------------------------------
# AI Trader Toggle
# -----------------------------------------------
@app.route("/api/trader/toggle", methods=["POST"])
def trader_toggle():
    global _ai_trader_enabled
    blocked = _owner_freeze_block("AI trader toggle")
    if blocked:
        return blocked
    payload = request.json or {}
    if "enabled" in payload:
        _ai_trader_enabled = bool(payload["enabled"])
    else:
        _ai_trader_enabled = not _ai_trader_enabled
    # Keep trading settings in sync so the engine picks it up on next poll
    _trading_settings["auto_trade"] = _ai_trader_enabled
    # Persist so the auto-trade state survives restarts
    _save_settings()
    socketio.emit("ai_trader_state", {"ai_trader_enabled": _ai_trader_enabled})
    return jsonify({"ai_trader_enabled": _ai_trader_enabled}), 200


@app.route("/api/trader/status", methods=["GET"])
def trader_toggle_status():
    return jsonify({"ai_trader_enabled": _ai_trader_enabled}), 200


# -----------------------------------------------
# Notifications
# -----------------------------------------------
@app.route("/api/notifications", methods=["GET"])
def get_notifications():
    limit = int(request.args.get("limit", 50))
    return jsonify(_notifications[-limit:]), 200


@app.route("/api/notifications", methods=["POST"])
def add_notification():
    global _notifications
    payload = request.json or {}
    note = {
        "time": int(time.time()),
        "level": payload.get("level", "info"),
        "symbol": payload.get("symbol", ""),
        "message": payload.get("message", ""),
    }
    _notifications.append(note)
    _notifications = _notifications[-200:]
    # Push notification to all browser clients instantly
    socketio.emit("notification", note)
    return jsonify({"status": "ok"}), 200


@app.route("/api/notifications/clear", methods=["POST"])
def clear_notifications():
    blocked = _owner_freeze_block("notification clearing")
    if blocked:
        return blocked
    global _notifications
    _notifications = []
    socketio.emit("notifications_cleared", {})
    return jsonify({"status": "ok"}), 200


# -----------------------------------------------
# Live Trading Settings  (engine polls this)
# -----------------------------------------------
def _settings_response() -> dict:
    """Settings plus the authoritative mode picture. 'trading_mode' is the
    EFFECTIVE mode the engine must use; 'requested_mode' is what the user asked."""
    allowed, reason = _live_allowed()
    resp = dict(_trading_settings)
    resp["requested_mode"]    = _requested_mode()
    resp["trading_mode"]      = _effective_mode()
    resp["live_allowed"]      = allowed
    resp["live_keys_present"] = _live_keys_present()
    resp["licensed"]          = _license_is_active()
    resp["live_block_reason"] = "" if allowed else reason
    resp["market_hours_only"] = bool(_MARKET_HOURS_ONLY)
    # Pro-tier feature gating (Safety Shield is deliberately NOT gated).
    _apply_pro_gating(resp)
    return resp


@app.route("/api/settings/trading", methods=["GET"])
def get_trading_settings():
    return jsonify(_settings_response()), 200


@app.route("/api/settings/trading", methods=["POST"])
def update_trading_settings():
    global _trading_settings, _MARKET_HOURS_ONLY
    blocked = _owner_freeze_block("trading settings update")
    if blocked:
        return blocked
    payload = request.json or {}

    # ── Paper ↔ Live switch — license-gated, fails safe to paper ──────────────
    if "trading_mode" in payload:
        want = str(payload.get("trading_mode", "")).lower()
        if want not in ("paper", "live"):
            return jsonify({"status": "error",
                            "message": "trading_mode must be 'paper' or 'live'."}), 400
        if want == "live":
            ok, reason = _live_allowed()
            if not ok:
                # Refuse to go live; leave the stored mode untouched (paper).
                return jsonify({"status": "error", "message": reason,
                                "trading_mode": _effective_mode(),
                                "requested_mode": _requested_mode(),
                                "licensed": _license_is_active(),
                                "live_keys_present": _live_keys_present()}), 403
        _trading_settings["trading_mode"] = want
        note = {"time": int(time.time()),
                "level": "trade" if want == "live" else "info", "symbol": "",
                "message": ("⚠ LIVE trading enabled — REAL MONEY is now active."
                            if want == "live" else "Switched to PAPER trading (practice money).")}
        _notifications.append(note)
        socketio.emit("notification", note)

    allowed = {
        # Core execution
        "poll_seconds", "trailing_stop_pct", "loss_threshold",
        "max_trades_per_hour", "scan_all_market", "max_positions", "initial_capital",
        # Auto-trade master switch
        "auto_trade",
        # Position sizing / risk controls
        "risk_per_trade_pct", "max_position_pct", "min_positions", "risk_per_trade_usd",
        # Signal quality filters
        "rsi_buy_max", "rsi_sell_min", "sma_spread_min",
        # Forecast-based exit
        "forecast_exit_enabled",
        # Portfolio Safety Shield
        "portfolio_stop_loss", "portfolio_stop_buffer", "shield_enabled",
        # 5hr 59min minimum hold rule
        "min_hold_seconds",
        # Runtime schedule mode (true=market hours only, false=24/7 loop)
        "market_hours_only",
    }
    for k, v in payload.items():
        if k in allowed:
            if k == "market_hours_only":
                _MARKET_HOURS_ONLY = bool(v)
                note = {
                    "time": int(time.time()),
                    "level": "info",
                    "symbol": "",
                    "message": (
                        "Market-hours mode enabled (engine pauses when market is closed)."
                        if _MARKET_HOURS_ONLY else
                        "Off-hours mode enabled (engine continues running after close)."
                    ),
                }
                _notifications.append(note)
                socketio.emit("notification", note)
            else:
                _trading_settings[k] = v
    # Persist to disk so settings survive restarts
    _save_settings()
    # Push updated settings to all browser clients so UI stays in sync
    resp = _settings_response()
    socketio.emit("trading_settings", resp)
    return jsonify(resp), 200


@app.route("/api/keys/live", methods=["POST"])
def save_live_keys():
    """Save the user's LIVE Alpaca keys entered in-app (no Render dashboard trip).
    Verifies them against Alpaca before storing so we never enable live with bad
    keys. An optional Alpha Vantage key can be added/updated at the same time."""
    blocked = _owner_freeze_block("live key updates")
    if blocked:
        return blocked
    payload = request.json or {}
    k = (payload.get("alpaca_live_key") or "").strip()
    s = (payload.get("alpaca_live_secret") or "").strip()
    av = (payload.get("alpha_vantage_key") or "").strip()
    if not k or not s:
        return jsonify({"status": "error",
                        "message": "Enter both your Alpaca LIVE key and secret."}), 400
    # Verify the keys actually work on the live endpoint before saving.
    try:
        acct = REST(k, s, base_url="https://api.alpaca.markets").get_account()
        status = getattr(acct, "status", "")
    except Exception as e:
        return jsonify({"status": "error",
                        "message": f"Alpaca rejected those live keys — double-check them. ({e})"}), 400

    key_store.set_keys(alpaca_key=k, alpaca_secret=s, alpha=(av or None))
    global _alpaca_live
    _alpaca_live = None  # force rebuild with the new keys
    note = {"time": int(time.time()), "level": "info", "symbol": "",
            "message": "Live Alpaca keys saved and verified. You can switch to Live now."}
    _notifications.append(note)
    socketio.emit("notification", note)
    return jsonify({"status": "ok", "account_status": status,
                    "message": "Live keys saved and verified."}), 200


# -----------------------------------------------
# WebSocket events
# -----------------------------------------------
@socketio.on("connect")
def on_connect():
    # Reject the live data stream unless logged in (when a password is set).
    if DASHBOARD_PASSWORD and not session.get("dash_authed"):
        return False
    emit("worker_status", _worker_status)
    emit("ai_trader_state", {"ai_trader_enabled": _ai_trader_enabled})
    emit("notifications_init", {"notifications": _notifications[-50:]})
    emit("trading_settings", _trading_settings)
    emit("ladder_update", {"ladder": _ladder_top20})


# ── Integrated trading engine (replaces separate worker.py process) ─────

def _engine_alert(message: str, level: str = "info", symbol: str = "") -> None:
    """Bridge engine alerts to the browser in-process — no HTTP, no
    DASHBOARD_BASE_URL needed. Mirrors the /api/notifications handler so engine
    buys, sells, shield events and errors appear in the live notifications feed
    (with their colors, browser push and sound)."""
    global _notifications
    note = {
        "time": int(time.time()),
        "level": level,
        "symbol": symbol,
        "message": message,
    }
    _notifications.append(note)
    _notifications = _notifications[-200:]
    try:
        socketio.emit("notification", note)
    except Exception:
        pass


def _internal_heartbeat(eng: TradingEngine, lad: PortfolioLadderScanner) -> None:
    """Update _worker_status and _ladder_top20 in-process (no HTTP round-trip)."""
    global _worker_status, _ladder_top20
    while getattr(eng, "running", True):
        try:
            with eng.lock:
                positions = {
                    sym: {"price": h["price"], "qty": h["qty"]}
                    for sym, h in eng.current_holdings.items()
                }
                signals_snapshot = dict(eng._symbol_signals)
                invested = sum(h["qty"] * h["price"] for h in eng.current_holdings.values())

            top20: list = []
            try:
                top20 = lad.get_ladder()[:20]
            except Exception:
                pass

            _worker_status.update({
                "running":              eng.running,
                "state":                "trading" if eng.running else "offline",
                "mode":                 eng.trading_mode,
                "stocks":               eng.stock_list,
                "profit":               round(eng.profit, 4),
                "positions":            positions,
                "signals":              signals_snapshot,
                "message":              "alive",
                "trade_count":          len(eng.trade_log),
                "capital": {
                    "initial":   round(eng.initial_capital, 2),
                    "available": round(eng._available_capital, 2),
                    "invested":  round(invested, 2),
                    "total":     round(eng._available_capital + invested, 2),
                    "mode":      "pool" if eng.initial_capital > 0 else "fixed_qty",
                },
                "trailing_stop_pct":    round(eng.trailing_stop_pct * 100, 2),
                "loss_threshold":       round(eng.loss_threshold * 100, 2),
                "scan_all_market":      eng.scan_all_market,
                "max_positions":        eng.max_positions,
                "min_positions":        eng.min_positions,
                "trading_mode":         eng.trading_mode,
                "live_trading_enabled": eng.live_enabled,
                "last_heartbeat":       int(time.time()),
            })

            if top20:
                _ladder_top20 = top20
                socketio.emit("ladder_update", {"ladder": _ladder_top20})

            socketio.emit("worker_status", _worker_status)
        except Exception:
            pass
        time.sleep(_HEARTBEAT_SECS)


def _engine_session(session_num: int) -> None:
    """Run one 5h59m trading session then return so the supervisor can restart."""
    global _engine, _ladder

    # License gate: live trading requires an active license. Paper is free.
    # Force a fresh server re-check so a cancelled/refunded license can't start
    # a new live session on stale local data.
    if _requested_mode() == "live":
        _revalidate_local_license(force=True)
    if _requested_mode() == "live" and not _license_is_active():
        os.environ["TRADING_MODE"] = "paper"
        os.environ["LIVE_TRADING_ENABLED"] = "false"
        msg = ("Live trading requires an active license — running in PAPER mode. "
               "Activate in Settings → License.")
        print(f"[LICENSE] {msg}")
        _worker_status["message"] = msg

    stock_list = [
        s.strip().upper()
        for s in os.environ.get("STOCK_LIST", "AAPL,GOOG,TSLA,MSFT,AMZN").split(",")
        if s.strip()
    ]
    mode = os.environ.get("ENGINE_MODE", "AI")

    _engine = TradingEngine(stock_list=stock_list, mode=mode, alert_callback=_engine_alert)
    _worker_status.update({
        "running": True,
        "state": "starting",
        "message": "Engine booted; initializing trading threads...",
        "last_heartbeat": int(time.time()),
    })
    ladder_symbols = list(dict.fromkeys(stock_list + DEFAULT_PORTFOLIO))
    _ladder = PortfolioLadderScanner(symbols=ladder_symbols, engine=_engine)
    integrate_ladder_with_engine(_engine, _ladder)
    _engine.start()
    print(f"[ENGINE] Session #{session_num} started (mode={mode}, stocks={stock_list}).")

    hb_thread = threading.Thread(
        target=_internal_heartbeat, args=(_engine, _ladder),
        daemon=True, name="Heartbeat"
    )
    hb_thread.start()

    ladder_thread = threading.Thread(
        target=_ladder.run_forever,
        kwargs={"interval_seconds": _LADDER_INTERVAL},
        daemon=True, name="LadderScanner"
    )
    ladder_thread.start()

    engine_thread = threading.Thread(
        target=_engine.run_forever,
        daemon=True, name="TradingEngine"
    )
    engine_thread.start()

    start = time.time()
    last_summary = 0.0

    while True:
        now = time.time()

        if not engine_thread.is_alive():
            msg = f"[ENGINE] Engine thread died (session #{session_num}) — restarting."
            print(msg)
            send_crash_notification(msg)
            _engine.start()
            engine_thread = threading.Thread(
                target=_engine.run_forever, daemon=True, name="TradingEngine"
            )
            engine_thread.start()

        if not ladder_thread.is_alive():
            msg = f"[ENGINE] Ladder thread died (session #{session_num}) — restarting."
            print(msg)
            send_crash_notification(msg)
            ladder_thread = threading.Thread(
                target=_ladder.run_forever,
                kwargs={"interval_seconds": _LADDER_INTERVAL},
                daemon=True, name="LadderScanner"
            )
            ladder_thread.start()

        if now - last_summary >= 30:
            last_summary = now
            try:
                summary = _ladder.summary()
                top5 = [e["symbol"] for e in summary.get("top_5", [])]
                if top5:
                    print(f"[ENGINE] Ladder top 5: {' -> '.join(top5)}")
            except Exception:
                pass

        if now - start >= _RUN_SECONDS:
            print(f"[ENGINE] Session #{session_num} complete ({_RUN_SECONDS // 60}min) — recycling.")
            _ladder.stop()
            _engine.stop()
            time.sleep(3)
            return

        time.sleep(2)


_MARKET_HOURS_ONLY = os.environ.get("MARKET_HOURS_ONLY", "true").lower() == "true"


def _now_eastern():
    """Current time in US Eastern, DST-aware. Falls back to UTC-4 if tz data is missing."""
    import datetime
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return datetime.datetime.utcnow() - datetime.timedelta(hours=4)


def _is_market_hours() -> bool:
    """Return True if current time falls within US market hours Mon-Fri 9:25-16:05 ET."""
    now_et = _now_eastern()
    if now_et.weekday() >= 5:
        return False
    open_  = now_et.replace(hour=9,  minute=25, second=0, microsecond=0)
    close_ = now_et.replace(hour=16, minute=5,  second=0, microsecond=0)
    return open_ <= now_et <= close_


def _wait_for_market_open() -> None:
    """Sleep until market hours. Refreshes the heartbeat every 30s so the UI
    shows 'Paused — market closed' instead of going stale/offline."""
    announced = 0.0
    last_equity_check = 0.0
    shield_alerted = False
    shield_alert_ts = 0.0
    while not _is_market_hours():
        now_et = _now_eastern()
        now_ts = time.time()

        # During paused market-hours mode, keep a lightweight portfolio check
        # alive so Safety Shield still monitors account-level drawdowns.
        if now_ts - last_equity_check >= 60:
            last_equity_check = now_ts
            try:
                threshold = float(_trading_settings.get("portfolio_stop_loss", 0) or 0)
                buffer_usd = float(_trading_settings.get("portfolio_stop_buffer", 200) or 0)
                shield_on = bool(_trading_settings.get("shield_enabled", True))
                client = _active_alpaca()
                if shield_on and threshold > 0 and client is not None:
                    acct = client.get_account()
                    equity = float(getattr(acct, "equity", 0) or 0)
                    recovery_target = threshold + buffer_usd
                    if equity > 0 and equity <= threshold:
                        if (not shield_alerted) or (now_ts - shield_alert_ts >= 900):
                            shield_alerted = True
                            shield_alert_ts = now_ts
                            _engine_alert(
                                (
                                    f"Shield watch (market closed): account equity ${equity:,.2f} "
                                    f"is at/below threshold ${threshold:,.2f}."
                                ),
                                level="alert",
                            )
                    elif shield_alerted and equity >= recovery_target:
                        shield_alerted = False
                        _engine_alert(
                            (
                                f"Shield watch reset (market closed): equity recovered to "
                                f"${equity:,.2f} above ${recovery_target:,.2f}."
                            ),
                            level="info",
                        )
            except Exception:
                pass

        msg = (f"Market closed — engine paused until 9:30 ET "
               f"(ET now: {now_et.strftime('%a %H:%M')}).")
        _worker_status.update({
            "running": False,
            "state": "paused",
            "message": msg,
            "last_heartbeat": int(time.time()),
        })
        if time.time() - announced >= 1800:
            announced = time.time()
            print(f"[ENGINE] {msg}")
        socketio.emit("worker_status", _worker_status)
        time.sleep(30)
    print("[ENGINE] Market open — starting trading session.")


def _engine_preflight_error() -> str:
    """Return a user-facing preflight error, or empty string when config is OK."""
    alpha_present = bool(key_store.get_alpha_key())
    if not alpha_present:
        return "Missing ALPHA_VANTAGE_KEY. Open SETUP API KEYS and save it."

    # Preflight the account that the engine will actually use right now.
    if _effective_mode() == "live":
        lk, ls = key_store.get_live_keys()
        live_ok, live_detail = _alpaca_auth_probe(
            lk, ls, "https://api.alpaca.markets"
        )
        if not live_ok:
            if _is_transient_broker_error(live_detail):
                return (
                    "Live Alpaca preflight could not reach broker (temporary network/API issue). "
                    "Engine will auto-retry. "
                    f"Detail: {live_detail}"
                )
            return (
                "Live Alpaca authorization failed. Re-enter ALPACA_LIVE_KEY and "
                f"ALPACA_LIVE_SECRET as a matching LIVE pair. Detail: {live_detail}"
            )
        return ""

    paper_ok, paper_detail = _alpaca_auth_probe(
        ALPACA_KEY, ALPACA_SECRET, "https://paper-api.alpaca.markets"
    )
    if not paper_ok:
        if _is_transient_broker_error(paper_detail):
            return (
                "Paper Alpaca preflight could not reach broker (temporary network/API issue). "
                "Engine will auto-retry. "
                f"Detail: {paper_detail}"
            )
        return (
            "Paper Alpaca authorization failed. Re-enter ALPACA_KEY and "
            f"ALPACA_SECRET as a matching PAPER pair. Detail: {paper_detail}"
        )
    return ""


def _heartbeat_watchdog() -> None:
    """Independent thread: refreshes last_heartbeat every 10 s so the heartbeat
    never goes stale even if the supervisor or session thread crashes.
    This is the ONLY place that guarantees liveness of the status endpoint."""
    global _supervisor_thread
    while True:
        try:
            _worker_status["last_heartbeat"] = int(time.time())
            # If supervisor is not running (or never started), recover it.
            if os.environ.get("DISABLE_ENGINE_AUTOSTART") != "1":
                need_restart = (_supervisor_thread is None) or (not _supervisor_thread.is_alive())
                if need_restart:
                    _worker_status.update({
                        "running": False,
                        "state": "starting",
                        "message": "Engine supervisor recovering...",
                        "last_heartbeat": int(time.time()),
                    })
                    try:
                        socketio.emit("worker_status", _worker_status)
                    except Exception:
                        pass
                    print("[ENGINE] Supervisor was not alive; restarting supervisor thread.")
                    _supervisor_thread = threading.Thread(
                        target=_engine_supervisor, daemon=True, name="EngineSupervisor"
                    )
                    _supervisor_thread.start()
        except Exception:
            pass
        time.sleep(10)


def _engine_supervisor() -> None:
    """Outer loop: starts sessions indefinitely, restarting after each one ends or crashes.
    The entire loop body is wrapped so an unhandled exception can never silently kill
    this thread and leave last_heartbeat stale."""
    session = 0
    last_preflight_msg = ""
    last_preflight_log_ts = 0.0
    while True:
        try:
            try:
                preflight_error = _engine_preflight_error()
            except Exception as pe:
                preflight_error = f"Preflight check raised an unexpected error: {pe}"

            if preflight_error:
                transient = "temporary network/api issue" in preflight_error.lower()
                state = "starting" if transient else "offline"
                _worker_status.update({
                    "running": False,
                    "state": state,
                    "message": preflight_error,
                    "last_heartbeat": int(time.time()),
                })
                try:
                    socketio.emit("worker_status", _worker_status)
                except Exception:
                    pass
                now = time.time()
                if preflight_error != last_preflight_msg or (now - last_preflight_log_ts) >= 300:
                    print(f"[ENGINE] Preflight failed: {preflight_error}")
                    last_preflight_msg = preflight_error
                    last_preflight_log_ts = now
                if not transient:
                    time.sleep(30)
                    continue
                print("[ENGINE] Continuing startup despite transient preflight issue; will retry inside session.")

            if _MARKET_HOURS_ONLY:
                try:
                    _wait_for_market_open()
                except Exception as wme:
                    print(f"[ENGINE] _wait_for_market_open raised: {wme}")
                    time.sleep(30)
                    continue

            session += 1
            print(f"[ENGINE] {'Starting' if session == 1 else 'Restarting'} session #{session} ...")
            try:
                _engine_session(session)
            except SystemExit:
                raise
            except Exception as e:
                msg = f"[ENGINE] Crash in session #{session}: {e}"
                print(msg)
                _worker_status.update({
                    "running": False,
                    "state": "offline",
                    "message": f"Engine failed to start: {e}",
                    "last_heartbeat": int(time.time()),
                })
                try:
                    socketio.emit("worker_status", _worker_status)
                except Exception:
                    pass
                try:
                    send_crash_notification(msg)
                except Exception:
                    pass
            print(f"[ENGINE] Session #{session} ended. Next session in 5s ...")
            time.sleep(5)

        except SystemExit:
            raise
        except Exception as supervisor_err:
            # Last-resort catch: log the unexpected error, refresh heartbeat,
            # and continue looping so the supervisor thread NEVER dies.
            print(f"[ENGINE] Unexpected supervisor error (will retry in 15s): {supervisor_err}")
            _worker_status.update({
                "running": False,
                "state": "offline",
                "message": f"Supervisor recovered from unexpected error: {supervisor_err}",
                "last_heartbeat": int(time.time()),
            })
            try:
                socketio.emit("worker_status", _worker_status)
            except Exception:
                pass
            time.sleep(15)


# Engine always starts inside the dashboard process.
# The separate worker service has been removed to reduce Render costs.
# Set DISABLE_ENGINE_AUTOSTART=1 to import this module without launching the
# engine (used by tests / tooling). Production leaves it unset.
# Re-activate the license from the environment before the engine starts, so a
# wiped license.json is restored automatically and live trading resumes without
# any manual re-entry after an update/restart/crash.
_recover_license_on_boot()

if DASHBOARD_PASSWORD:
    print("[DASHBOARD] Password gate ENABLED — dashboard requires login.")
else:
    print("[DASHBOARD] WARNING: DASHBOARD_PASSWORD is not set — the dashboard and "
          "its control endpoints are OPEN to anyone with the URL. Set DASHBOARD_PASSWORD "
          "in your Render env vars to lock it down.")

if os.environ.get("DISABLE_ENGINE_AUTOSTART") != "1":
    # Independent watchdog: keeps last_heartbeat fresh even if supervisor crashes.
    _watchdog_thread = threading.Thread(
        target=_heartbeat_watchdog, daemon=True, name="HeartbeatWatchdog"
    )
    _watchdog_thread.start()
    _supervisor_thread = threading.Thread(
        target=_engine_supervisor, daemon=True, name="EngineSupervisor"
    )
    _supervisor_thread.start()
    print("[DASHBOARD] Trading engine supervisor started.")
else:
    print("[DASHBOARD] Engine autostart disabled (DISABLE_ENGINE_AUTOSTART=1).")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)

# Built by Troy Walker of T-Dub's Apps — 2026-04-22
