from news_sentiment import get_symbol_sentiment
from ai_model import ai_predict_signal
from dynamic_position import calc_volatility, adjust_risk_for_streak, adjust_risk_for_volatility
try:
    from forecasting import get_forecast as _get_forecast
    def get_forecast(closes, periods_ahead=5):
        return _get_forecast(closes, periods_ahead)
except Exception:
    def get_forecast(closes, periods_ahead=5):
        return {"score": 0.0, "forecast_direction": "neutral", "forecast_phase": "unknown", "predicted_price": None, "confidence": 0.0, "slope_pct_per_bar": 0.0}
import os
import time
import threading
import statistics
import requests
import key_store
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
from alpaca_trade_api.rest import REST, TimeFrame
from alpha_vantage.timeseries import TimeSeries
from pushbullet import Pushbullet

try:
    from twilio.rest import Client as TwilioClient
except Exception:
    TwilioClient = None


class TradingEngine:
    @staticmethod
    def _clean_env(name: str, default: str = "") -> str:
        """Normalize env values, stripping accidental wrapper quotes."""
        raw = os.environ.get(name)
        if raw is None:
            return default
        s = str(raw).strip()
        if len(s) >= 2 and s[0] in ("'", '"') and s[-1] == s[0]:
            s = s[1:-1].strip()
        return s

    def _calc_macd(self, closes: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
        if len(closes) < slow + signal:
            return None, None
        exp1 = closes.ewm(span=fast, adjust=False).mean()
        exp2 = closes.ewm(span=slow, adjust=False).mean()
        macd_line = exp1 - exp2
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        return float(macd_line.iloc[-1]), float(signal_line.iloc[-1])

    def _calc_bollinger(self, closes: pd.Series, period: int = 20, num_std: float = 2.0):
        if len(closes) < period:
            return None, None, None
        sma = closes.rolling(window=period).mean().iloc[-1]
        std = closes.rolling(window=period).std().iloc[-1]
        upper = sma + num_std * std
        lower = sma - num_std * std
        return float(upper), float(sma), float(lower)

    def _calc_vwap(self, df: pd.DataFrame):
        # VWAP = sum(price * volume) / sum(volume)
        if df is None or df.empty or 'c' not in df or 'v' not in df:
            return None
        pv = (df['c'].astype(float) * df['v'].astype(float)).sum()
        v = df['v'].astype(float).sum()
        if v == 0:
            return None
        return float(pv / v)

    """
    TradingEngine — upgraded for concurrent scanning, RSI + SMA crossover signals,
    ROI tracking, price caching, and faster real-time heartbeats.

    - Secrets are read from environment variables (Render env vars).
    - Live trading requires explicit enablement (TRADING_MODE=live AND LIVE_TRADING_ENABLED=true).
    - Heartbeats are posted to your dashboard web service with per-symbol signal data.
    """

    def __init__(self, stock_list: List[str], mode: str = "AI", alert_callback=None, activity_callback=None):
        self.stock_list = [s.strip().upper() for s in stock_list if s and s.strip()]
        self.mode = mode
        self.alert_callback = alert_callback
        self.activity_callback = activity_callback

        self.running = False
        self.lock = threading.Lock()
        # Serializes order placement so concurrent scan threads cannot overspend
        # capital or exceed max_positions during the same cycle.
        self._buy_lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._afterhours_started = False

        self.current_holdings: Dict[str, Dict[str, Any]] = {}
        self.trade_log: List[Dict[str, Any]] = []
        self.profit = 0.0
        self._reconciled = False   # seed holdings from Alpaca once per session

        # ROI tracking (inspired by growth_forecaster pattern)
        self._session_start_equity: Optional[float] = None
        self._symbol_signals: Dict[str, Dict[str, Any]] = {}   # per-symbol last signal data

        # ── Auto-trade master switch (live-toggled from dashboard UI) ──────────
        # When False the engine scans and signals but never places orders.
        # Flipping the toggle in the UI updates /api/settings/trading which the
        # engine picks up on the next _poll_live_settings() call.
        self.auto_trade = True   # default ON; dashboard can override

        # ── Risk controls (live-updateable from dashboard UI) ──
        self.loss_threshold    = float(os.environ.get("LOSS_THRESHOLD",    "0.05"))  # 5% absolute floor
        self.trailing_stop_pct = float(os.environ.get("TRAILING_STOP_PCT", "0.03"))  # 3% drop from peak

        # Forecast-based early exit: sell before trailing stop fires when climb peaks
        self.forecast_exit_enabled = os.environ.get("FORECAST_EXIT_ENABLED", "true").lower() == "true"

        # Scan interval (live-configurable from UI)
        self.poll_seconds = int(os.environ.get("POLL_SECONDS", "15"))

        # Max parallel workers
        self.max_workers = int(os.environ.get("SCAN_WORKERS", "8"))

        # ── Capital pool (compound reinvestment mode) ──
        # INITIAL_CAPITAL=0 (default) → AUTO: size every trade to the broker
        #   account's REAL balance, detected once per session (see
        #   _autodetect_capital). This is what makes buy/sell amounts scale to
        #   however much money the user actually funded.
        # INITIAL_CAPITAL=100 (or any >0) → MANUAL override: pin the pool to that
        #   dollar amount (useful for sandboxing a small slice of a big account).
        self.initial_capital    = float(os.environ.get("INITIAL_CAPITAL", "0"))
        self._available_capital = self.initial_capital
        # True until the user pins an explicit INITIAL_CAPITAL; controls whether
        # we auto-size to the live account balance each session.
        self._capital_is_auto   = self.initial_capital <= 0

        # Max simultaneous open positions
        self.max_positions = int(os.environ.get("MAX_POSITIONS", "5"))

        # Hard exposure guardrails (invariants): these are non-negotiable limits
        # that prevent catastrophic over-allocation during fast market moves.
        self.max_gross_exposure_pct = float(os.environ.get("MAX_GROSS_EXPOSURE_PCT", "85.0"))
        self.min_cash_reserve_pct = float(os.environ.get("MIN_CASH_RESERVE_PCT", "10.0"))

        # Forecast policy: mandatory only when a trade is high-risk to execute
        # without forward confirmation (capital-intensive, volatile, illiquid).
        self.forecast_required_capital_pct = float(os.environ.get("FORECAST_REQUIRED_CAPITAL_PCT", "12.0"))
        self.forecast_required_volatility = float(os.environ.get("FORECAST_REQUIRED_VOLATILITY", "0.03"))
        self.forecast_required_min_volume = float(os.environ.get("FORECAST_REQUIRED_MIN_VOLUME", "1000000"))

        # ── Position sizing / risk-per-trade controls ──────────────────────────
        #
        # RISK_PER_TRADE_PCT  — what % of total capital to risk on a single trade.
        #   Default: 2.0  →  $100 capital = max $2.00 risked per position.
        #   This is the PRIMARY knob. Lower = more conservative, more positions.
        #
        # MAX_POSITION_PCT    — hard ceiling: no single position > X% of capital.
        #   Default: 20.0  →  $100 capital = max $20 in any one stock.
        #   Prevents the engine from putting too much in one winner.
        #
        # MIN_POSITIONS       — minimum number of positions to spread capital across.
        #   Default: 5   →  $100 split into at least 5 trades (~$20 each max).
        #   Works together with max_positions to enforce diversification.
        #
        # RISK_PER_TRADE_USD  — optional hard dollar cap per trade (0 = disabled).
        #   Example: RISK_PER_TRADE_USD=10 caps every trade at $10 regardless of %.
        #   Useful during testing when you want absolute dollar control.
        #
        self.risk_per_trade_pct  = float(os.environ.get("RISK_PER_TRADE_PCT",  "2.0"))   # % of capital
        self.max_position_pct    = float(os.environ.get("MAX_POSITION_PCT",    "20.0"))  # % of capital
        self.min_positions       = int(os.environ.get("MIN_POSITIONS",         "5"))
        self.risk_per_trade_usd  = float(os.environ.get("RISK_PER_TRADE_USD",  "0"))     # 0 = disabled

        # ── Signal strength filter ──────────────────────────────────────────────
        # Require RSI to be genuinely oversold (not just "not overbought") before buying.
        # Default: RSI must be BELOW 50 to enter — catching dips, not chasing tops.
        # Raise this value (e.g. 60) for more trades; lower (e.g. 40) for fewer, higher-quality entries.
        self.rsi_buy_max    = float(os.environ.get("RSI_BUY_MAX",    "50.0"))  # RSI ceiling to BUY
        self.rsi_sell_min   = float(os.environ.get("RSI_SELL_MIN",   "70.0"))  # RSI floor to SELL
        # Minimum SMA20/SMA50 spread % before a golden cross is "real enough"
        self.sma_spread_min = float(os.environ.get("SMA_SPREAD_MIN", "0.1"))   # 0.1% spread required

        # Optional momentum-chase mode for explosive movers that would fail the
        # dip-buy filter stack (e.g., large same-day breakouts).
        self.rocket_breakout_enabled = os.environ.get("ROCKET_BREAKOUT_ENABLED", "true").lower() == "true"
        self.rocket_breakout_min_day_change_pct = float(os.environ.get("ROCKET_BREAKOUT_MIN_DAY_CHANGE_PCT", "12.0"))
        self.rocket_breakout_volume_mult = float(os.environ.get("ROCKET_BREAKOUT_VOLUME_MULT", "1.5"))
        self.rocket_breakout_min_avg_volume = float(os.environ.get("ROCKET_BREAKOUT_MIN_AVG_VOLUME", "150000"))
        self.rocket_breakout_max_above_sma20_pct = float(os.environ.get("ROCKET_BREAKOUT_MAX_ABOVE_SMA20_PCT", "35.0"))
        self.rocket_breakout_lookback_bars = int(os.environ.get("ROCKET_BREAKOUT_LOOKBACK_BARS", "20"))

        # ── Full-market scan ──
        self.scan_all_market         = os.environ.get("SCAN_ALL_MARKET", "false").lower() == "true"
        self._market_scan_candidates = int(os.environ.get("MARKET_SCAN_CANDIDATES", "30"))

        # Trailing-stop high-water marks: {symbol: highest_price_since_buy}
        self._peak_prices: Dict[str, float] = {}

        # ── Trading mode & Alpaca credentials ─────────────────────────────────
        # The engine holds BOTH key pairs so the dashboard's licensed Paper↔Live
        # toggle can switch accounts instantly — the buyer never returns to Alpaca.
        #   paper keys → ALPACA_KEY / ALPACA_SECRET
        #   live  keys → ALPACA_LIVE_KEY / ALPACA_LIVE_SECRET
        # Live is ONLY ever activated by the dashboard after it confirms a valid
        # signed license (see dashboard _live_allowed()). The engine trusts the
        # effective mode it is handed on /api/settings/trading and always fails
        # SAFE to paper when live keys are absent.
        self._paper_key    = self._clean_env("ALPACA_KEY", "")
        self._paper_secret = self._clean_env("ALPACA_SECRET", "")
        self._live_key     = self._clean_env("ALPACA_LIVE_KEY", "")
        self._live_secret  = self._clean_env("ALPACA_LIVE_SECRET", "")
        alpha_vantage_key  = key_store.get_alpha_key()
        pushbullet_token   = (
            self._clean_env("PUSHBULLET_TOKEN", "")
            or self._clean_env("PUSHBULLET_API_KEY", "")
        )

        if not self._paper_key or not self._paper_secret:
            raise RuntimeError("Missing ALPACA_KEY / ALPACA_SECRET env vars.")
        if not alpha_vantage_key:
            raise RuntimeError("Missing ALPHA_VANTAGE_KEY env var.")

        # Always boot in PAPER. Honor an explicit live boot only when live keys
        # actually exist (no send_alert here — pushbullet/pushover aren't set up yet).
        self.live_enabled = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() == "true"
        self.trading_mode = "paper"
        self.api = self._make_alpaca("paper")
        if os.environ.get("TRADING_MODE", "paper").lower() == "live" and key_store.has_live_keys():
            self.api = self._make_alpaca("live")
            self.trading_mode = "live"

        # Market data feed: default to IEX (widely available) so live mode keeps
        # receiving quotes/bars even when SIP entitlement is absent.
        feed = str(os.environ.get("ALPACA_DATA_FEED", "iex") or "iex").strip().lower()
        self.alpaca_data_feed = feed if feed in ("iex", "sip") else "iex"

        self.ts = TimeSeries(key=alpha_vantage_key, output_format="json")

        self.pb = Pushbullet(pushbullet_token) if pushbullet_token else None
        self._pb_disabled_reason = ""

        # ── Pushover (DND-breaking mobile alerts) ──
        self.pushover_token = os.environ.get("PUSHOVER_TOKEN", "")
        self.pushover_user  = os.environ.get("PUSHOVER_USER",  "")

        # ── Twilio voice call (crash emergency) ──
        twilio_sid    = os.environ.get("TWILIO_ACCOUNT_SID", "")
        twilio_token  = os.environ.get("TWILIO_AUTH_TOKEN",  "")
        self.twilio_from   = os.environ.get("TWILIO_FROM_NUMBER", "")
        self.twilio_to     = os.environ.get("TWILIO_TO_NUMBER",   "")  # your cell number
        self.twilio_client = TwilioClient(twilio_sid, twilio_token) if (TwilioClient and twilio_sid and twilio_token) else None

        # ── After-hours portfolio protection ──
        # Monitors holdings 24/7; places GTC stop orders when market is closed.
        self.afterhours_drop_pct  = float(os.environ.get("AFTERHOURS_DROP_PCT",  "3.0")) / 100.0
        self.rocket_alert_pct     = float(os.environ.get("ROCKET_ALERT_PCT",     "5.0")) / 100.0
        self._ah_stops_placed: set = set()   # symbols with a protective stop already queued
        self._ah_last_prices: Dict[str, float] = {}

        # ── Capital ratchet (high-water mark — the ladder never comes down) ──
        self._capital_hwm = self.initial_capital   # highest total portfolio value ever seen

        # Dashboard heartbeat + live-settings poll.
        # Accept either DASHBOARD_BASE_URL or DASHBOARD_URL; otherwise fall back to
        # the local loopback. The engine runs IN-PROCESS with the dashboard, so
        # 127.0.0.1:$PORT always reaches it — this guarantees the Paper↔Live toggle
        # (and all live settings) work with no extra env var to configure.
        self.dashboard_base_url = (
            os.environ.get("DASHBOARD_BASE_URL") or
            os.environ.get("DASHBOARD_URL") or
            f"http://127.0.0.1:{os.environ.get('PORT', '5000')}"
        ).rstrip("/")
        self.heartbeat_path = os.environ.get("HEARTBEAT_PATH", "/api/worker/heartbeat")
        self.heartbeat_every = int(os.environ.get("HEARTBEAT_EVERY_SECONDS", "10"))
        self._last_heartbeat = 0
        # Shared secret so our own calls to the dashboard pass its password gate.
        # Same value the dashboard reads (FLASK_SECRET); empty locally = no gate.
        _tok = os.environ.get("FLASK_SECRET", "")
        self._internal_headers = {"X-Internal-Token": _tok} if _tok else {}

        # Operational guardrails
        self.max_trades_per_hour = int(os.environ.get("MAX_TRADES_PER_HOUR", "30"))
        self._trade_timestamps: List[float] = []

        # Price cache: {symbol: (price, fetched_at_epoch)}
        self._price_cache: Dict[str, Tuple[Optional[float], float]] = {}
        self._cache_ttl = int(os.environ.get("PRICE_CACHE_TTL", "8"))   # seconds

        # Daily bars cache: {symbol: (DataFrame, fetched_at_epoch)}
        # Daily bars don't change meaningfully within a session — 30-min TTL
        # prevents hammering Alpaca's API on every scan cycle.
        self._bars_cache: Dict[str, Tuple[Optional[pd.DataFrame], float]] = {}
        self._bars_cache_ttl = int(os.environ.get("BARS_CACHE_TTL", "1800"))  # 30 min

        # Market candidates cache: avoid calling list_assets every scan cycle
        self._market_candidates_cache: Tuple[List[str], float] = ([], 0.0)
        self._market_candidates_ttl = int(os.environ.get("MARKET_CANDIDATES_TTL", "600"))  # 10 min

        # Data-issue alert throttle: prevents notification spam when a symbol's
        # market data feed is unavailable for multiple scan cycles.
        self.data_issue_alert_cooldown = int(os.environ.get("DATA_ISSUE_ALERT_COOLDOWN", "300"))
        self._last_data_issue_alert: Dict[str, float] = {}
        self.data_issue_skip_seconds = int(os.environ.get("DATA_ISSUE_SKIP_SECONDS", "3600"))
        self._symbol_skip_until: Dict[str, float] = {}

        # ── Portfolio Safety Shield ─────────────────────────────────────────────
        # If the total portfolio value drops to/below this threshold,
        # the engine pauses ALL new buys and fires an alert.
        # 0 = disabled.  Example: start=$100k, set threshold=$99500 → max $500 loss.
        self.portfolio_stop_loss   = float(os.environ.get("PORTFOLIO_STOP_LOSS",   "0"))    # 0 = off
        self.portfolio_stop_buffer = float(os.environ.get("PORTFOLIO_STOP_BUFFER", "200"))  # recovery gap
        self.shield_enabled        = True
        self.shield_triggered      = False   # True = buys paused until recovery

        # ── 5hr 59min Minimum Hold Rule ────────────────────────────────────────
        # Don't exit a position until it has been held this many seconds.
        # Default 21,540 s = 5h 59m. Prevents same-day round-trip (day trade) flagging.
        # Emergency trailing-stops and hard stop-losses are EXEMPT (always fire).
        self.min_hold_seconds = int(os.environ.get("MIN_HOLD_SECONDS", "21540"))

    # ──────────────────────────────────────────────────────────────────────────
    # Portfolio Safety Shield
    # ──────────────────────────────────────────────────────────────────────────

    def _check_portfolio_shield(self):
        """
        Halt all new buys when total portfolio value drops to/below
        self.portfolio_stop_loss.  Resume only when it recovers to
        portfolio_stop_loss + portfolio_stop_buffer (hysteresis prevents flip-flop).
        """
        try:
            total = self._available_capital
            for sym, h in list(self.current_holdings.items()):
                cached_price, cached_at = self._price_cache.get(sym, (h["price"], 0))
                use_price = cached_price if (time.time() - cached_at) < 60 else h["price"]
                total += use_price * h["qty"]

            if total <= 0:
                return

            # Update capital high-water mark (the ladder never comes down)
            if total > self._capital_hwm:
                self._capital_hwm = total

            if not self.shield_triggered:
                # ── Trigger: portfolio fell to/below threshold ──
                if total <= self.portfolio_stop_loss:
                    self.shield_triggered = True
                    self.auto_trade = False   # Halt new buys — sell logic still runs
                    msg = (
                        f"\U0001f6e1 SAFETY SHIELD TRIGGERED! Portfolio ${total:,.2f} "
                        f"dropped to/below threshold ${self.portfolio_stop_loss:,.2f}. "
                        f"ALL new buys PAUSED. Current positions held. "
                        f"Will resume when value recovers to "
                        f"${self.portfolio_stop_loss + self.portfolio_stop_buffer:,.2f}."
                    )
                    self.send_alert(msg, level="alert")
                    self._send_pushover(
                        title="\U0001f6e1 SAFETY SHIELD FIRED",
                        message=(
                            f"Portfolio: ${total:,.2f}\n"
                            f"Threshold: ${self.portfolio_stop_loss:,.2f}\n"
                            f"AI buys PAUSED until recovery to "
                            f"${self.portfolio_stop_loss + self.portfolio_stop_buffer:,.2f}"
                        ),
                        priority=1,   # bypass quiet hours
                    )
            else:
                # ── Recovery: portfolio climbed back above threshold + buffer ──
                recovery_target = self.portfolio_stop_loss + self.portfolio_stop_buffer
                if total >= recovery_target:
                    self.shield_triggered = False
                    self.auto_trade = True    # Resume AI trading
                    msg = (
                        f"\u2705 SAFETY SHIELD RESET — Portfolio recovered to ${total:,.2f} "
                        f"(above ${recovery_target:,.2f}). Resuming AI trading."
                    )
                    self.send_alert(msg, level="rocket")
                    self._send_pushover(
                        title="\u2705 Shield Reset — Trading Resumed",
                        message=f"Portfolio: ${total:,.2f}  Recovery target: ${recovery_target:,.2f}",
                        priority=0,
                    )
        except Exception as e:
            self.send_alert(f"[shield] check error: {e}", level="warn")


    def start(self):
        with self._start_lock:
            self.running = True
            # Seed holdings from the broker ONCE so the dashboard reflects the real
            # account after every restart (runs once per engine instance/session).
            if not self._reconciled:
                self._reconcile_from_alpaca()
                self._reconciled = True
            # Start after-hours background watcher exactly once.
            if not self._afterhours_started:
                t = threading.Thread(target=self._afterhours_loop, daemon=True, name="afterhours-watcher")
                t.start()
                self._afterhours_started = True

    def stop(self):
        self.running = False

    def _autodetect_capital(self):
        """Size the capital pool to the broker account's REAL balance so buy/sell
        amounts scale to whatever the user actually funded — no manual
        INITIAL_CAPITAL needed. Runs once per session (auto mode only).

        Uses total EQUITY as the sizing base (so every % cap is measured against
        real money) and free CASH as the spendable pool. Deliberately ignores
        margin buying power — the engine sizes on cash it truly has. Fails SAFE:
        on any error, or a $0 account, it leaves the engine in its prior mode
        (legacy fixed ORDER_QTY sizing when capital was 0), never oversizing."""
        if not self._capital_is_auto:
            return  # user pinned an explicit INITIAL_CAPITAL — respect it

        def _f(v):
            try:
                return float(v)
            except Exception:
                return 0.0

        try:
            acct = self.api.get_account()
        except Exception as e:
            self.send_alert(
                f"Capital auto-detect skipped — could not read account balance: {e}. "
                f"Using fixed {os.environ.get('ORDER_QTY', '1')}-share sizing until next session.",
                level="warn")
            return

        equity = _f(getattr(acct, "equity", None)) or _f(getattr(acct, "portfolio_value", None))
        cash   = _f(getattr(acct, "cash", None))
        if equity <= 0:
            self.send_alert(
                "Capital auto-detect: account equity is $0 — staying in fixed-qty mode.",
                level="warn")
            return

        with self.lock:
            self.initial_capital    = equity
            self._available_capital = max(0.0, cash)   # only spend real free cash
            self._capital_hwm       = max(self._capital_hwm, equity)

        self.send_alert(
            f"Capital auto-detected from {self.trading_mode.upper()} account: "
            f"equity ${equity:,.2f}, free cash ${cash:,.2f}. Sizing every trade to your "
            f"real balance — {self.risk_per_trade_pct:.1f}% risk/trade, max "
            f"{self.max_position_pct:.0f}% per position, spread across ≥{self.min_positions} "
            f"positions.",
            level="info")

    def _reconcile_from_alpaca(self):
        """Seed in-memory holdings from the broker's REAL open positions.

        A fresh TradingEngine starts with empty current_holdings/trade_log.
        Because the supervisor builds a new engine every session (~5h59m),
        without this the dashboard would show nothing after each restart even
        though Alpaca still holds the positions. Reading them back makes the
        app 'return exactly as it was' after a restart.

        Note: Alpaca position objects carry no entry timestamp, so each seeded
        position's hold-clock restarts at 'now'. That only makes the engine
        WAIT LONGER before a voluntary profit-sell (never causes a same-day
        round-trip) — emergency stop-losses and trailing stops are exempt and
        still fire immediately.
        """
        # First, size the capital pool to the account's real balance (auto mode).
        # Runs before seeding holdings so total_capital = free cash + positions.
        self._autodetect_capital()

        try:
            positions = self.api.list_positions()
        except Exception as e:
            self.send_alert(
                f"Startup reconcile skipped — could not read Alpaca positions: {e}",
                level="warn",
            )
            return

        seeded = 0
        with self.lock:
            for pos in positions:
                try:
                    symbol = pos.symbol
                    qty = float(pos.qty)
                    if qty <= 0:
                        continue
                    if qty.is_integer():
                        qty = int(qty)
                    entry = float(pos.avg_entry_price)
                    try:
                        current = float(pos.current_price)
                    except Exception:
                        current = entry
                    self.current_holdings[symbol] = {
                        "price": entry, "qty": qty,
                        "cost": entry * qty, "time": time.time(),
                    }
                    # Trailing peak starts at the higher of entry / current price
                    self._peak_prices[symbol] = max(entry, current)
                    seeded += 1
                except Exception:
                    continue

        if seeded:
            self.send_alert(
                f"Reconciled {seeded} open position(s) from Alpaca on startup.",
                level="info",
            )

    def run_forever(self):
        """
        Main loop — polls live settings, optionally extends the scan queue with
        full-market momentum candidates, then scans all symbols concurrently.
        """
        self.start()
        while self.running:
            # Pick up live setting changes pushed from the dashboard UI
            self._poll_live_settings()
            # Portfolio Safety Shield — halt buys if portfolio drops to threshold
            if self.shield_enabled and self.portfolio_stop_loss > 0:
                self._check_portfolio_shield()
            self._maybe_heartbeat(message="scan-start")
            symbols = list(self.stock_list)

            # Market-wide scan: pull top momentum movers and add to this cycle's queue
            if self.scan_all_market:
                candidates = self._get_market_candidates(max_candidates=self._market_scan_candidates)
                symbols = list(dict.fromkeys(symbols + candidates))

            if symbols:
                with ThreadPoolExecutor(max_workers=min(self.max_workers, len(symbols))) as pool:
                    futures = {pool.submit(self._scan_symbol, sym): sym for sym in symbols}
                    for future in as_completed(futures):
                        if not self.running:
                            break
                        try:
                            future.result()
                        except Exception as exc:
                            sym = futures[future]
                            self.send_alert(f"Scan error for {sym}: {exc}", level="warn")

            self._maybe_heartbeat(message="scan-complete")
            time.sleep(self.poll_seconds)

    def _scan_symbol(self, symbol: str):
        """Fetch price and evaluate a single symbol (runs in thread pool)."""
        price = self.get_live_price(symbol)
        if price is None:
            with self.lock:
                self._symbol_signals[symbol] = {
                    "symbol": symbol,
                    "price": None,
                    "verdict": "HOLD",
                    "data_issue": "price_unavailable",
                    "data_issue_detail": "No latest trade/quote available from broker or fallback feeds.",
                }
            self._alert_data_issue(
                symbol,
                "price_unavailable",
                "Skipping this scan because no live price was returned.",
            )
            self.emit_activity(
                action="scan_skip",
                message=f"SCAN {symbol}: skipped (no live price).",
                symbol=symbol,
                level="warn",
            )
            return
        self.evaluate(symbol, price)

        # Emit one live-feed action for every completed symbol scan.
        try:
            with self.lock:
                snap = dict(self._symbol_signals.get(symbol) or {})
            verdict = str(snap.get("verdict") or "HOLD").upper()
            if verdict == "BUY_BLOCKED":
                msg = f"SCAN {symbol}: BUY signal blocked (auto-trade OFF) @ ${price:.2f}"
                action = "hold"
            elif verdict == "BUY":
                msg = f"SCAN {symbol}: BUY signal @ ${price:.2f}"
                action = "scan"
            elif verdict == "SELL":
                msg = f"SCAN {symbol}: SELL signal @ ${price:.2f}"
                action = "scan"
            else:
                msg = f"SCAN {symbol}: HOLD @ ${price:.2f}"
                action = "hold"
            self.emit_activity(action=action, message=msg, symbol=symbol, level="info")
        except Exception:
            pass

    def _alert_data_issue(self, symbol: str, issue: str, detail: str) -> None:
        """Emit a throttled warning for data issues so users can diagnose skips."""
        key = f"{symbol}:{issue}"
        now = time.time()
        issue_lc = str(issue or "").lower()

        # Keep problematic symbols out of market-candidate rotation for a while
        # so they do not keep reappearing every scan cycle.
        if issue_lc in ("bars_unavailable", "price_unavailable"):
            self._symbol_skip_until[str(symbol or "").upper()] = now + max(60, self.data_issue_skip_seconds)
            # Invalidate market-candidate cache so skip list applies immediately.
            self._market_candidates_cache = ([], 0.0)

        last = self._last_data_issue_alert.get(key, 0.0)
        if now - last < self.data_issue_alert_cooldown:
            return
        self._last_data_issue_alert[key] = now
        self.send_alert(
            (
                f"DATA ISSUE {symbol}: {issue.replace('_', ' ')}. "
                f"{detail}"
            ),
            level="warn",
            symbol=symbol,
        )

    # -------------------------------
    # Live settings poll
    # -------------------------------

    def _make_alpaca(self, mode: str):
        """Build an Alpaca REST client for the given mode. Live keys are read
        from key_store (env var OR keys the user entered in-app), so a live
        switch works without a restart. Falls back to paper when live keys are
        unavailable, so the engine can NEVER accidentally trade real money."""
        if mode == "live":
            lk, ls = key_store.get_live_keys()
            if lk and ls:
                return REST(lk, ls, base_url="https://api.alpaca.markets")
        return REST(self._paper_key, self._paper_secret,
                    base_url="https://paper-api.alpaca.markets")

    def _apply_trading_mode(self, mode: str) -> None:
        """Switch which Alpaca account the engine trades against. Only ever
        called with a mode the dashboard already authorized (license-gated).
        Fails safe to PAPER when live keys are missing."""
        mode = "live" if str(mode).lower() == "live" else "paper"
        if mode == self.trading_mode:
            return
        if mode == "live" and not key_store.has_live_keys():
            self.send_alert(
                "Live trading was requested but no live Alpaca keys are configured — "
                "staying in PAPER mode. Add live keys via the Setup Wizard.",
                level="warn")
            return
        self.api = self._make_alpaca(mode)
        self.trading_mode = mode
        # Peak prices belong to the previous account's positions — reset them.
        self._peak_prices.clear()
        self.send_alert(
            f"Trading mode switched to {mode.upper()} "
            f"({'REAL MONEY' if mode == 'live' else 'practice money'}).",
            level="trade" if mode == "live" else "info")

    def _poll_live_settings(self):
        """
        Fetch live trading settings from the dashboard's /api/settings/trading.
        Lets the UI change scan speed, trailing stop %, etc. without restarting.
        """
        if not self.dashboard_base_url:
            return
        try:
            r = requests.get(f"{self.dashboard_base_url}/api/settings/trading",
                             headers=self._internal_headers, timeout=3)
            if r.status_code != 200:
                return
            s = r.json()
            # Paper↔Live account switch first — the dashboard only ever reports an
            # effective mode of "live" after it has confirmed a valid license.
            if "trading_mode" in s: self._apply_trading_mode(s.get("trading_mode"))
            if "auto_trade"         in s: self.auto_trade          = bool(s["auto_trade"])
            if "poll_seconds"        in s: self.poll_seconds        = max(5, int(s["poll_seconds"]))
            if "trailing_stop_pct"   in s: self.trailing_stop_pct   = max(0.001, float(s["trailing_stop_pct"]) / 100.0)
            if "loss_threshold"      in s: self.loss_threshold       = max(0.001, float(s["loss_threshold"])    / 100.0)
            if "max_trades_per_hour" in s: self.max_trades_per_hour  = max(1, int(s["max_trades_per_hour"]))
            if "scan_all_market"     in s: self.scan_all_market      = bool(s["scan_all_market"])
            if "max_positions"       in s: self.max_positions        = max(1, int(s["max_positions"]))
            # Live-updatable position sizing / risk knobs from dashboard settings box
            if "initial_capital"     in s:
                new_cap = max(0.0, float(s["initial_capital"]))
                if new_cap > 0:
                    # Explicit manual override — pin the pool to this dollar amount.
                    if self._capital_is_auto or new_cap != self.initial_capital:
                        self._capital_is_auto = False
                        self.initial_capital = new_cap
                        if not self.current_holdings:   # only reset if no open positions
                            self._available_capital = new_cap
                # new_cap == 0 means AUTO. The dashboard sends 0 by default on
                # every poll, so we must NOT reset here — that would wipe the
                # auto-detected balance and mid-session spend tracking. Auto
                # detection happens once per session in _autodetect_capital().
            if "risk_per_trade_pct"  in s: self.risk_per_trade_pct  = max(0.1,  float(s["risk_per_trade_pct"]))
            if "max_position_pct"    in s: self.max_position_pct     = max(1.0,  float(s["max_position_pct"]))
            if "min_positions"       in s: self.min_positions        = max(1,    int(s["min_positions"]))
            if "risk_per_trade_usd"  in s: self.risk_per_trade_usd   = max(0.0,  float(s["risk_per_trade_usd"]))
            if "rsi_buy_max"         in s: self.rsi_buy_max          = max(20.0, float(s["rsi_buy_max"]))
            if "rsi_sell_min"        in s: self.rsi_sell_min         = max(50.0, float(s["rsi_sell_min"]))
            if "sma_spread_min"      in s: self.sma_spread_min       = max(0.0,  float(s["sma_spread_min"]))
            if "rocket_breakout_enabled" in s: self.rocket_breakout_enabled = bool(s["rocket_breakout_enabled"])
            if "rocket_breakout_min_day_change_pct" in s: self.rocket_breakout_min_day_change_pct = max(1.0, float(s["rocket_breakout_min_day_change_pct"]))
            if "rocket_breakout_volume_mult" in s: self.rocket_breakout_volume_mult = max(1.0, float(s["rocket_breakout_volume_mult"]))
            if "rocket_breakout_min_avg_volume" in s: self.rocket_breakout_min_avg_volume = max(0.0, float(s["rocket_breakout_min_avg_volume"]))
            if "rocket_breakout_max_above_sma20_pct" in s: self.rocket_breakout_max_above_sma20_pct = max(1.0, float(s["rocket_breakout_max_above_sma20_pct"]))
            if "rocket_breakout_lookback_bars" in s: self.rocket_breakout_lookback_bars = max(5, int(s["rocket_breakout_lookback_bars"]))
            if "forecast_exit_enabled" in s: self.forecast_exit_enabled = bool(s["forecast_exit_enabled"])
            # Safety Shield live settings
            if "portfolio_stop_loss"   in s: self.portfolio_stop_loss   = max(0.0, float(s["portfolio_stop_loss"]))
            if "portfolio_stop_buffer" in s: self.portfolio_stop_buffer = max(0.0, float(s["portfolio_stop_buffer"]))
            if "shield_enabled"        in s: self.shield_enabled         = bool(s["shield_enabled"])
            if "min_hold_seconds"      in s: self.min_hold_seconds       = max(0, int(s["min_hold_seconds"]))
        except Exception:
            pass

    # -------------------------------
    # Full-market momentum scanner
    # -------------------------------

    def _get_market_candidates(self, max_candidates: int = 30) -> List[str]:
        """
        Two-phase scan of the entire US equity market:
        1. Load all active tradable symbols from Alpaca (cached 10 min).
        2. Batch-fetch snapshots (price, volume, daily change) — 1 API call per 500.
        3. Filter: price $2–$1000, daily volume > 200k, day change > +0.5%.
        4. Return the top N by daily gain % (hottest movers first).
        Already-held and watchlist symbols are excluded (evaluated separately).

        10-minute cache: list_assets returns ~10k symbols and barely changes
        during a session — no need to re-fetch every scan cycle.
        """
        cached_syms, cached_ts = self._market_candidates_cache
        if cached_ts > 0 and (time.time() - cached_ts) < self._market_candidates_ttl:
            return cached_syms

        try:
            assets = self.api.list_assets(status="active", asset_class="us_equity")
            tradable = [
                a.symbol for a in assets
                if getattr(a, "tradable", False) and "." not in a.symbol
            ]
        except Exception as e:
            self.send_alert(f"Asset list fetch failed: {e}", level="warn")
            return []

        already_held = set(self.current_holdings.keys())
        watchlist    = set(self.stock_list)
        candidates: List[tuple] = []

        # Capital-based price ceiling: spread capital across min_positions stocks.
        # $10 capital / 5 positions = max $2/share; $10,000 / 5 = max $2,000/share.
        # Price floors/ceilings are env-tunable so operators can include
        # sub-$1 momentum names when desired.
        min_price_env = float(os.environ.get("MARKET_MIN_PRICE", "0.50"))
        max_price_env = float(os.environ.get("MARKET_MAX_PRICE", "5000"))
        min_price_env = max(0.10, min_price_env)
        max_price_env = max(min_price_env, max_price_env)
        with self.lock:
            invested = sum(h["qty"] * h["price"] for h in self.current_holdings.values())
        total_capital = self._available_capital + invested
        if total_capital > 0 and self.initial_capital > 0:
            max_price = max(2.0, total_capital / max(self.min_positions, 1))
            min_price = min_price_env
        else:
            max_price = 1000.0
            min_price = min_price_env
        max_price = min(max_price, max_price_env)

        BATCH = 500
        for i in range(0, min(len(tradable), 5000), BATCH):
            batch = tradable[i : i + BATCH]
            try:
                snaps = self.api.get_snapshots(batch)
                for sym, snap in snaps.items():
                    skip_until = self._symbol_skip_until.get(sym, 0.0)
                    if skip_until > time.time():
                        continue
                    if snap is None or sym in already_held or sym in watchlist:
                        continue
                    lt    = getattr(snap, "latest_trade", None)
                    price = float(getattr(lt, "price", 0) or 0)
                    if price < min_price or price > max_price:
                        continue
                    db     = getattr(snap, "daily_bar", None)
                    volume = float(getattr(db, "v", 0) or 0)
                    if volume < 200_000:
                        continue
                    pb         = getattr(snap, "prev_daily_bar", None)
                    prev_close = float(getattr(pb, "c", 0) or 0)
                    if prev_close <= 0:
                        continue
                    day_chg = (price - prev_close) / prev_close * 100
                    if day_chg >= 0.5:
                        candidates.append((sym, day_chg))
            except Exception:
                pass

        candidates.sort(key=lambda x: x[1], reverse=True)
        result = [sym for sym, _ in candidates[:max_candidates]]
        self._market_candidates_cache = (result, time.time())
        return result

    # -----------------------------------------------
    # After-hours portfolio guard (runs 24/7)
    # -----------------------------------------------

    def _is_market_open(self) -> bool:
        """Returns True if the US market is currently open (via Alpaca clock)."""
        try:
            clock = self.api.get_clock()
            return bool(clock.is_open)
        except Exception:
            return False   # assume closed on error — safer

    def _afterhours_loop(self):
        """
        Runs permanently on a background thread.
        - When market is OPEN: tracks rocket climbers in held positions.
        - When market is CLOSED: monitors held positions every 5 minutes,
          sends DND-breaking alerts and places GTC stop orders if a stock
          drops more than `afterhours_drop_pct` from its buy price.
        """
        CHECK_INTERVAL_OPEN   = 60    # seconds between checks while open
        CHECK_INTERVAL_CLOSED = 300   # 5 minutes between checks while closed
        while True:
            time.sleep(5)   # brief startup delay
            if not self.running:
                time.sleep(30)
                continue
            try:
                market_open = self._is_market_open()
                with self.lock:
                    holdings = dict(self.current_holdings)

                for symbol, holding in holdings.items():
                    price = self.get_live_price(symbol)
                    if price is None:
                        continue

                    bought_price = holding["price"]
                    qty          = holding["qty"]
                    change       = (price - bought_price) / bought_price

                    # ── Rocket alert — stock is surging ──
                    prev = self._ah_last_prices.get(symbol, bought_price)
                    climb_since_last = (price - prev) / prev if prev > 0 else 0
                    if climb_since_last >= self.rocket_alert_pct:
                        self._send_pushover(
                            title=f"ROCKET {symbol} +{climb_since_last*100:.1f}%",
                            message=(
                                f"{symbol} surged {climb_since_last*100:.1f}% "
                                f"to ${price:.2f}! Trailing stop protecting your gains."
                            ),
                            priority=1,   # HIGH — bypasses quiet hours, no repeat
                            sound="cashregister",
                        )
                    self._ah_last_prices[symbol] = price

                    # ── After-hours crash protection ──
                    if not market_open and change <= -self.afterhours_drop_pct:
                        if symbol not in self._ah_stops_placed:
                            # Place a GTC stop order that fires when market reopens
                            stop_price = round(price * 0.995, 2)   # 0.5% below current
                            self._place_protective_stop(symbol, qty, stop_price)
                            self._ah_stops_placed.add(symbol)
                            self._send_pushover(
                                title=f"CRASH ALERT: {symbol} {change*100:.1f}%",
                                message=(
                                    f"{symbol} is down {change*100:.1f}% after hours "
                                    f"(now ${price:.2f}, bought ${bought_price:.2f}). "
                                    f"Protective stop placed at ${stop_price:.2f}."
                                ),
                                priority=2,   # EMERGENCY — repeats every 60s until acknowledged
                                sound="siren",
                            )
                            self._send_twilio_call(
                                f"Alien AI Trader emergency. {symbol} is crashing "
                                f"{abs(change*100):.0f} percent after hours. "
                                f"A protective stop order has been placed at "
                                f"${stop_price:.2f}. Check your dashboard."
                            )
                    # Clear stop flag once stock recovers above threshold
                    elif change > -self.afterhours_drop_pct and symbol in self._ah_stops_placed:
                        self._ah_stops_placed.discard(symbol)

                interval = CHECK_INTERVAL_OPEN if market_open else CHECK_INTERVAL_CLOSED
            except Exception as exc:
                interval = 60
                print(f"[afterhours-watcher] error: {exc}")
            time.sleep(interval)

    def _place_protective_stop(self, symbol: str, qty: int, stop_price: float):
        """Place a GTC stop-market order that executes when the market opens."""
        try:
            self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side="sell",
                type="stop",
                stop_price=str(stop_price),
                time_in_force="gtc",
            )
            self.send_alert(
                f"Protective GTC stop placed: SELL {qty}x {symbol} if price <= ${stop_price:.2f}",
                level="warn", symbol=symbol,
            )
        except Exception as e:
            self.send_alert(f"Failed to place stop for {symbol}: {e}", level="alert", symbol=symbol)

    # -----------------------------------------------
    # Pushover (DND-breaking push notifications)
    # -----------------------------------------------

    def _send_pushover(self, title: str, message: str, priority: int = 0, sound: str = "pushover"):
        """
        Send a Pushover notification.
        priority: -1=silent, 0=normal, 1=high (bypasses DND), 2=emergency (repeats until ACK)
        """
        if not self.pushover_token or not self.pushover_user:
            return
        payload = {
            "token":    self.pushover_token,
            "user":     self.pushover_user,
            "title":    title,
            "message":  message,
            "priority": priority,
            "sound":    sound,
        }
        if priority == 2:
            # Emergency: repeat every 60s, expire after 1 hour
            payload["retry"]  = 60
            payload["expire"] = 3600
        try:
            requests.post("https://api.pushover.net/1/messages.json", data=payload, timeout=8)
        except Exception as e:
            print(f"[pushover] send failed: {e}")

    # -----------------------------------------------
    # Twilio voice call (emergency crash)
    # -----------------------------------------------

    def _send_twilio_call(self, spoken_message: str):
        """Call the user's phone and speak the alert. Breaks through Do Not Disturb."""
        if not self.twilio_client or not self.twilio_from or not self.twilio_to:
            return
        try:
            twiml = (
                f"<Response><Say voice='alice'>{spoken_message} "
                f"This message will repeat once.</Say>"
                f"<Pause length='1'/>"
                f"<Say voice='alice'>{spoken_message}</Say></Response>"
            )
            self.twilio_client.calls.create(
                twiml=twiml,
                to=self.twilio_to,
                from_=self.twilio_from,
            )
        except Exception as e:
            print(f"[twilio-call] failed: {e}")

    # -----------------------------------------------
    # Capital ratchet — the ladder never comes down
    # -----------------------------------------------

    def _update_capital_hwm(self):
        """
        After every sell, check if total portfolio value has hit a new all-time high.
        If yes, update the high-water mark and send a celebratory rocket alert.
        """
        if self.initial_capital <= 0:
            return
        with self.lock:
            invested = sum(h["qty"] * h["price"] for h in self.current_holdings.values())
            total    = self._available_capital + invested
        if total > self._capital_hwm * 1.005:   # 0.5% buffer avoids noise
            self._capital_hwm = total
            self._send_pushover(
                title=f"New All-Time High: ${total:.2f}",
                message=(
                    f"Your capital pool just hit a new record of ${total:.2f}! "
                    f"The ladder keeps climbing. Keep going."
                ),
                priority=1,
                sound="cashregister",
            )
            self.send_alert(
                f"NEW ALL-TIME HIGH: portfolio total = ${total:.2f}",
                level="info",
            )

    # -------------------------------
    # Market data  (with price cache)
    # -------------------------------

    def get_live_price(self, symbol: str) -> Optional[float]:
        # Serve from cache if fresh enough
        cached = self._price_cache.get(symbol)
        if cached and (time.time() - cached[1]) < self._cache_ttl:
            return cached[0]

        price = None
        try:
            try:
                t = self.api.get_latest_trade(symbol, feed=self.alpaca_data_feed)
            except TypeError:
                # Older alpaca_trade_api versions do not support feed=...
                t = self.api.get_latest_trade(symbol)
            price = float(getattr(t, "price", 0) or 0)
            if price <= 0:
                price = None
        except Exception:
            # Feed entitlement mismatches are common in live mode; retry with IEX.
            if self.alpaca_data_feed != "iex":
                try:
                    t = self.api.get_latest_trade(symbol, feed="iex")
                    price = float(getattr(t, "price", 0) or 0)
                    if price <= 0:
                        price = None
                except Exception:
                    pass

        # Fallback to quote midpoint when latest trade is unavailable.
        if price is None:
            for feed_try in [self.alpaca_data_feed, "iex"]:
                try:
                    try:
                        q = self.api.get_latest_quote(symbol, feed=feed_try)
                    except TypeError:
                        q = self.api.get_latest_quote(symbol)
                    bid = float(getattr(q, "bidprice", 0) or 0)
                    ask = float(getattr(q, "askprice", 0) or 0)
                    if bid > 0 and ask > 0:
                        price = (bid + ask) / 2.0
                        break
                    if ask > 0:
                        price = ask
                        break
                    if bid > 0:
                        price = bid
                        break
                except Exception:
                    continue

        if price is None:
            # Last-resort fallback to Alpha Vantage.
            try:
                data, _ = self.ts.get_quote_endpoint(symbol)
                px = float(data.get("05. price", 0) or 0)
                price = px if px > 0 else None
            except Exception:
                pass

        self._price_cache[symbol] = (price, time.time())
        return price

    def _get_bars_df(self, symbol: str, limit: int = 100) -> Optional[pd.DataFrame]:
        """
        Fetch recent DAILY bars as a DataFrame with a 30-minute cache.

        WHY DAILY:
          RSI-14, SMA-20, SMA-50, MACD, and Bollinger Bands are all standard
          *daily* indicators. Using 1-minute bars produced a 14-minute RSI and
          a 20-minute SMA — numbers that look valid but mean something completely
          different and cannot produce reliable trade signals.

        WHY CACHED:
          Daily bars are stable for at least 30 minutes. Fetching them on every
          15-60 second scan cycle burned Alpaca API quota for no benefit.
          With caching, a 35-symbol watchlist uses ~35 Alpaca calls per 30 min
          instead of ~35 calls per minute.
        """
        # Serve from cache if fresh
        cached = self._bars_cache.get(symbol)
        if cached and (time.time() - cached[1]) < self._bars_cache_ttl:
            return cached[0]

        df = None

        def _df_from_alpha_daily() -> Optional[pd.DataFrame]:
            """Fallback historical bars from Alpha Vantage daily endpoint."""
            try:
                data, _ = self.ts.get_daily_adjusted(symbol=symbol, outputsize="compact")
                ts = data.get("Time Series (Daily)", {}) if isinstance(data, dict) else {}
                if not ts:
                    return None
                rows = []
                for _, bar in ts.items():
                    rows.append({
                        "o": float(bar.get("1. open", 0) or 0),
                        "h": float(bar.get("2. high", 0) or 0),
                        "l": float(bar.get("3. low", 0) or 0),
                        "c": float(bar.get("4. close", 0) or 0),
                        "v": float(bar.get("6. volume", 0) or 0),
                    })
                if not rows:
                    return None
                out = pd.DataFrame(rows)
                out = out[(out["c"] > 0) & (out["o"] >= 0) & (out["h"] >= 0) & (out["l"] >= 0)]
                if out.empty:
                    return None
                # Keep most recent rows and preserve oldest->newest order for rolling indicators.
                out = out.head(max(10, int(limit)))
                return out.iloc[::-1].reset_index(drop=True)
            except Exception:
                return None
        try:
            try:
                bars = self.api.get_bars(symbol, TimeFrame.Day, limit=limit, feed=self.alpaca_data_feed)
            except TypeError:
                bars = self.api.get_bars(symbol, TimeFrame.Day, limit=limit)
            except Exception:
                if self.alpaca_data_feed != "iex":
                    bars = self.api.get_bars(symbol, TimeFrame.Day, limit=limit, feed="iex")
                else:
                    raise
            bar_list = list(bars) if bars else []
            if bar_list:
                df = pd.DataFrame([{
                    "c": float(b.c),
                    "v": float(b.v),
                    "h": float(b.h),
                    "l": float(b.l),
                    "o": float(b.o),
                } for b in bar_list])
            else:
                # Fallback: try hourly bars if daily returns nothing
                # (can happen for thinly traded or recently listed symbols)
                try:
                    bars_h = self.api.get_bars(symbol, TimeFrame.Hour, limit=limit, feed=self.alpaca_data_feed)
                except TypeError:
                    bars_h = self.api.get_bars(symbol, TimeFrame.Hour, limit=limit)
                except Exception:
                    if self.alpaca_data_feed != "iex":
                        bars_h = self.api.get_bars(symbol, TimeFrame.Hour, limit=limit, feed="iex")
                    else:
                        raise
                bar_list_h = list(bars_h) if bars_h else []
                if bar_list_h:
                    df = pd.DataFrame([{
                        "c": float(b.c),
                        "v": float(b.v),
                        "h": float(b.h),
                        "l": float(b.l),
                        "o": float(b.o),
                    } for b in bar_list_h])
                else:
                    # Last-resort fallback to Alpha Vantage daily bars.
                    df = _df_from_alpha_daily()
        except Exception as e:
            print(f"[ENGINE] _get_bars_df({symbol}) error: {e}")
            if df is None:
                df = _df_from_alpha_daily()

        self._bars_cache[symbol] = (df, time.time())
        return df

    # -------------------------------
    # Technical indicators
    # -------------------------------

    def _calc_rsi(self, closes: pd.Series, period: int = 14) -> Optional[float]:
        """Calculate RSI for the most recent bar."""
        if len(closes) < period + 1:
            return None
        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(period).mean().iloc[-1]
        avg_loss = loss.rolling(period).mean().iloc[-1]
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    def _calc_sma(self, closes: pd.Series, period: int) -> Optional[float]:
        if len(closes) < period:
            return None
        return float(closes.rolling(period).mean().iloc[-1])

    def _get_signal(self, symbol: str, price: float) -> Dict[str, Any]:
        """
        Returns a signal dict using DAILY bars for all indicators.

        Indicators calculated (all on daily close prices):
          RSI-14       — momentum oscillator; buy dip below rsi_buy_max
          SMA-20/50    — trend filter; golden cross = uptrend confirmed
          MACD 12/26/9 — momentum confirmation
          Bollinger    — 20-day bands; price inside = not extended
          VWAP         — volume-weighted average price over the bar window
          week52_high/low — 52-week (approx.) range for ladder trend scoring
        """
        df = self._get_bars_df(symbol)   # daily bars, limit=100, 30-min cached
        signal: Dict[str, Any] = {
            "symbol": symbol, "price": price,
            "rsi": None, "sma20": None, "sma50": None,
            "macd": None, "macd_signal": None,
            "boll_upper": None, "boll_mid": None, "boll_lower": None,
            "vwap": None,
            "week52_high": None, "week52_low": None,
            "forecast": None,
            "forecast_direction": "neutral",
            "forecast_phase": "unknown",
            "predicted_price": None,
            "verdict": "HOLD",
            "rocket_breakout_triggered": False,
            "avg_volume_20": None,
            "realized_vol_20d": None,
            "data_issue": None,
            "data_issue_detail": "",
        }
        if df is None or df.empty:
            signal["data_issue"] = "bars_unavailable"
            signal["data_issue_detail"] = "No historical bars available to compute indicators."
            return signal

        # Populate 52-week range from the daily bar window (up to ~5 months
        # on limit=100; close enough for the ladder trend score)
        if "h" in df.columns and "l" in df.columns:
            signal["week52_high"] = round(float(df["h"].max()), 4)
            signal["week52_low"]  = round(float(df["l"].min()), 4)

        closes = df["c"].astype(float)
        rsi = self._calc_rsi(closes)
        sma20 = self._calc_sma(closes, 20)
        sma50 = self._calc_sma(closes, 50)
        macd, macd_signal = self._calc_macd(closes)
        boll_upper, boll_mid, boll_lower = self._calc_bollinger(closes)
        vwap = self._calc_vwap(df)

        signal["rsi"] = rsi
        signal["sma20"] = round(sma20, 4) if sma20 else None
        signal["sma50"] = round(sma50, 4) if sma50 else None
        signal["macd"] = round(macd, 4) if macd is not None else None
        signal["macd_signal"] = round(macd_signal, 4) if macd_signal is not None else None
        signal["boll_upper"] = round(boll_upper, 4) if boll_upper else None
        signal["boll_mid"] = round(boll_mid, 4) if boll_mid else None
        signal["boll_lower"] = round(boll_lower, 4) if boll_lower else None
        signal["vwap"] = round(vwap, 4) if vwap else None
        try:
            if "v" in df.columns and len(df["v"]) >= 20:
                signal["avg_volume_20"] = round(float(df["v"].astype(float).tail(20).mean()), 2)
            returns = closes.pct_change().dropna()
            if len(returns) >= 20:
                signal["realized_vol_20d"] = round(float(statistics.pstdev(returns.tail(20).tolist())), 6)
        except Exception:
            pass

        # ── Predictive forecast (linear regression + EMA stacking) ──
        try:
            fc = get_forecast(closes, periods_ahead=5)
            signal["forecast"]           = fc
            signal["forecast_direction"] = fc["forecast_direction"]
            signal["forecast_phase"]     = fc["forecast_phase"]
            signal["predicted_price"]    = fc.get("predicted_price")
        except Exception:
            pass

        # ── Advanced confluence logic ──
        # BUY requires ALL of:
        #   1. Golden cross: SMA20 > SMA50 by at least sma_spread_min %
        #   2. RSI below rsi_buy_max
        #   3. MACD > MACD signal (bullish)
        #   4. Price above lower Bollinger Band but below upper
        #   5. Price not far above VWAP (within 2%)
        # SELL if:
        #   1. Death cross (SMA20 < SMA50)
        #   2. RSI > rsi_sell_min
        #   3. MACD < MACD signal (bearish)
        #   4. Price >= upper Bollinger Band

        if sma20 and sma50 and rsi is not None and macd is not None and macd_signal is not None and boll_upper and boll_lower and vwap:
            spread_pct = abs(sma20 - sma50) / sma50 * 100
            golden_cross = sma20 > sma50 and spread_pct >= self.sma_spread_min
            death_cross  = sma20 < sma50
            price_above_lower = price > boll_lower
            price_below_upper = price < boll_upper
            price_near_vwap = abs(price - vwap) / vwap <= 0.02
            forecast_up = signal.get("forecast_direction") == "up"

            # BUY: all must be true — forecast confirms upward momentum
            if (
                golden_cross and
                rsi < self.rsi_buy_max and
                macd > macd_signal and
                price_above_lower and price_below_upper and
                price_near_vwap and
                forecast_up
            ):
                signal["verdict"] = "BUY"
                signal["spread_pct"] = round(spread_pct, 3)
            # SELL: any trigger fires
            elif (
                death_cross or
                rsi > self.rsi_sell_min or
                macd < macd_signal or
                price >= boll_upper
            ):
                signal["verdict"] = "SELL"
                signal["spread_pct"] = round(spread_pct, 3)

        # Optional breakout mode: lets the engine participate in genuine rocket
        # moves that fail dip-buy rules but clear momentum + liquidity checks.
        if signal.get("verdict") == "HOLD" and self.rocket_breakout_enabled:
            try:
                latest_close = float(closes.iloc[-1]) if len(closes) else float(price)
                prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else None
                latest_vol = float(df["v"].astype(float).iloc[-1]) if ("v" in df.columns and len(df["v"])) else 0.0

                avg_vol = signal.get("avg_volume_20")
                if avg_vol is None and "v" in df.columns and len(df["v"]) > 0:
                    avg_vol = float(df["v"].astype(float).tail(min(20, len(df["v"]))).mean())

                day_change_pct = None
                if prev_close and prev_close > 0:
                    day_change_pct = (latest_close - prev_close) / prev_close * 100.0

                prev_high = None
                if "h" in df.columns and len(df["h"]) >= 2:
                    lb = max(5, int(self.rocket_breakout_lookback_bars))
                    highs = df["h"].astype(float).tail(min(lb, len(df["h"])))
                    if len(highs) >= 2:
                        prev_high = float(highs.iloc[:-1].max())

                broke_recent_high = (prev_high is not None and latest_close > prev_high)
                liquid_enough = (avg_vol is not None and float(avg_vol) >= self.rocket_breakout_min_avg_volume)
                volume_surge = (avg_vol is not None and float(avg_vol) > 0 and latest_vol >= float(avg_vol) * self.rocket_breakout_volume_mult)
                strong_day = (day_change_pct is not None and day_change_pct >= self.rocket_breakout_min_day_change_pct)
                sma20_gap_pct = ((price - sma20) / sma20 * 100.0) if (sma20 and sma20 > 0) else 0.0
                not_overextended = (sma20 is None or sma20_gap_pct <= self.rocket_breakout_max_above_sma20_pct)
                momentum_ok = (macd is None or macd_signal is None or macd >= macd_signal)
                forecast_ok = signal.get("forecast_direction") in ("up", "neutral")

                if (
                    strong_day and
                    broke_recent_high and
                    liquid_enough and
                    volume_surge and
                    not_overextended and
                    momentum_ok and
                    forecast_ok
                ):
                    signal["verdict"] = "BUY"
                    signal["rocket_breakout_triggered"] = True
                    signal["rocket_breakout_detail"] = {
                        "day_change_pct": round(float(day_change_pct), 3),
                        "latest_volume": round(float(latest_vol), 2),
                        "avg_volume_20": round(float(avg_vol), 2) if avg_vol is not None else None,
                        "recent_high": round(float(prev_high), 4) if prev_high is not None else None,
                        "above_sma20_pct": round(float(sma20_gap_pct), 3),
                    }
            except Exception:
                pass

        return signal

    def _forecast_required_for_entry(self, signal: Dict[str, Any], price: float) -> Tuple[bool, List[str]]:
        """Return whether forecast must be UP before entry, and the reasons.

        Mandatory when trade is capital-intensive, volatile, or not highly liquid.
        Optional confidence booster when liquid + low-volatility + small allocation.
        """
        reasons: List[str] = []
        with self.lock:
            invested = sum(h["qty"] * h["price"] for h in self.current_holdings.values())
            total_capital = self._available_capital + invested
            slots = max(1, max(self.max_positions, self.min_positions) - len(self.current_holdings))
            est_alloc = self._available_capital / slots if self.initial_capital > 0 else price

        alloc_pct = (est_alloc / total_capital * 100.0) if total_capital > 0 else 0.0
        if alloc_pct >= self.forecast_required_capital_pct:
            reasons.append("capital_intensive")

        vol20 = signal.get("realized_vol_20d")
        if vol20 is not None and float(vol20) >= self.forecast_required_volatility:
            reasons.append("volatile")

        avg_vol = signal.get("avg_volume_20")
        if avg_vol is not None and float(avg_vol) < self.forecast_required_min_volume:
            reasons.append("long_lead_or_illiquid")

        return bool(reasons), reasons

    # -------------------------------
    # Decision logic
    # -------------------------------

    def evaluate(self, symbol: str, price: Optional[float]):
        if price is None:
            return

        signal = self._get_signal(symbol, price)
        if signal.get("data_issue"):
            self._alert_data_issue(
                symbol,
                str(signal.get("data_issue")),
                str(signal.get("data_issue_detail") or "Missing market data for indicators."),
            )
        # Integrate news/sentiment analysis
        sentiment = get_symbol_sentiment(symbol)
        signal["sentiment_score"] = sentiment["sentiment_score"]
        signal["sentiment_headlines"] = sentiment["headlines"]
        # Block BUY if sentiment is negative
        if signal["verdict"] == "BUY" and sentiment["sentiment_score"] < 0:
            signal["verdict"] = "HOLD"
            signal["sentiment_blocked"] = True
        # If mode is 'AI_MODEL', override verdict with ML model prediction
        if self.mode == "AI_MODEL":
            verdict = ai_predict_signal(signal)
            signal["verdict"] = verdict
        with self.lock:
            self._symbol_signals[symbol] = signal
            holding = self.current_holdings.get(symbol)

        if self.mode != "AI":
            return

        if not holding:
            # Only enter if we have an open position slot
            if signal["verdict"] == "BUY" and len(self.current_holdings) < self.max_positions:
                forecast_required, forecast_reasons = self._forecast_required_for_entry(signal, price)
                if forecast_required and signal.get("forecast_direction") != "up":
                    signal["verdict"] = "HOLD"
                    signal["forecast_blocked"] = True
                    signal["forecast_required"] = True
                    signal["forecast_required_reasons"] = forecast_reasons
                    self.send_alert(
                        f"FORECAST BLOCK: {symbol} buy skipped (requires forecast UP for {', '.join(forecast_reasons)} asset profile).",
                        level="warn",
                        symbol=symbol,
                    )
                    return
                signal["forecast_required"] = forecast_required
                # Auto-trade master switch — if OFF, signal but don't execute
                if not self.auto_trade:
                    signal["verdict"] = "BUY_BLOCKED"
                    print(f"[ENGINE] {symbol} BUY signal — auto-trade is OFF, skipping.")
                    return
                # Check ladder approval if scanner is attached
                # is_ladder_approved is attached by integrate_ladder_with_engine()
                ladder_check = getattr(self, 'is_ladder_approved', None)
                if ladder_check and not ladder_check(symbol):
                    entry = getattr(self, 'ladder_scanner', None)
                    score = entry._ladder.get(symbol.upper()) if entry else None
                    tier  = score.tier if score else 'UNKNOWN'
                    sc    = score.score if score else 0.0
                    signal["verdict"]        = "HOLD"
                    signal["ladder_blocked"] = True
                    signal["ladder_tier"]    = tier
                    signal["ladder_score"]   = sc
                    return  # Skip buy -- not in top ladder tier

                if self.initial_capital > 0:
                    if self._available_capital >= price:
                        self.buy(symbol, price, signal=signal)
                else:
                    self.buy(symbol, price, signal=signal)
        else:
            bought_price    = holding["price"]
            change_from_buy = (price - bought_price) / bought_price

            # Update trailing high-water mark
            with self.lock:
                peak = self._peak_prices.get(symbol, bought_price)
                if price > peak:
                    self._peak_prices[symbol] = price
                    peak = price

            drop_from_peak = (peak - price) / peak if peak > 0 else 0

            # ── 5hr 59min minimum hold check ──
            # Forecast + signal exits respect the minimum hold time.
            # Emergency trailing-stop and hard stop-loss always fire immediately.
            _hold_secs = time.time() - holding.get("time", time.time())
            _min_hold_ok = self.min_hold_seconds <= 0 or _hold_secs >= self.min_hold_seconds

            # 1. Trailing stop — price fell X% below its peak since purchase → SELL
            if drop_from_peak >= self.trailing_stop_pct:
                if not self.auto_trade:
                    print(f"[ENGINE] {symbol} TRAILING STOP triggered — auto-trade is OFF, skipping sell.")
                    return
                self.send_alert(
                    f"TRAILING STOP: {symbol} fell {drop_from_peak*100:.1f}% from peak "
                    f"${peak:.2f} \u2192 selling @ ${price:.2f}",
                    level="warn", symbol=symbol,
                )
                self.sell(symbol, price, reason="trailing_stop")

            # 2. Absolute floor stop-loss (catches a stock that never rose)
            elif change_from_buy <= -self.loss_threshold:
                self.send_alert(
                    f"STOP-LOSS: {symbol} down {change_from_buy*100:.1f}% from entry. "
                    f"Selling @ ${price:.2f}",
                    level="alert", symbol=symbol,
                )
                self.sell(symbol, price, reason="stop_loss")

            # 3. Forecast-based early exit: momentum peaked — sell before trailing stop fires
            #    Only exits when: forecast flips DOWN + EMA phase is "falling" + in profit
            #    Respects 5hr 59min minimum hold rule.
            elif (
                self.forecast_exit_enabled and
                _min_hold_ok and
                signal.get("forecast_direction") == "down" and
                signal.get("forecast_phase") == "falling" and
                change_from_buy > 0
            ):
                if not self.auto_trade:
                    print(f"[ENGINE] {symbol} FORECAST EXIT triggered — auto-trade is OFF, skipping sell.")
                    return
                self.send_alert(
                    f"FORECAST EXIT: {symbol} momentum peaked @ ${peak:.2f} "
                    f"(+{change_from_buy*100:.1f}% since buy) — forecast flipped DOWN. "
                    f"Selling @ ${price:.2f} before drop materialises.",
                    level="warn", symbol=symbol,
                )
                self.sell(symbol, price, reason="forecast_exit")

            # 4. Signal-based exit (death cross / RSI overbought) while in profit
            #    Respects 5hr 59min minimum hold rule — emergency stops above are exempt.
            elif signal["verdict"] == "SELL" and change_from_buy > 0 and _min_hold_ok:
                self.sell(symbol, price, reason="signal_exit")

    def should_buy(self, symbol: str, price: float) -> bool:
        signal = self._get_signal(symbol, price)
        return signal["verdict"] == "BUY"

    # -------------------------------
    # Execution
    # -------------------------------

    def _throttle_trades(self) -> bool:
        now = time.time()
        one_hour_ago = now - 3600
        self._trade_timestamps = [t for t in self._trade_timestamps if t >= one_hour_ago]
        return len(self._trade_timestamps) < self.max_trades_per_hour

    def buy(self, symbol: str, price: float, signal: Optional[Dict[str, Any]] = None):
        with self._buy_lock:
            if not self._throttle_trades():
                self.send_alert(f"Trade throttled (max/hour). Skipped buy for {symbol}.", level="warn")
                return

            with self.lock:
                if symbol in self.current_holdings:
                    return
                if len(self.current_holdings) >= self.max_positions:
                    self.send_alert(f"Position limit reached. Skipped buy for {symbol}.", level="warn", symbol=symbol)
                    return

        # ── Position sizing ──────────────────────────────────────────────────
        #
        # Capital pool mode (INITIAL_CAPITAL > 0):
        #   Spreads capital using risk-per-trade % with two hard caps:
        #     1. RISK_PER_TRADE_PCT  — e.g. 2% of $100 = $2.00 max risk per trade
        #     2. MAX_POSITION_PCT    — e.g. 20% of $100 = $20.00 max position size
        #     3. RISK_PER_TRADE_USD  — optional hard dollar cap (e.g. $10 max)
        #     4. MIN_POSITIONS slot  — ensures capital spreads across ≥ min_positions
        #   Example with $100, 5 max positions, 2% risk, 20% max position:
        #     → slot_alloc = $100 / 5 = $20 per slot
        #     → risk_cap   = $100 * 2% = $2.00 per trade
        #     → actual alloc = min($20, $2 * (price / stop_distance)) ≈ small slice
        #     → Result: several $2-$20 positions, never one $99 bet!
        #
            if self.initial_capital > 0:
                with self.lock:
                    total_capital = self._available_capital + sum(
                        h["qty"] * h["price"] for h in self.current_holdings.values()
                    )

            # Slot-based allocation: spread across max(max_positions, min_positions) slots
                effective_slots = max(self.max_positions, self.min_positions)
                with self.lock:
                    open_slots = max(1, effective_slots - len(self.current_holdings))
                    avail_now = self._available_capital
                slot_alloc = avail_now / open_slots

            # --- Dynamic risk adjustment ---
            # 1. Streak-based risk adjustment
            streak_risk = adjust_risk_for_streak(self.risk_per_trade_pct, self.trade_log)

            # 2. Volatility-based risk adjustment (use last 20 closes)
            df = self._get_bars_df(symbol, limit=21)
            closes = df["c"].astype(float) if df is not None and not df.empty else None
            vol_risk = streak_risk
            if closes is not None:
                vol = calc_volatility(closes)
                vol_risk = adjust_risk_for_volatility(streak_risk, vol)

            # Risk-per-trade cap (% of total capital)
            risk_alloc = total_capital * (vol_risk / 100.0)

            # Max position cap (% of total capital)
            max_alloc  = total_capital * (self.max_position_pct  / 100.0)

            # Hard USD cap (if set)
            if self.risk_per_trade_usd > 0:
                risk_alloc = min(risk_alloc, self.risk_per_trade_usd)

            # Final allocation = most conservative of slot, risk, and max caps
                alloc = min(slot_alloc, risk_alloc, max_alloc)
                alloc = min(alloc, avail_now)   # never exceed what we have

                qty  = max(1, int(alloc / price))
                cost = qty * price

            # Final safety: if even 1 share costs more than available capital, skip
                with self.lock:
                    avail_now = self._available_capital
                if price > avail_now:
                    self.send_alert(
                        f"Insufficient capital (${avail_now:.2f}) to buy even "
                        f"1x {symbol} @ ${price:.2f} — skipping.",
                        level="warn",
                    )
                    return

            # Clamp qty so cost never exceeds available capital
                while cost > avail_now and qty > 1:
                    qty  -= 1
                    cost  = qty * price

                if qty < 1:
                    self.send_alert(
                        f"Position sizing produced qty=0 for {symbol} @ ${price:.2f} "
                        f"(available: ${avail_now:.2f}, alloc: ${alloc:.2f}). Skipping.",
                        level="warn",
                    )
                    return

                # Hard invariants (never bypassed): exposure and reserve limits.
                invested_now = max(0.0, total_capital - avail_now)
                projected_invested = invested_now + cost
                projected_cash = max(0.0, avail_now - cost)
                exposure_pct = (projected_invested / total_capital * 100.0) if total_capital > 0 else 0.0
                reserve_pct = (projected_cash / total_capital * 100.0) if total_capital > 0 else 0.0
                if exposure_pct > self.max_gross_exposure_pct:
                    self.send_alert(
                        f"HARD GUARD: blocked {symbol} buy; projected exposure {exposure_pct:.1f}% exceeds max {self.max_gross_exposure_pct:.1f}%.",
                        level="warn",
                        symbol=symbol,
                    )
                    return
                if reserve_pct < self.min_cash_reserve_pct:
                    self.send_alert(
                        f"HARD GUARD: blocked {symbol} buy; projected cash reserve {reserve_pct:.1f}% below minimum {self.min_cash_reserve_pct:.1f}%.",
                        level="warn",
                        symbol=symbol,
                    )
                    return

                self.send_alert(
                    f"SIZING: {symbol} @ ${price:.2f} | "
                    f"slots={open_slots} slot_alloc=${slot_alloc:.2f} "
                    f"risk_alloc=${risk_alloc:.2f} max_alloc=${max_alloc:.2f} "
                    f"(streak_risk={streak_risk:.2f}%, vol_risk={vol_risk:.2f}%) "
                    f"→ buying {qty}x (${cost:.2f})",
                    level="info", symbol=symbol,
                )
            else:
                qty  = int(os.environ.get("ORDER_QTY", "1"))
                cost = qty * price

            try:
                self.api.submit_order(
                    symbol=symbol,
                    qty=qty,
                    side="buy",
                    type="market",
                    time_in_force="day",
                )

                with self.lock:
                    if self.initial_capital > 0:
                        self._available_capital -= cost
                    self.current_holdings[symbol] = {
                        "price": price, "qty": qty,
                        "cost": cost, "time": time.time(),
                    }
                    self._peak_prices[symbol] = price       # start trailing peak at buy price
                    self._trade_timestamps.append(time.time())
                    self.trade_log.append({
                        "action": "BUY", "symbol": symbol, "price": price,
                        "qty": qty, "cost": cost, "time": time.time(),
                        "rsi": signal.get("rsi") if signal else None,
                    })

                msg = f"BUY {qty}x {symbol} @ ${price:.2f} (cost ${cost:.2f})"
                if signal:
                    msg += f" | RSI={signal.get('rsi')} SMA20/50={signal.get('sma20')}/{signal.get('sma50')}"
                self.send_alert(msg, level="info", symbol=symbol)

            except Exception as e:
                self.send_alert(f"BUY ERROR {symbol}: {e}", level="alert", symbol=symbol)

    def sell(self, symbol: str, price: float, reason: str = "profit"):
        with self.lock:
            holding = self.current_holdings.pop(symbol, None)
            peak    = self._peak_prices.pop(symbol, price)
        if not holding:
            return

        qty          = holding.get("qty", int(os.environ.get("ORDER_QTY", "1")))
        bought_price = holding["price"]
        proceeds     = qty * price
        pnl          = (price - bought_price) * qty

        try:
            self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side="sell",
                type="market",
                time_in_force="day",
            )

            with self.lock:
                self.profit += pnl
                if self.initial_capital > 0:
                    self._available_capital += proceeds   # reinvest full proceeds
                self._trade_timestamps.append(time.time())
                self.trade_log.append({
                    "action": "SELL", "symbol": symbol, "price": price,
                    "qty": qty, "pnl": round(pnl, 4),
                    "proceeds": round(proceeds, 2),
                    "peak": round(peak, 4),
                    "reason": reason,
                    "time": time.time(),
                })

            label = reason.replace("_", " ").upper()
            level = "info" if pnl >= 0 else "warn"
            self.send_alert(
                f"{label}: SELL {qty}x {symbol} @ ${price:.2f} | "
                f"P&L ${pnl:+.2f} | Peak ${peak:.2f} | Reinvesting ${proceeds:.2f}",
                level=level, symbol=symbol,
            )
            # Clear any after-hours stop flag for this symbol now that we've sold
            self._ah_stops_placed.discard(symbol)
            # Update capital high-water mark (the ladder)
            self._update_capital_hwm()

        except Exception as e:
            self.send_alert(f"SELL ERROR {symbol}: {e}", level="alert", symbol=symbol)
            # Restore holding so we can retry
            with self.lock:
                self.current_holdings[symbol] = holding
                self._peak_prices[symbol]     = peak

    # -------------------------------
    # Alerts + Pushbullet
    # -------------------------------

    def send_alert(self, message: str, level: str = "info", symbol: str = ""):
        """
        Tiered alert routing:
          info   → print + Pushbullet
          warn   → print + Pushbullet + Pushover (normal)
          alert  → print + Pushbullet + Pushover (EMERGENCY, breaks DND) + Twilio call
          rocket → print + Pushbullet + Pushover (HIGH, bypasses quiet hours)
        """
        print(f"[{level.upper()}] {message}")

        if self.alert_callback:
            try:
                self.alert_callback(message, level, symbol)
            except Exception:
                pass

        if self.pb:
            try:
                self.pb.push_note(f"Alien AI Trader [{level.upper()}]", message)
            except Exception as e:
                err_txt = str(e)
                print(f"[Pushbullet] send failed: {err_txt}")
                # Pushbullet may return plan-gate errors (e.g. pushbullet_pro_required).
                # Disable further PB sends to avoid log spam while keeping trading alive.
                if "pushbullet_pro_required" in err_txt.lower() or "pro is required" in err_txt.lower():
                    self._pb_disabled_reason = "Pushbullet API call requires Pro for this account"
                    self.pb = None
                    print("[Pushbullet] Disabled further Pushbullet sends for this session: "
                          f"{self._pb_disabled_reason}. Use Pushover or upgrade Pushbullet plan.")

        title = f"Alien AI Trader — {symbol or level.upper()}"
        if level == "warn":
            try:
                self._send_pushover(title=title, message=message, priority=0)
            except Exception as e:
                print(f"[Pushover] send failed: {e}")
        elif level == "alert":
            try:
                self._send_pushover(title=f"CRASH ALERT: {symbol or 'PORTFOLIO'}",
                                    message=message, priority=2, sound="siren")
            except Exception as e:
                print(f"[Pushover] send failed: {e}")
            try:
                self._send_twilio_call(message)
            except Exception as e:
                print(f"[Twilio] call failed: {e}")
        elif level == "rocket":
            try:
                self._send_pushover(title=title, message=message, priority=1, sound="cashregister")
            except Exception as e:
                print(f"[Pushover] send failed: {e}")

        # In integrated mode, dashboard.py injects alert_callback which already
        # writes to the same notifications stream. Skip HTTP mirror to avoid
        # duplicate alert rows in the Alerts tab.
        if self.dashboard_base_url and not self.alert_callback:
            try:
                requests.post(
                    f"{self.dashboard_base_url}/api/notifications",
                    json={"level": level, "message": message, "symbol": symbol},
                    headers=self._internal_headers,
                    timeout=5,
                )
            except Exception:
                pass

    def emit_activity(self, action: str, message: str, symbol: str = "", level: str = "info") -> None:
        """Emit lightweight activity events (scan/hold/etc.) for the live feed."""
        cb = self.activity_callback
        if not cb:
            return
        try:
            cb(action=action, message=message, symbol=symbol, level=level)
        except Exception:
            pass

    # -------------------------------
    # Heartbeat to dashboard
    # -------------------------------

    def _maybe_heartbeat(self, message: str = "ok"):
        if not self.dashboard_base_url:
            return
        now = time.time()
        if now - self._last_heartbeat < self.heartbeat_every:
            return
        self._last_heartbeat = now

        with self.lock:
            positions = {
                sym: {"price": h["price"], "qty": h["qty"]}
                for sym, h in self.current_holdings.items()
            }
            signals_snapshot = dict(self._symbol_signals)
            invested = sum(h["qty"] * h["price"] for h in self.current_holdings.values())

        payload = {
            "running":      self.running,
            "mode":         self.trading_mode,
            "stock_list":   self.stock_list,
            "profit":       round(self.profit, 4),
            "positions":    positions,
            "signals":      signals_snapshot,
            "message":      message,
            "poll_seconds": self.poll_seconds,
            "trade_count":  len(self.trade_log),
            "capital": {
                "initial":   round(self.initial_capital, 2),
                "available": round(self._available_capital, 2),
                "invested":  round(invested, 2),
                "total":     round(self._available_capital + invested, 2),
                "mode":      "pool" if self.initial_capital > 0 else "fixed_qty",
            },
            "trailing_stop_pct": round(self.trailing_stop_pct * 100, 2),
            "loss_threshold":    round(self.loss_threshold * 100, 2),
            "scan_all_market":   self.scan_all_market,
            "max_positions":     self.max_positions,
            "min_positions":     self.min_positions,
            "risk_settings": {
                "risk_per_trade_pct": self.risk_per_trade_pct,
                "max_position_pct":   self.max_position_pct,
                "risk_per_trade_usd": self.risk_per_trade_usd,
                "rsi_buy_max":        self.rsi_buy_max,
                "rsi_sell_min":       self.rsi_sell_min,
                "sma_spread_min":     self.sma_spread_min,
                "rocket_breakout_enabled": self.rocket_breakout_enabled,
                "rocket_breakout_min_day_change_pct": self.rocket_breakout_min_day_change_pct,
                "rocket_breakout_volume_mult": self.rocket_breakout_volume_mult,
                "rocket_breakout_min_avg_volume": self.rocket_breakout_min_avg_volume,
                "rocket_breakout_max_above_sma20_pct": self.rocket_breakout_max_above_sma20_pct,
                "rocket_breakout_lookback_bars": self.rocket_breakout_lookback_bars,
                "forecast_exit_enabled": self.forecast_exit_enabled,
            },
            "live_trading_enabled": self.live_enabled,
            "trading_mode":         self.trading_mode,
        }
        try:
            requests.post(
                f"{self.dashboard_base_url}{self.heartbeat_path}",
                json=payload,
                headers=self._internal_headers,
                timeout=5,
            )
        except Exception:
            pass

    # -------------------------------
    # ROI / session reporting (from growth_forecaster pattern)
    # -------------------------------

    def session_roi(self) -> Dict[str, Any]:
        """Returns a session P&L / ROI snapshot including risk settings."""
        invested     = sum(h["qty"] * h["price"] for h in self.current_holdings.values())
        total_value  = self._available_capital + invested
        roi_pct      = 0.0
        if self.initial_capital > 0:
            roi_pct = round((total_value - self.initial_capital) / self.initial_capital * 100, 2)
        return {
            "session_profit_usd":  round(self.profit, 4),
            "open_positions":      len(self.current_holdings),
            "total_trades":        len(self.trade_log),
            "mode":                self.trading_mode,
            "live_enabled":        self.live_enabled,
            "available_capital":   round(self._available_capital, 2),
            "invested":            round(invested, 2),
            "total_value":         round(total_value, 2),
            "initial_capital":     round(self.initial_capital, 2),
            "roi_pct":             roi_pct,
            "capital_hwm":         round(self._capital_hwm, 2),
            "risk_per_trade_pct":  self.risk_per_trade_pct,
            "max_position_pct":    self.max_position_pct,
            "min_positions":       self.min_positions,
            "risk_per_trade_usd":  self.risk_per_trade_usd,
            "rsi_buy_max":         self.rsi_buy_max,
            "rsi_sell_min":        self.rsi_sell_min,
        }

# Built by Troy Walker of T-Dub's Apps — 2026-04-22

