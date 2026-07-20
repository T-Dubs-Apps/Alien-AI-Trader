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
        if df is None or df.empty or 'c' not in df or 'v' not in df:
            return None
        pv = (df['c'].astype(float) * df['v'].astype(float)).sum()
        v = df['v'].astype(float).sum()
        if v == 0:
            return None
        return float(pv / v)

    def __init__(self, stock_list: List[str], mode: str = "AI", alert_callback=None):
        self.stock_list = [s.strip().upper() for s in stock_list if s and s.strip()]
        self.mode = mode
        self.alert_callback = alert_callback

        self.running = False
        self.lock = threading.Lock()

        self.current_holdings: Dict[str, Dict[str, Any]] = {}
        self.trade_log: List[Dict[str, Any]] = []
        self.profit = 0.0
        self._reconciled = False

        self._session_start_equity: Optional[float] = None
        self._symbol_signals: Dict[str, Dict[str, Any]] = {}

        self.auto_trade = True

        self.loss_threshold    = float(os.environ.get("LOSS_THRESHOLD",    "0.05"))
        self.trailing_stop_pct = float(os.environ.get("TRAILING_STOP_PCT", "0.03"))
        self.forecast_exit_enabled = os.environ.get("FORECAST_EXIT_ENABLED", "true").lower() == "true"
        self.poll_seconds = int(os.environ.get("POLL_SECONDS", "15"))
        self.max_workers = int(os.environ.get("SCAN_WORKERS", "8"))

        self.initial_capital    = float(os.environ.get("INITIAL_CAPITAL", "0"))
        self._available_capital = self.initial_capital

        self.max_positions = int(os.environ.get("MAX_POSITIONS", "5"))

        self.risk_per_trade_pct  = float(os.environ.get("RISK_PER_TRADE_PCT",  "2.0"))
        self.max_position_pct    = float(os.environ.get("MAX_POSITION_PCT",    "20.0"))
        self.min_positions       = int(os.environ.get("MIN_POSITIONS",         "5"))
        self.risk_per_trade_usd  = float(os.environ.get("RISK_PER_TRADE_USD",  "0"))

        # Adjusted default RSI ceiling to 65.0 to allow entries on momentum setups
        self.rsi_buy_max    = float(os.environ.get("RSI_BUY_MAX",    "65.0"))
        self.rsi_sell_min   = float(os.environ.get("RSI_SELL_MIN",   "70.0"))
        self.sma_spread_min = float(os.environ.get("SMA_SPREAD_MIN", "0.1"))

        self.scan_all_market         = os.environ.get("SCAN_ALL_MARKET", "false").lower() == "true"
        self._market_scan_candidates = int(os.environ.get("MARKET_SCAN_CANDIDATES", "30"))

        self._peak_prices: Dict[str, float] = {}

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

        self.pushover_token = os.environ.get("PUSHOVER_TOKEN", "")
        self.pushover_user  = os.environ.get("PUSHOVER_USER",  "")

        twilio_sid    = os.environ.get("TWILIO_ACCOUNT_SID", "")
        twilio_token  = os.environ.get("TWILIO_AUTH_TOKEN",  "")
        self.twilio_from   = os.environ.get("TWILIO_FROM_NUMBER", "")
        self.twilio_to     = os.environ.get("TWILIO_TO_NUMBER",   "")
        self.twilio_client = TwilioClient(twilio_sid, twilio_token) if (TwilioClient and twilio_sid and twilio_token) else None

        self.afterhours_drop_pct  = float(os.environ.get("AFTERHOURS_DROP_PCT",  "3.0")) / 100.0
        self.rocket_alert_pct     = float(os.environ.get("ROCKET_ALERT_PCT",     "5.0")) / 100.0
        self._ah_stops_placed: set = set()
        self._ah_last_prices: Dict[str, float] = {}

        self._capital_hwm = self.initial_capital

        self.dashboard_base_url = (
            os.environ.get("DASHBOARD_BASE_URL") or
            os.environ.get("DASHBOARD_URL") or ""
        ).rstrip("/")
        self.heartbeat_path = os.environ.get("HEARTBEAT_PATH", "/api/worker/heartbeat")
        self.heartbeat_every = int(os.environ.get("HEARTBEAT_EVERY_SECONDS", "10"))
        self._last_heartbeat = 0

        self.max_trades_per_hour = int(os.environ.get("MAX_TRADES_PER_HOUR", "30"))
        self._trade_timestamps: List[float] = []

        self._price_cache: Dict[str, Tuple[Optional[float], float]] = {}
        self._cache_ttl = int(os.environ.get("PRICE_CACHE_TTL", "8"))

        self._bars_cache: Dict[str, Tuple[Optional[pd.DataFrame], float]] = {}
        self._bars_cache_ttl = int(os.environ.get("BARS_CACHE_TTL", "1800"))

        self._market_candidates_cache: Tuple[List[str], float] = ([], 0.0)
        self._market_candidates_ttl = int(os.environ.get("MARKET_CANDIDATES_TTL", "600"))

        self.portfolio_stop_loss   = float(os.environ.get("PORTFOLIO_STOP_LOSS",   "0"))
        self.portfolio_stop_buffer = float(os.environ.get("PORTFOLIO_STOP_BUFFER", "200"))
        self.shield_enabled        = True
        self.shield_triggered      = False

        self.min_hold_seconds = int(os.environ.get("MIN_HOLD_SECONDS", "21540"))

    def _check_portfolio_shield(self):
        try:
            total = self._available_capital
            for sym, h in list(self.current_holdings.items()):
                cached_price, cached_at = self._price_cache.get(sym, (h["price"], 0))
                use_price = cached_price if (time.time() - cached_at) < 60 else h["price"]
                total += use_price * h["qty"]

            if total <= 0:
                return

            if total > self._capital_hwm:
                self._capital_hwm = total

            if not self.shield_triggered:
                if total <= self.portfolio_stop_loss:
                    self.shield_triggered = True
                    self.auto_trade = False
                    msg = (
                        f"🛡️ SAFETY SHIELD TRIGGERED! Portfolio ${total:,.2f} "
                        f"dropped to/below threshold ${self.portfolio_stop_loss:,.2f}. "
                        f"ALL new buys PAUSED."
                    )
                    self.send_alert(msg, level="alert")
            else:
                recovery_target = self.portfolio_stop_loss + self.portfolio_stop_buffer
                if total >= recovery_target:
                    self.shield_triggered = False
                    self.auto_trade = True
                    msg = f"✅ SAFETY SHIELD RESET — Portfolio recovered to ${total:,.2f}."
                    self.send_alert(msg, level="rocket")
        except Exception as e:
            self.send_alert(f"[shield] check error: {e}", level="warn")

    def start(self):
        self.running = True
        if not self._reconciled:
            self._reconcile_from_alpaca()
            self._reconciled = True
        t = threading.Thread(target=self._afterhours_loop, daemon=True, name="afterhours-watcher")
        t.start()

    def stop(self):
        self.running = False

    def _reconcile_from_alpaca(self):
        try:
            positions = self.api.list_positions()
        except Exception as e:
            self.send_alert(f"Startup reconcile skipped — could not read Alpaca positions: {e}", level="warn")
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
                    self._peak_prices[symbol] = max(entry, current)
                    seeded += 1
                except Exception:
                    continue

        if seeded:
            self.send_alert(f"Reconciled {seeded} open position(s) from Alpaca on startup.", level="info")

    def run_forever(self):
        self.start()
        while self.running:
            self._poll_live_settings()
            if self.shield_enabled and self.portfolio_stop_loss > 0:
                self._check_portfolio_shield()
            self._maybe_heartbeat(message="scan-start")
            symbols = list(self.stock_list)

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
        price = self.get_live_price(symbol)
        self.evaluate(symbol, price)

    def _poll_live_settings(self):
        if not self.dashboard_base_url:
            return
        try:
            r = requests.get(f"{self.dashboard_base_url}/api/settings/trading", timeout=3)
            if r.status_code != 200:
                return
            s = r.json()
            if "auto_trade"         in s: self.auto_trade          = bool(s["auto_trade"])
            if "poll_seconds"        in s: self.poll_seconds        = max(5, int(s["poll_seconds"]))
            if "trailing_stop_pct"   in s: self.trailing_stop_pct   = max(0.001, float(s["trailing_stop_pct"]) / 100.0)
            if "loss_threshold"      in s: self.loss_threshold      = max(0.001, float(s["loss_threshold"])    / 100.0)
            if "max_trades_per_hour" in s: self.max_trades_per_hour  = max(1, int(s["max_trades_per_hour"]))
            if "scan_all_market"      in s: self.scan_all_market      = bool(s["scan_all_market"])
            if "max_positions"       in s: self.max_positions        = max(1, int(s["max_positions"]))
            if "initial_capital"     in s:
                new_cap = max(0.0, float(s["initial_capital"]))
                if new_cap != self.initial_capital:
                    self.initial_capital = new_cap
                    if not self.current_holdings:
                        self._available_capital = new_cap
            if "risk_per_trade_pct"  in s: self.risk_per_trade_pct  = max(0.1,  float(s["risk_per_trade_pct"]))
            if "max_position_pct"    in s: self.max_position_pct    = max(1.0,  float(s["max_position_pct"]))
            if "min_positions"       in s: self.min_positions       = max(1,    int(s["min_positions"]))
            if "risk_per_trade_usd"  in s: self.risk_per_trade_usd  = max(0.0,  float(s["risk_per_trade_usd"]))
            if "rsi_buy_max"         in s: self.rsi_buy_max         = max(20.0, float(s["rsi_buy_max"]))
            if "rsi_sell_min"        in s: self.rsi_sell_min        = max(50.0, float(s["rsi_sell_min"]))
            if "sma_spread_min"      in s: self.sma_spread_min      = max(0.0,  float(s["sma_spread_min"]))
            if "forecast_exit_enabled" in s: self.forecast_exit_enabled = bool(s["forecast_exit_enabled"])
            if "portfolio_stop_loss"   in s: self.portfolio_stop_loss   = max(0.0, float(s["portfolio_stop_loss"]))
            if "portfolio_stop_buffer" in s: self.portfolio_stop_buffer = max(0.0, float(s["portfolio_stop_buffer"]))
            if "shield_enabled"        in s: self.shield_enabled         = bool(s["shield_enabled"])
            if "min_hold_seconds"      in s: self.min_hold_seconds       = max(0, int(s["min_hold_seconds"]))
        except Exception:
            pass

    def _get_market_candidates(self, max_candidates: int = 30) -> List[str]:
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

        with self.lock:
            invested = sum(h["qty"] * h["price"] for h in self.current_holdings.values())
        total_capital = self._available_capital + invested
        if total_capital > 0 and self.initial_capital > 0:
            max_price = max(2.0, total_capital / max(self.min_positions, 1))
            min_price = 0.50
        else:
            max_price = 1000.0
            min_price = 2.0
        max_price = min(max_price, 5000.0)

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

    def _is_market_open(self) -> bool:
        try:
            clock = self.api.get_clock()
            return bool(clock.is_open)
        except Exception:
            return False

    def _afterhours_loop(self):
        CHECK_INTERVAL_OPEN   = 60
        CHECK_INTERVAL_CLOSED = 300
        while True:
            time.sleep(5)
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

                    prev = self._ah_last_prices.get(symbol, bought_price)
                    climb_since_last = (price - prev) / prev if prev > 0 else 0
                    if climb_since_last >= self.rocket_alert_pct:
                        self._send_pushover(
                            title=f"ROCKET {symbol} +{climb_since_last*100:.1f}%",
                            message=f"{symbol} surged {climb_since_last*100:.1f}% to ${price:.2f}!",
                            priority=1,
                            sound="cashregister",
                        )
                    self._ah_last_prices[symbol] = price

                    if not market_open and change <= -self.afterhours_drop_pct:
                        if symbol not in self._ah_stops_placed:
                            stop_price = round(price * 0.995, 2)
                            self._place_protective_stop(symbol, qty, stop_price)
                            self._ah_stops_placed.add(symbol)
                            self._send_pushover(
                                title=f"CRASH ALERT: {symbol} {change*100:.1f}%",
                                message=f"{symbol} is down {change*100:.1f}% after hours.",
                                priority=2,
                                sound="siren",
                            )
                            self._send_twilio_call(
                                f"Alien AI Trader emergency. {symbol} is crashing after hours."
                            )
                    elif change > -self.afterhours_drop_pct and symbol in self._ah_stops_placed:
                        self._ah_stops_placed.discard(symbol)

                interval = CHECK_INTERVAL_OPEN if market_open else CHECK_INTERVAL_CLOSED
            except Exception as exc:
                interval = 60
                print(f"[afterhours-watcher] error: {exc}")
            time.sleep(interval)

    def _place_protective_stop(self, symbol: str, qty: int, stop_price: float):
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

    def _send_pushover(self, title: str, message: str, priority: int = 0, sound: str = "pushover"):
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
            payload["retry"]  = 60
            payload["expire"] = 3600
        try:
            requests.post("https://api.pushover.net/1/messages.json", data=payload, timeout=8)
        except Exception as e:
            print(f"[pushover] send failed: {e}")

    def _send_twilio_call(self, spoken_message: str):
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

    def _update_capital_hwm(self):
        if self.initial_capital <= 0:
            return
        with self.lock:
            invested = sum(h["qty"] * h["price"] for h in self.current_holdings.values())
            total    = self._available_capital + invested
        if total > self._capital_hwm * 1.005:
            self._capital_hwm = total
            self._send_pushover(
                title=f"New All-Time High: ${total:.2f}",
                message=f"Your capital pool just hit a new record of ${total:.2f}!",
                priority=1,
                sound="cashregister",
            )
            self.send_alert(f"NEW ALL-TIME HIGH: portfolio total = ${total:.2f}", level="info")

    def get_live_price(self, symbol: str) -> Optional[float]:
        cached = self._price_cache.get(symbol)
        if cached and (time.time() - cached[1]) < self._cache_ttl:
            return cached[0]

        price = None
        try:
            t = self.api.get_latest_trade(symbol)
            price = float(t.price)
        except Exception:
            try:
                data, _ = self.ts.get_quote_endpoint(symbol)
                price = float(data["05. price"])
            except Exception:
                pass

        self._price_cache[symbol] = (price, time.time())
        return price

    def _get_bars_df(self, symbol: str, limit: int = 100) -> Optional[pd.DataFrame]:
        cached = self._bars_cache.get(symbol)
        if cached and (time.time() - cached[1]) < self._bars_cache_ttl:
            return cached[0]

        df = None
        try:
            bars = self.api.get_bars(symbol, TimeFrame.Day, limit=limit)
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
                bars_h = self.api.get_bars(symbol, TimeFrame.Hour, limit=limit)
                bar_list_h = list(bars_h) if bars_h else []
                if bar_list_h:
                    df = pd.DataFrame([{
                        "c": float(b.c),
                        "v": float(b.v),
                        "h": float(b.h),
                        "l": float(b.l),
                        "o": float(b.o),
                    } for b in bar_list_h])
        except Exception as e:
            print(f"[ENGINE] _get_bars_df({symbol}) error: {e}")

        self._bars_cache[symbol] = (df, time.time())
        return df

    def _calc_rsi(self, closes: pd.Series, period: int = 14) -> Optional[float]:
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
        df = self._get_bars_df(symbol)
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
            "verdict": "HOLD"
        }
        if df is None or df.empty:
            return signal

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
            fc = get_forecast(closes, periods_ahead=5)
            signal["forecast"]           = fc
            signal["forecast_direction"] = fc["forecast_direction"]
            signal["forecast_phase"]     = fc["forecast_phase"]
            signal["predicted_price"]    = fc.get("predicted_price")
        except Exception:
            pass

        # FIXED SIGNAL LOGIC: High probability momentum scoring instead of impossible strict checks
        if rsi is not None and macd is not None and macd_signal is not None:
            # Flexible Golden Cross or Momentum condition
            golden_cross = (sma20 and sma50 and sma20 > sma50)
            macd_bullish = macd > macd_signal
            rsi_valid = rsi < self.rsi_buy_max
            forecast_up = signal.get("forecast_direction") in ["up", "neutral"]

            # BUY Trigger: MACD Bullish + RSI in Range + (Golden Cross OR Bullish Forecast)
            if macd_bullish and rsi_valid and (golden_cross or forecast_up):
                signal["verdict"] = "BUY"
            elif (sma20 and sma50 and sma20 < sma50) or rsi > self.rsi_sell_min or macd < macd_signal:
                signal["verdict"] = "SELL"

        return signal

    def evaluate(self, symbol: str, price: Optional[float]):
        if price is None:
            return

        signal = self._get_signal(symbol, price)
        sentiment = get_symbol_sentiment(symbol)
        signal["sentiment_score"] = sentiment["sentiment_score"]
        signal["sentiment_headlines"] = sentiment["headlines"]

        if signal["verdict"] == "BUY" and sentiment["sentiment_score"] < -0.2:
            signal["verdict"] = "HOLD"
            signal["sentiment_blocked"] = True

        if self.mode == "AI_MODEL":
            verdict = ai_predict_signal(signal)
            signal["verdict"] = verdict

        with self.lock:
            self._symbol_signals[symbol] = signal
            holding = self.current_holdings.get(symbol)

        if self.mode != "AI":
            return

        if not holding:
            if signal["verdict"] == "BUY" and len(self.current_holdings) < self.max_positions:
                if not self.auto_trade:
                    signal["verdict"] = "BUY_BLOCKED"
                    print(f"[ENGINE] {symbol} BUY signal — auto-trade is OFF, skipping.")
                    return

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
                    return

                if self.initial_capital > 0:
                    if self._available_capital >= price:
                        self.buy(symbol, price, signal=signal)
                else:
                    self.buy(symbol, price, signal=signal)
        else:
            bought_price    = holding["price"]
            change_from_buy = (price - bought_price) / bought_price

            with self.lock:
                peak = self._peak_prices.get(symbol, bought_price)
                if price > peak:
                    self._peak_prices[symbol] = price
                    peak = price

            drop_from_peak = (peak - price) / peak if peak > 0 else 0

            _hold_secs = time.time() - holding.get("time", time.time())
            _min_hold_ok = self.min_hold_seconds <= 0 or _hold_secs >= self.min_hold_seconds

            if drop_from_peak >= self.trailing_stop_pct:
                if not self.auto_trade:
                    print(f"[ENGINE] {symbol} TRAILING STOP triggered — auto-trade is OFF, skipping sell.")
                    return
                self.send_alert(f"TRAILING STOP: {symbol} fell {drop_from_peak*100:.1f}% from peak", level="warn", symbol=symbol)
                self.sell(symbol, price, reason="trailing_stop")

            elif change_from_buy <= -self.loss_threshold:
                self.send_alert(f"STOP-LOSS: {symbol} down {change_from_buy*100:.1f}% from entry.", level="alert", symbol=symbol)
                self.sell(symbol, price, reason="stop_loss")

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
                self.send_alert(f"FORECAST EXIT: {symbol} momentum peaked", level="warn", symbol=symbol)
                self.sell(symbol, price, reason="forecast_exit")

            elif signal["verdict"] == "SELL" and change_from_buy > 0 and _min_hold_ok:
                self.sell(symbol, price, reason="signal_exit")

    def should_buy(self, symbol: str, price: float) -> bool:
        signal = self._get_signal(symbol, price)
        return signal["verdict"] == "BUY"

    def _throttle_trades(self) -> bool:
        now = time.time()
        one_hour_ago = now - 3600
        self._trade_timestamps = [t for t in self._trade_timestamps if t >= one_hour_ago]
        return len(self._trade_timestamps) < self.max_trades_per_hour

    def buy(self, symbol: str, price: float, signal: Optional[Dict[str, Any]] = None):
        if not self._throttle_trades():
            self.send_alert(f"Trade throttled (max/hour). Skipped buy for {symbol}.", level="warn")
            return

        if self.initial_capital > 0:
            total_capital = self._available_capital + sum(
                h["qty"] * h["price"] for h in self.current_holdings.values()
            )

            effective_slots = max(self.max_positions, self.min_positions)
            open_slots      = max(1, effective_slots - len(self.current_holdings))
            slot_alloc      = self._available_capital / open_slots

            streak_risk = adjust_risk_for_streak(self.risk_per_trade_pct, self.trade_log)

            df = self._get_bars_df(symbol, limit=21)
            closes = df["c"].astype(float) if df is not None and not df.empty else None
            vol_risk = streak_risk
            if closes is not None:
                vol = calc_volatility(closes)
                vol_risk = adjust_risk_for_volatility(streak_risk, vol)

            risk_alloc = total_capital * (vol_risk / 100.0)
            max_alloc  = total_capital * (self.max_position_pct  / 100.0)

            if self.risk_per_trade_usd > 0:
                risk_alloc = min(risk_alloc, self.risk_per_trade_usd)

            alloc = min(slot_alloc, risk_alloc, max_alloc)
            alloc = min(alloc, self._available_capital)

            qty  = max(1, int(alloc / price))
            cost = qty * price

            if price > self._available_capital:
                self.send_alert(
                    f"Insufficient capital (${self._available_capital:.2f}) to buy even 1x {symbol} @ ${price:.2f} — skipping.",
                    level="warn",
                )
                return

            while cost > self._available_capital and qty > 1:
                qty  -= 1
                cost  = qty * price

            if qty < 1:
                self.send_alert(f"Position sizing produced qty=0 for {symbol} @ ${price:.2f}. Skipping.", level="warn")
                return

            self.send_alert(
                f"SIZING: {symbol} @ ${price:.2f} | buying {qty}x (${cost:.2f})",
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
                self._peak_prices[symbol] = price
                self._trade_timestamps.append(time.time())
                self.trade_log.append({
                    "action": "BUY", "symbol": symbol, "price": price,
                    "qty": qty, "cost": cost, "time": time.time(),
                    "rsi": signal.get("rsi") if signal else None,
                })

            msg = f"BUY {qty}x {symbol} @ ${price:.2f} (cost ${cost:.2f})"
            if signal:
                msg += f" | RSI={signal.get('rsi')}"
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
                    self._available_capital += proceeds
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
                f"{label}: SELL {qty}x {symbol} @ ${price:.2f} | P&L ${pnl:+.2f}",
                level=level, symbol=symbol,
            )
            self._ah_stops_placed.discard(symbol)
            self._update_capital_hwm()

        except Exception as e:
            self.send_alert(f"SELL ERROR {symbol}: {e}", level="alert", symbol=symbol)
            with self.lock:
                self.current_holdings[symbol] = holding
                self._peak_prices[symbol]     = peak

    def send_alert(self, message: str, level: str = "info", symbol: str = ""):
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
                print(f"[Pushbullet] send failed: {e}")

        title = f"Alien AI Trader — {symbol or level.upper()}"
        if level == "warn":
            try:
                self._send_pushover(title=title, message=message, priority=0)
            except Exception as e:
                print(f"[Pushover] send failed: {e}")
        elif level == "alert":
            try:
                self._send_pushover(title=f"CRASH ALERT: {symbol or 'PORTFOLIO'}", message=message, priority=2, sound="siren")
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

        if self.dashboard_base_url:
            try:
                requests.post(
                    f"{self.dashboard_base_url}/api/notifications",
                    json={"level": level, "message": message, "symbol": symbol},
                    timeout=5,
                )
            except Exception:
                pass

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
                "forecast_exit_enabled": self.forecast_exit_enabled,
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

    def session_roi(self) -> Dict[str, Any]:
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
            "roi_pct":              roi_pct,
            "capital_hwm":         round(self._capital_hwm, 2),
            "risk_per_trade_pct":  self.risk_per_trade_pct,
            "max_position_pct":    self.max_position_pct,
            "min_positions":       self.min_positions,
            "risk_per_trade_usd":  self.risk_per_trade_usd,
            "rsi_buy_max":         self.rsi_buy_max,
            "rsi_sell_min":        self.rsi_sell_min,
        }

# Built by Troy Walker of T-Dub's Apps — 2026
