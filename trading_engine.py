import os
import time
import threading
import requests
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
    """
    TradingEngine — upgraded for concurrent scanning, RSI + SMA crossover signals,
    ROI tracking, price caching, and faster real-time heartbeats.

    - Secrets are read from environment variables (Render env vars).
    - Live trading requires explicit enablement (TRADING_MODE=live AND LIVE_TRADING_ENABLED=true).
    - Heartbeats are posted to your dashboard web service with per-symbol signal data.
    """

    def __init__(self, stock_list: List[str], mode: str = "AI", alert_callback=None):
        self.stock_list = [s.strip().upper() for s in stock_list if s and s.strip()]
        self.mode = mode
        self.alert_callback = alert_callback

        self.running = False
        self.lock = threading.Lock()

        self.current_holdings: Dict[str, Dict[str, Any]] = {}
        self.trade_log: List[Dict[str, Any]] = []
        self.profit = 0.0

        # ROI tracking (inspired by growth_forecaster pattern)
        self._session_start_equity: Optional[float] = None
        self._symbol_signals: Dict[str, Dict[str, Any]] = {}   # per-symbol last signal data

        # ── Risk controls (live-updateable from dashboard UI) ──
        self.loss_threshold    = float(os.environ.get("LOSS_THRESHOLD",    "0.05"))  # 5% absolute floor
        self.trailing_stop_pct = float(os.environ.get("TRAILING_STOP_PCT", "0.03"))  # 3% drop from peak

        # Scan interval (live-configurable from UI)
        self.poll_seconds = int(os.environ.get("POLL_SECONDS", "15"))

        # Max parallel workers
        self.max_workers = int(os.environ.get("SCAN_WORKERS", "8"))

        # ── Capital pool (compound reinvestment mode) ──
        # Set INITIAL_CAPITAL=100 to start with $100 and auto-reinvest every sell.
        # 0 = legacy fixed ORDER_QTY per trade.
        self.initial_capital    = float(os.environ.get("INITIAL_CAPITAL", "0"))
        self._available_capital = self.initial_capital

        # Max simultaneous open positions
        self.max_positions = int(os.environ.get("MAX_POSITIONS", "5"))

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

        # ── Full-market scan ──
        self.scan_all_market         = os.environ.get("SCAN_ALL_MARKET", "false").lower() == "true"
        self._market_scan_candidates = int(os.environ.get("MARKET_SCAN_CANDIDATES", "30"))

        # Trailing-stop high-water marks: {symbol: highest_price_since_buy}
        self._peak_prices: Dict[str, float] = {}

        # Hard safety gate for live trading
        self.trading_mode = os.environ.get("TRADING_MODE", "paper").lower()
        self.live_enabled = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() == "true"

        alpaca_key = os.environ.get("ALPACA_KEY")
        alpaca_secret = os.environ.get("ALPACA_SECRET")
        alpha_vantage_key = os.environ.get("ALPHA_VANTAGE_KEY")
        pushbullet_token = os.environ.get("PUSHBULLET_TOKEN", "")

        if not alpaca_key or not alpaca_secret:
            raise RuntimeError("Missing ALPACA_KEY / ALPACA_SECRET env vars.")
        if not alpha_vantage_key:
            raise RuntimeError("Missing ALPHA_VANTAGE_KEY env var.")

        base_url = "https://paper-api.alpaca.markets"
        if self.trading_mode == "live":
            if not self.live_enabled:
                raise RuntimeError("Live trading requested but LIVE_TRADING_ENABLED is not true.")
            base_url = "https://api.alpaca.markets"

        self.api = REST(alpaca_key, alpaca_secret, base_url=base_url)
        self.ts = TimeSeries(key=alpha_vantage_key, output_format="json")

        self.pb = Pushbullet(pushbullet_token) if pushbullet_token else None

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

        # Dashboard heartbeat (optional)
        # Accept either DASHBOARD_BASE_URL or DASHBOARD_URL for flexibility
        self.dashboard_base_url = (
            os.environ.get("DASHBOARD_BASE_URL") or
            os.environ.get("DASHBOARD_URL") or ""
        ).rstrip("/")
        self.heartbeat_path = os.environ.get("HEARTBEAT_PATH", "/api/worker/heartbeat")
        self.heartbeat_every = int(os.environ.get("HEARTBEAT_EVERY_SECONDS", "10"))
        self._last_heartbeat = 0

        # Operational guardrails
        self.max_trades_per_hour = int(os.environ.get("MAX_TRADES_PER_HOUR", "30"))
        self._trade_timestamps: List[float] = []

        # Price cache: {symbol: (price, fetched_at_epoch)}
        self._price_cache: Dict[str, Tuple[Optional[float], float]] = {}
        self._cache_ttl = int(os.environ.get("PRICE_CACHE_TTL", "8"))   # seconds

    def start(self):
        self.running = True
        # Start after-hours background watcher on its own daemon thread
        t = threading.Thread(target=self._afterhours_loop, daemon=True, name="afterhours-watcher")
        t.start()

    def stop(self):
        self.running = False

    def run_forever(self):
        """
        Main loop — polls live settings, optionally extends the scan queue with
        full-market momentum candidates, then scans all symbols concurrently.
        """
        self.start()
        while self.running:
            # Pick up live setting changes pushed from the dashboard UI
            self._poll_live_settings()
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
        self.evaluate(symbol, price)

    # -------------------------------
    # Live settings poll
    # -------------------------------

    def _poll_live_settings(self):
        """
        Fetch live trading settings from the dashboard's /api/settings/trading.
        Lets the UI change scan speed, trailing stop %, etc. without restarting.
        """
        if not self.dashboard_base_url:
            return
        try:
            r = requests.get(f"{self.dashboard_base_url}/api/settings/trading", timeout=3)
            if r.status_code != 200:
                return
            s = r.json()
            if "poll_seconds"        in s: self.poll_seconds        = max(5, int(s["poll_seconds"]))
            if "trailing_stop_pct"   in s: self.trailing_stop_pct   = max(0.001, float(s["trailing_stop_pct"]) / 100.0)
            if "loss_threshold"      in s: self.loss_threshold       = max(0.001, float(s["loss_threshold"])    / 100.0)
            if "max_trades_per_hour" in s: self.max_trades_per_hour  = max(1, int(s["max_trades_per_hour"]))
            if "scan_all_market"     in s: self.scan_all_market      = bool(s["scan_all_market"])
            if "max_positions"       in s: self.max_positions        = max(1, int(s["max_positions"]))
            # Live-updatable position sizing / risk knobs from dashboard settings box
            if "initial_capital"     in s:
                new_cap = max(0.0, float(s["initial_capital"]))
                if new_cap != self.initial_capital:
                    self.initial_capital = new_cap
                    if not self.current_holdings:   # only reset if no open positions
                        self._available_capital = new_cap
            if "risk_per_trade_pct"  in s: self.risk_per_trade_pct  = max(0.1,  float(s["risk_per_trade_pct"]))
            if "max_position_pct"    in s: self.max_position_pct     = max(1.0,  float(s["max_position_pct"]))
            if "min_positions"       in s: self.min_positions        = max(1,    int(s["min_positions"]))
            if "risk_per_trade_usd"  in s: self.risk_per_trade_usd   = max(0.0,  float(s["risk_per_trade_usd"]))
            if "rsi_buy_max"         in s: self.rsi_buy_max          = max(20.0, float(s["rsi_buy_max"]))
            if "rsi_sell_min"        in s: self.rsi_sell_min         = max(50.0, float(s["rsi_sell_min"]))
            if "sma_spread_min"      in s: self.sma_spread_min       = max(0.0,  float(s["sma_spread_min"]))
        except Exception:
            pass

    # -------------------------------
    # Full-market momentum scanner
    # -------------------------------

    def _get_market_candidates(self, max_candidates: int = 30) -> List[str]:
        """
        Two-phase scan of the entire US equity market:
        1. Load all active tradable symbols from Alpaca.
        2. Batch-fetch snapshots (price, volume, daily change) — 1 API call per 500.
        3. Filter: price $2–$1000, daily volume > 200k, day change > +0.5%.
        4. Return the top N by daily gain % (hottest movers first).
        Already-held and watchlist symbols are excluded (evaluated separately).
        """
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

        BATCH = 500
        for i in range(0, min(len(tradable), 5000), BATCH):
            batch = tradable[i : i + BATCH]
            try:
                snaps = self.api.get_snapshots(batch)
                for sym, snap in snaps.items():
                    if snap is None or sym in already_held or sym in watchlist:
                        continue
                    lt    = getattr(snap, "latest_trade", None)
                    price = float(getattr(lt, "price", 0) or 0)
                    if price < 2.0 or price > 1000.0:
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
        return [sym for sym, _ in candidates[:max_candidates]]

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
            t = self.api.get_latest_trade(symbol)
            price = float(t.price)
        except Exception:
            # Failover to Alpha Vantage if Alpaca fails
            try:
                data, _ = self.ts.get_quote_endpoint(symbol)
                price = float(data["05. price"])
            except Exception:
                pass

        self._price_cache[symbol] = (price, time.time())
        return price

    def _get_bars_df(self, symbol: str, limit: int = 50) -> Optional[pd.DataFrame]:
        """Fetch recent 1-minute bars as a DataFrame. Returns None on error."""
        try:
            bars = self.api.get_bars(symbol, TimeFrame.Minute, limit=limit)
            if not bars:
                return None
            df = pd.DataFrame([{"c": b.c, "v": b.v} for b in bars])
            return df
        except Exception:
            return None

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
        Returns a signal dict with RSI, SMA20, SMA50, and a BUY/SELL/HOLD verdict.
        Uses SMA20/SMA50 crossover + RSI oversold/overbought filter.
        """
        df = self._get_bars_df(symbol, limit=60)
        signal: Dict[str, Any] = {
            "symbol": symbol, "price": price,
            "rsi": None, "sma20": None, "sma50": None, "verdict": "HOLD"
        }
        if df is None or df.empty:
            return signal

        closes = df["c"].astype(float)
        rsi = self._calc_rsi(closes)
        sma20 = self._calc_sma(closes, 20)
        sma50 = self._calc_sma(closes, 50)

        signal["rsi"]   = rsi
        signal["sma20"] = round(sma20, 4) if sma20 else None
        signal["sma50"] = round(sma50, 4) if sma50 else None

        # ── Signal quality filter ─────────────────────────────────────────────
        # BUY requires ALL of:
        #   1. Golden cross: SMA20 > SMA50 by at least sma_spread_min %
        #      (avoids triggering on a razor-thin, unstable crossover)
        #   2. RSI below rsi_buy_max (default 50) — catching dips, not chasing tops
        #      RSI < 30 = deeply oversold (strong signal)
        #      RSI < 50 = mild pullback (default — decent entries)
        #      RSI < 70 = original (too loose — enters near tops)
        # SELL requires ANY of:
        #   1. Death cross: SMA20 < SMA50, or
        #   2. RSI overbought above rsi_sell_min (default 70), but only while in profit
        if sma20 and sma50 and rsi is not None:
            spread_pct = abs(sma20 - sma50) / sma50 * 100
            golden_cross = sma20 > sma50 and spread_pct >= self.sma_spread_min
            death_cross  = sma20 < sma50

            if golden_cross and rsi < self.rsi_buy_max:
                signal["verdict"] = "BUY"
                signal["spread_pct"] = round(spread_pct, 3)
            elif death_cross or rsi > self.rsi_sell_min:
                signal["verdict"] = "SELL"
                signal["spread_pct"] = round(spread_pct, 3)

        return signal

    # -------------------------------
    # Decision logic
    # -------------------------------

    def evaluate(self, symbol: str, price: Optional[float]):
        if price is None:
            return

        signal = self._get_signal(symbol, price)
        with self.lock:
            self._symbol_signals[symbol] = signal
            holding = self.current_holdings.get(symbol)

        if self.mode != "AI":
            return

        if not holding:
            # Only enter if we have an open position slot
            if signal["verdict"] == "BUY" and len(self.current_holdings) < self.max_positions:
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

            # 1. Trailing stop — price fell X% below its peak since purchase → SELL
            if drop_from_peak >= self.trailing_stop_pct:
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

            # 3. Signal-based exit (death cross / RSI overbought) while in profit
            elif signal["verdict"] == "SELL" and change_from_buy > 0:
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
        if not self._throttle_trades():
            self.send_alert(f"Trade throttled (max/hour). Skipped buy for {symbol}.", level="warn")
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
            total_capital = self._available_capital + sum(
                h["qty"] * h["price"] for h in self.current_holdings.values()
            )

            # Slot-based allocation: spread across max(max_positions, min_positions) slots
            effective_slots = max(self.max_positions, self.min_positions)
            open_slots      = max(1, effective_slots - len(self.current_holdings))
            slot_alloc      = self._available_capital / open_slots

            # Risk-per-trade cap (% of total capital)
            risk_alloc = total_capital * (self.risk_per_trade_pct / 100.0)

            # Max position cap (% of total capital)
            max_alloc  = total_capital * (self.max_position_pct  / 100.0)

            # Hard USD cap (if set)
            if self.risk_per_trade_usd > 0:
                risk_alloc = min(risk_alloc, self.risk_per_trade_usd)

            # Final allocation = most conservative of slot, risk, and max caps
            alloc = min(slot_alloc, risk_alloc, max_alloc)
            alloc = min(alloc, self._available_capital)   # never exceed what we have

            qty  = max(1, int(alloc / price))
            cost = qty * price

            # Final safety: if even 1 share costs more than available capital, skip
            if price > self._available_capital:
                self.send_alert(
                    f"Insufficient capital (${self._available_capital:.2f}) to buy even "
                    f"1x {symbol} @ ${price:.2f} — skipping.",
                    level="warn",
                )
                return

            # Clamp qty so cost never exceeds available capital
            while cost > self._available_capital and qty > 1:
                qty  -= 1
                cost  = qty * price

            if qty < 1:
                self.send_alert(
                    f"Position sizing produced qty=0 for {symbol} @ ${price:.2f} "
                    f"(available: ${self._available_capital:.2f}, alloc: ${alloc:.2f}). Skipping.",
                    level="warn",
                )
                return

            self.send_alert(
                f"SIZING: {symbol} @ ${price:.2f} | "
                f"slots={open_slots} slot_alloc=${slot_alloc:.2f} "
                f"risk_alloc=${risk_alloc:.2f} max_alloc=${max_alloc:.2f} "
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
            except Exception:
                pass

        title = f"Alien AI Trader — {symbol or level.upper()}"
        if level == "warn":
            self._send_pushover(title=title, message=message, priority=0)
        elif level == "alert":
            # Emergency: repeats every 60s until you tap acknowledge on your phone
            self._send_pushover(title=f"CRASH ALERT: {symbol or 'PORTFOLIO'}",
                                message=message, priority=2, sound="siren")
            self._send_twilio_call(message)
        elif level == "rocket":
            self._send_pushover(title=title, message=message, priority=1, sound="cashregister")

        if self.dashboard_base_url:
            try:
                requests.post(
                    f"{self.dashboard_base_url}/api/notifications",
                    json={"level": level, "message": message, "symbol": symbol},
                    timeout=5,
                )
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
            },
            "live_trading_enabled": self.live_enabled,
            "trading_mode":         self.trading_mode,
        }
        try:
            requests.post(
                f"{self.dashboard_base_url}{self.heartbeat_path}",
                json=payload,
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

