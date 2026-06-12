# CRITICAL: gevent monkey patch MUST be first -- before ANY other imports.
# This patches Python's standard library to work with gevent's async model.
# Required for Socket.IO WebSocket support on Render/gunicorn with gevent worker.
from gevent import monkey
monkey.patch_all()

import json
import os
import threading
import time
import requests
from threading import Lock
from typing import Dict, Any, List

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
        return lic.get("status") == "active" and int(lic.get("expiresAt", 0)) > int(time.time() * 1000)
    except Exception:
        return False

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

_alpaca = None
_alpha = None

if ALPACA_KEY and ALPACA_SECRET:
    _alpaca = REST(ALPACA_KEY, ALPACA_SECRET, base_url=ALPACA_BASE_URL)

if ALPHA_VANTAGE_KEY:
    _alpha = TimeSeries(key=ALPHA_VANTAGE_KEY, output_format="json")

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
                t = _alpaca.get_latest_trade(sym)
                price = _safe_float(getattr(t, "price", None))
                out[sym] = {
                    "symbol": sym,
                    "name": next((i["name"] for i in SYMBOL_CATALOG if i["symbol"] == sym), sym),
                    "price": price,
                    "change": None,
                    "change_percent": None,
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


@app.route("/api/license/pricing-proxy", methods=["GET"])
def license_pricing_proxy():
    try:
        r = requests.get(f"{LICENSE_SERVER_URL}/api/license/pricing",
                         params={"appId": APP_ID}, timeout=15)
        return jsonify(r.json()), 200
    except Exception:
        return jsonify([]), 200


# -----------------------------------------------
# Manual Orders (Trade tab Buy/Sell buttons)
# -----------------------------------------------
@app.route("/api/order", methods=["POST"])
def submit_order():
    """Submit a real order through Alpaca. Paper or live depends on ALPACA_BASE_URL."""
    if not _alpaca:
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

    is_paper = "paper" in ALPACA_BASE_URL.lower()
    try:
        order = _alpaca.submit_order(**order_kwargs)
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
@app.route("/api/settings/trading", methods=["GET"])
def get_trading_settings():
    return jsonify(_trading_settings), 200


@app.route("/api/settings/trading", methods=["POST"])
def update_trading_settings():
    global _trading_settings
    payload = request.json or {}
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
    socketio.emit("trading_settings", _trading_settings)
    return jsonify(_trading_settings), 200


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

    _engine = TradingEngine(stock_list=stock_list, mode=mode)
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
_supervisor_thread = threading.Thread(
    target=_engine_supervisor, daemon=True, name="EngineSupervisor"
)
_supervisor_thread.start()
print("[DASHBOARD] Trading engine supervisor started.")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)

# Built by Troy Walker of T-Dub's Apps — 2026-04-22
