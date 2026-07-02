# CRITICAL: gevent monkey patch MUST be first -- before ANY other imports.
# This patches Python's standard library to work with gevent's async model.
# Required for Socket.IO WebSocket support on Render/gunicorn with gevent worker.
from gevent import monkey
monkey.patch_all()

import json
import os
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

from flask import Flask, render_template, request, jsonify
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

# Settings are persisted here so they survive restarts
SETTINGS_FILE = os.path.join(base_dir, "trading_settings.json")

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
LICENSE_FILE = os.path.join(base_dir, "license.json")

# -- Distribution URLs (used by the shareable Render landing page /get) --------
# The public repo IS the installation package. The GitHub archive link always
# serves the latest build, so buyers always download an up-to-date copy.
GITHUB_REPO_URL   = os.environ.get("GITHUB_REPO_URL", "https://github.com/T-Dubs-Apps/Alien-AI-Trader")
DOWNLOAD_ZIP_URL  = os.environ.get("DOWNLOAD_ZIP_URL", GITHUB_REPO_URL + "/archive/refs/heads/main.zip")
# One-click "Deploy to Render" — Render reads render.yaml from the repo and
# stands up the buyer's OWN private cloud instance (their keys, their trades).
RENDER_DEPLOY_URL = os.environ.get("RENDER_DEPLOY_URL", "https://render.com/deploy?repo=" + GITHUB_REPO_URL)

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
    email = lic.get("email")
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
ALPACA_KEY = os.environ.get("ALPACA_KEY")
ALPACA_SECRET = os.environ.get("ALPACA_SECRET")
ALPACA_BASE_URL = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY")
# Separate LIVE credentials so the licensed Paper↔Live toggle can switch accounts
# without the buyer ever regenerating keys. Paper keys above stay paper; these
# stay live. Absent live keys = live simply cannot be enabled (fail safe).
ALPACA_LIVE_KEY    = os.environ.get("ALPACA_LIVE_KEY")
ALPACA_LIVE_SECRET = os.environ.get("ALPACA_LIVE_SECRET")

_alpaca = None        # paper client (always paper endpoint)
_alpaca_live = None   # live client, built lazily only when live is used
_alpha = None

if ALPACA_KEY and ALPACA_SECRET:
    _alpaca = REST(ALPACA_KEY, ALPACA_SECRET, base_url="https://paper-api.alpaca.markets")

if ALPHA_VANTAGE_KEY:
    _alpha = TimeSeries(key=ALPHA_VANTAGE_KEY, output_format="json")


def _live_keys_present() -> bool:
    return bool(ALPACA_LIVE_KEY and ALPACA_LIVE_SECRET)


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
        _alpaca_live = REST(ALPACA_LIVE_KEY, ALPACA_LIVE_SECRET,
                            base_url="https://api.alpaca.markets")
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


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


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
— Troy Walker · T-Dub's Apps</p>
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

  <footer>&#128123; Alien AI Trader &middot; Built by Troy Walker &middot; T-Dub's Apps &middot; 2026<br>
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


def _fetch_quotes_uncached(symbols: List[str]) -> Dict[str, Any]:
    """Internal: hits Alpaca then Alpha Vantage without cache."""
    out: Dict[str, Any] = {}

    if _alpaca:
        for sym in symbols:
            try:
                # Snapshot gives the latest trade AND today's daily bar in one call,
                # so we can show the day's move (▲/▼ vs open) — not just the price.
                snap = _alpaca.get_snapshot(sym)
                latest = getattr(snap, "latest_trade", None)
                price = _safe_float(getattr(latest, "price", None)) if latest else None
                daily = getattr(snap, "daily_bar", None)
                open_px = _safe_float(getattr(daily, "o", None)) if daily else None
                change = change_pct = None
                if price is not None and open_px:
                    change = round(price - open_px, 4)
                    change_pct = round(change / open_px * 100, 4)
                out[sym] = {
                    "symbol": sym,
                    "name": next((i["name"] for i in SYMBOL_CATALOG if i["symbol"] == sym), sym),
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
                    "name": next((i["name"] for i in SYMBOL_CATALOG if i["symbol"] == sym), sym),
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
                "name": next((i["name"] for i in SYMBOL_CATALOG if i["symbol"] == sym), sym),
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
    payload = request.json or {}
    email = (payload.get("email") or "").strip()
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
        return jsonify({"status": "ok", "licensed": True, "tier": data.get("tier"),
                        "expiresAt": data.get("expiresAt"),
                        "message": "License activated — live trading is unlocked. Restart the app to trade live."}), 200

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
    # Pro-tier feature gating (Safety Shield is deliberately NOT gated).
    _apply_pro_gating(resp)
    return resp


@app.route("/api/settings/trading", methods=["GET"])
def get_trading_settings():
    return jsonify(_settings_response()), 200


@app.route("/api/settings/trading", methods=["POST"])
def update_trading_settings():
    global _trading_settings
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
                                "requested_mode": _requested_mode()}), 403
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
    }
    for k, v in payload.items():
        if k in allowed:
            _trading_settings[k] = v
    # Persist to disk so settings survive restarts
    _save_settings()
    # Push updated settings to all browser clients so UI stays in sync
    resp = _settings_response()
    socketio.emit("trading_settings", resp)
    return jsonify(resp), 200


# -----------------------------------------------
# WebSocket events
# -----------------------------------------------
@socketio.on("connect")
def on_connect():
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
    if os.environ.get("TRADING_MODE", "paper").strip().lower() == "live":
        _revalidate_local_license(force=True)
    if os.environ.get("TRADING_MODE", "paper").strip().lower() == "live" and not _license_is_active():
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
    while not _is_market_hours():
        now_et = _now_eastern()
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


def _engine_supervisor() -> None:
    """Outer loop: starts sessions indefinitely, restarting after each one ends or crashes."""
    session = 0
    while True:
        if _MARKET_HOURS_ONLY:
            _wait_for_market_open()
        session += 1
        print(f"[ENGINE] {'Starting' if session == 1 else 'Restarting'} session #{session} ...")
        try:
            _engine_session(session)
        except SystemExit:
            raise
        except Exception as e:
            msg = f"[ENGINE] Crash in session #{session}: {e}"
            print(msg)
            try:
                send_crash_notification(msg)
            except Exception:
                pass
        print(f"[ENGINE] Session #{session} ended. Next session in 5s ...")
        time.sleep(5)


# Engine always starts inside the dashboard process.
# The separate worker service has been removed to reduce Render costs.
# Set DISABLE_ENGINE_AUTOSTART=1 to import this module without launching the
# engine (used by tests / tooling). Production leaves it unset.
if os.environ.get("DISABLE_ENGINE_AUTOSTART") != "1":
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
