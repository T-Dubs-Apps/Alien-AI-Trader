import os
import time
from threading import Lock
from typing import Dict, Any, List

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from license_api import register_license_routes

# Market data providers (quotes + basic lookup)
from alpaca_trade_api.rest import REST
from alpha_vantage.timeseries import TimeSeries

# SMART PATHING: This finds 'templates' relative to where this script is sitting
base_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(base_dir, "templates")

app = Flask(__name__, template_folder=template_dir)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET", os.urandom(24).hex())

# CORS
allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*")
origins = [o.strip() for o in allowed_origins.split(",")] if allowed_origins else ["*"]
CORS(app, resources={r"/api/*": {"origins": origins}})

# WebSocket via SocketIO (async_mode=threading for Render/gunicorn compatibility)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading", logger=False, engineio_logger=False)

# License routes
register_license_routes(app)

# In-memory warehouse for ticker/market data sent to the dashboard
market_data = []

# In-memory worker status (the worker will POST heartbeat updates here)
_worker_status: Dict[str, Any] = {
    "running": False,
    "mode": os.environ.get("TRADING_MODE", "paper"),
    "stocks": [s.strip().upper() for s in os.environ.get("STOCK_LIST", "AAPL,GOOG,TSLA,MSFT,AMZN").split(",") if s.strip()],
    "last_heartbeat": None,
    "message": "Worker has not checked in yet."
}

# In-memory AI trader toggle (can be overridden by worker via heartbeat)
_ai_trader_enabled = True

# Live trading settings — the engine polls this endpoint every cycle
_trading_settings: dict = {
    # ── Core scan / execution settings ──────────────────────────────────────
    "poll_seconds":        int(os.environ.get("POLL_SECONDS",        "15")),
    "trailing_stop_pct":   float(os.environ.get("TRAILING_STOP_PCT", "3.0")),
    "loss_threshold":      float(os.environ.get("LOSS_THRESHOLD",    "5.0")),
    "max_trades_per_hour": int(os.environ.get("MAX_TRADES_PER_HOUR", "30")),
    "scan_all_market":     os.environ.get("SCAN_ALL_MARKET", "false").lower() == "true",
    "max_positions":       int(os.environ.get("MAX_POSITIONS",       "5")),
    "initial_capital":     float(os.environ.get("INITIAL_CAPITAL",   "0")),
    # ── Position sizing / risk controls ─────────────────────────────────────
    # These scale automatically to whatever INITIAL_CAPITAL the user sets.
    # A user with $100 gets small trades; a user with $50,000 gets larger ones.
    # All values are adjustable live from the dashboard without restarting.
    "risk_per_trade_pct":  float(os.environ.get("RISK_PER_TRADE_PCT",  "2.0")),   # % of capital per trade
    "max_position_pct":    float(os.environ.get("MAX_POSITION_PCT",    "20.0")),  # % max in one stock
    "min_positions":       int(os.environ.get("MIN_POSITIONS",         "5")),     # min spread across N stocks
    "risk_per_trade_usd":  float(os.environ.get("RISK_PER_TRADE_USD",  "0")),     # hard $ cap (0=off)
    # ── Signal quality filters ───────────────────────────────────────────────
    "rsi_buy_max":         float(os.environ.get("RSI_BUY_MAX",    "50.0")),  # RSI must be below this to BUY
    "rsi_sell_min":        float(os.environ.get("RSI_SELL_MIN",   "70.0")),  # RSI must be above this to SELL
    "sma_spread_min":      float(os.environ.get("SMA_SPREAD_MIN", "0.1")),   # min SMA20/50 spread % for signal
}

# In-memory notifications log
_notifications: List[Dict[str, Any]] = []

# ---- Providers (server-side only) ----
# These are safe because values come from Render env vars; never sent to browser.
ALPACA_KEY = os.environ.get("ALPACA_KEY")
ALPACA_SECRET = os.environ.get("ALPACA_SECRET")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY")

_alpaca = None
_alpha = None

if ALPACA_KEY and ALPACA_SECRET:
    _alpaca = REST(ALPACA_KEY, ALPACA_SECRET, base_url="https://paper-api.alpaca.markets")

if ALPHA_VANTAGE_KEY:
    _alpha = TimeSeries(key=ALPHA_VANTAGE_KEY, output_format="json")

# ---- Quote cache (prevents hammering APIs) ----
_quote_cache: Dict[str, Dict[str, Any]] = {}   # sym -> {data, fetched_at}
_quote_cache_lock = Lock()
QUOTE_CACHE_TTL = int(os.environ.get("QUOTE_CACHE_TTL", "8"))  # seconds


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


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


# --- Worker integration (Render Background Worker should call this) ---

@app.route("/api/worker/heartbeat", methods=["POST"])
def worker_heartbeat():
    global _worker_status
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
            # New: live/paper mode status and risk settings snapshot from engine
            "trading_mode":         payload.get("trading_mode",         _worker_status.get("trading_mode")),
            "live_trading_enabled": payload.get("live_trading_enabled", _worker_status.get("live_trading_enabled", False)),
            "risk_settings":        payload.get("risk_settings",        _worker_status.get("risk_settings", {})),
            "message":      payload.get("message", "ok"),
            "last_heartbeat": int(time.time()),
        })
        # Push live worker status to all browser clients
        socketio.emit("worker_status", _worker_status)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/api/worker/status", methods=["GET"])
def worker_status():
    status = dict(_worker_status)
    last = status.get("last_heartbeat")
    if last is None:
        status["running"] = False
        status["stale_seconds"] = None
    else:
        stale = int(time.time()) - int(last)
        status["stale_seconds"] = stale
        if stale > int(os.environ.get("WORKER_STALE_AFTER_SECONDS", "60")):
            status["running"] = False
            status["message"] = "Worker heartbeat is stale."
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
        # Position sizing / risk controls
        "risk_per_trade_pct", "max_position_pct", "min_positions", "risk_per_trade_usd",
        # Signal quality filters
        "rsi_buy_max", "rsi_sell_min", "sma_spread_min",
    }
    for k, v in payload.items():
        if k in allowed:
            _trading_settings[k] = v
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)

# Built by Troy Walker of T-Dub's Apps — 2026-04-22

