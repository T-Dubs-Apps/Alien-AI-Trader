"""
╔══════════════════════════════════════════════════════════════════╗
║  ALIEN AI TRADER — Portfolio Ladder Scanner                     ║
║  Continuously scans a large portfolio (up to 61+ symbols)       ║
║  and ranks them by a composite "ladder score" to identify       ║
║  the strongest momentum candidates for the engine to trade.     ║
║                                                                  ║
║  The goal: always be climbing — buy the strongest movers,       ║
║  shed the weakest, and let profits compound upward.             ║
║                                                                  ║
║  Built by Troy Walker of T-Dub's Apps — 2026                   ║
╚══════════════════════════════════════════════════════════════════╝

HOW THE LADDER SCORE WORKS:
────────────────────────────
Each stock gets a composite score from 0-100 each scan cycle:

  RSI Score      (25 pts max) — RSI in the sweet spot (40-60 = buying dip, not chasing)
  Momentum Score (25 pts max) — SMA20 vs SMA50 crossover strength + spread %
  Volume Score   (20 pts max) — Volume surge above 20-day average (confirms moves)
  Trend Score    (15 pts max) — Price position within 52-week high/low range
  Profit Score   (15 pts max) — If held: unrealized gain bonus (let winners ride)

Stocks are ranked highest → lowest score every cycle.
The engine focuses buys on the TOP N ranked stocks and avoids the bottom.

LADDER CLIMBING LOGIC:
───────────────────────
On each cycle the scanner:
  1. Scores all symbols in parallel
  2. Sorts by score descending (the "ladder")
  3. Flags TOP_TIER (top 20%) as BUY candidates
  4. Flags BOTTOM_TIER (bottom 20%) as SELL candidates if held
  5. Publishes the ranked ladder to dashboard via heartbeat
  6. Engine only acts on TOP_TIER signals → capital flows to winners

This prevents the engine from buying weak stocks just because RSI dipped.
"""

import os
import time
import threading
import logging
from typing import Dict, List, Optional, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
#  DATA STRUCTURES
# ════════════════════════════════════════════════════════════════

@dataclass
class LadderEntry:
    symbol:         str
    score:          float = 0.0        # 0-100 composite score
    tier:           str   = "NEUTRAL"  # TOP / NEUTRAL / BOTTOM
    rsi:            Optional[float] = None
    sma20:          Optional[float] = None
    sma50:          Optional[float] = None
    price:          Optional[float] = None
    volume_ratio:   float = 1.0        # current vol / 20d avg vol
    trend_pct:      float = 0.0        # % from 52-week low
    unrealized_pct: float = 0.0        # % gain if currently held
    verdict:        str   = "HOLD"
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    last_updated:   float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol":          self.symbol,
            "score":           round(self.score, 2),
            "tier":            self.tier,
            "rsi":             self.rsi,
            "sma20":           self.sma20,
            "sma50":           self.sma50,
            "price":           self.price,
            "volume_ratio":    round(self.volume_ratio, 2),
            "trend_pct":       round(self.trend_pct, 2),
            "unrealized_pct":  round(self.unrealized_pct, 2),
            "verdict":         self.verdict,
            "score_breakdown": self.score_breakdown,
            "last_updated":    self.last_updated,
        }


# ════════════════════════════════════════════════════════════════
#  LADDER SCORER
# ════════════════════════════════════════════════════════════════

class LadderScorer:
    """
    Scores a single symbol on a 0-100 composite ladder scale.
    Higher score = stronger candidate to buy / hold.
    Lower score  = weaker candidate to avoid / sell.
    """

    # ── Score weights (must sum to 100) ──────────────────────
    W_RSI       = 25   # RSI in buying-dip sweet spot
    W_MOMENTUM  = 25   # SMA crossover strength
    W_VOLUME    = 20   # Volume surge confirmation
    W_TREND     = 15   # 52-week position
    W_PROFIT    = 15   # Unrealized gain bonus (held positions)

    def score(
        self,
        rsi: Optional[float],
        sma20: Optional[float],
        sma50: Optional[float],
        price: Optional[float],
        volume_ratio: float = 1.0,
        week52_low: Optional[float] = None,
        week52_high: Optional[float] = None,
        unrealized_pct: float = 0.0,
        rsi_buy_max: float = 55.0,
    ) -> Tuple[float, Dict[str, float]]:
        """
        Returns (total_score, breakdown_dict).
        All sub-scores are clamped 0..their weight.
        """
        breakdown = {}

        # ── RSI Score ─────────────────────────────────────────────
        # Ideal: RSI between 35-55 (dipping, not crashed, not overbought)
        # Scores drop as RSI gets too low (<25 = panic/broken) or too high (>65)
        rsi_score = 0.0
        if rsi is not None:
            if 35 <= rsi <= rsi_buy_max:
                # Perfect zone — full score, proportional within the sweet spot
                rsi_score = self.W_RSI * (1.0 - abs(rsi - 45) / 30)
            elif 25 <= rsi < 35:
                # Oversold — possible bounce but risky, partial credit
                rsi_score = self.W_RSI * 0.5 * ((rsi - 25) / 10)
            elif rsi_buy_max < rsi <= 65:
                # Approaching overbought — declining score
                rsi_score = self.W_RSI * (1.0 - (rsi - rsi_buy_max) / (65 - rsi_buy_max)) * 0.6
            else:
                rsi_score = 0.0  # Deeply oversold or overbought — skip
        breakdown["rsi"] = round(rsi_score, 2)

        # ── Momentum Score ────────────────────────────────────────
        # Golden cross + spread magnitude = confirmation of real uptrend
        momentum_score = 0.0
        if sma20 and sma50 and sma50 > 0:
            spread_pct = (sma20 - sma50) / sma50 * 100
            if spread_pct > 0:
                # Golden cross — score rises with spread strength, capped at 3%
                momentum_score = self.W_MOMENTUM * min(spread_pct / 3.0, 1.0)
            else:
                # Death cross — penalize but allow partial score for recent crosses
                momentum_score = self.W_MOMENTUM * max(0.0, 1.0 + spread_pct / 2.0) * 0.3
        breakdown["momentum"] = round(momentum_score, 2)

        # ── Volume Score ──────────────────────────────────────────
        # Volume surge confirms the price move is real, not a fake-out
        volume_score = 0.0
        if volume_ratio >= 1.5:
            # Strong volume surge — full score at 3x average
            volume_score = self.W_VOLUME * min((volume_ratio - 1.0) / 2.0, 1.0)
        elif volume_ratio >= 1.0:
            # Normal / slightly above average — half credit
            volume_score = self.W_VOLUME * 0.3 * (volume_ratio - 1.0)
        else:
            # Below average volume — penalize (move may not be sustained)
            volume_score = self.W_VOLUME * 0.1
        breakdown["volume"] = round(volume_score, 2)

        # ── Trend Score ───────────────────────────────────────────
        # Where is the price in its 52-week range?
        # Best entries: 30-70% of range (off lows but not at highs)
        trend_score = 0.0
        trend_pct   = 0.0
        if price and week52_low and week52_high and week52_high > week52_low:
            trend_pct = (price - week52_low) / (week52_high - week52_low) * 100
            if 30 <= trend_pct <= 70:
                # Sweet spot — middle of range
                trend_score = self.W_TREND
            elif trend_pct < 30:
                # Near 52-week lows — risky (falling knife), partial credit
                trend_score = self.W_TREND * (trend_pct / 30) * 0.6
            else:
                # Near 52-week highs — momentum exists but chasing risk
                trend_score = self.W_TREND * (1.0 - (trend_pct - 70) / 30) * 0.7
        breakdown["trend"] = round(trend_score, 2)

        # ── Profit Score ──────────────────────────────────────────
        # Reward held positions that are climbing — let winners ride
        profit_score = 0.0
        if unrealized_pct > 0:
            # Positive unrealized gain — bonus, capped at 10% gain = full score
            profit_score = self.W_PROFIT * min(unrealized_pct / 10.0, 1.0)
        elif unrealized_pct < -3:
            # Significant loss — penalize to encourage stop-loss
            profit_score = -self.W_PROFIT * min(abs(unrealized_pct) / 10.0, 1.0)
        breakdown["profit"] = round(profit_score, 2)

        total = max(0.0, min(100.0,
            rsi_score + momentum_score + volume_score + trend_score + profit_score
        ))
        breakdown["total"] = round(total, 2)

        return total, breakdown


# ════════════════════════════════════════════════════════════════
#  PORTFOLIO LADDER SCANNER
# ════════════════════════════════════════════════════════════════

class PortfolioLadderScanner:
    """
    Manages a large portfolio (up to 61+ symbols).
    Continuously scores, ranks, and tiers all symbols.
    Publishes the ranked ladder to the trading engine each cycle.

    The "ladder" is a sorted list: best candidates at top, worst at bottom.
    Only TOP_TIER stocks are passed to the engine as BUY candidates.
    """

    def __init__(
        self,
        symbols: List[str],
        engine=None,                     # reference to TradingEngine (optional)
        max_workers: int = 12,           # parallel scan workers — use 12 for 61 stocks
        top_tier_pct: float = 0.20,      # top 20% = BUY candidates
        bottom_tier_pct: float = 0.20,   # bottom 20% = AVOID / sell if held
        min_score_to_buy: float = 45.0,  # even TOP_TIER needs this minimum score
        rsi_buy_max: float = 55.0,
    ):
        self.symbols        = [s.upper().strip() for s in symbols if s.strip()]
        self.engine         = engine
        self.max_workers    = max_workers
        self.top_tier_pct   = top_tier_pct
        self.bottom_tier_pct = bottom_tier_pct
        self.min_score_to_buy = min_score_to_buy
        self.rsi_buy_max    = rsi_buy_max

        self.scorer         = LadderScorer()
        self._ladder: Dict[str, LadderEntry] = {
            s: LadderEntry(symbol=s) for s in self.symbols
        }
        self._lock          = threading.Lock()
        self._running       = False
        self._cycle_count   = 0
        self._last_scan_ts  = 0.0

        logger.info(f"[LADDER] Initialized with {len(self.symbols)} symbols. "
                    f"Top tier: top {top_tier_pct*100:.0f}% | "
                    f"Min score to buy: {min_score_to_buy}")

    # ── Public API ────────────────────────────────────────────

    def get_ladder(self) -> List[Dict[str, Any]]:
        """Returns current ranked ladder as list of dicts (highest score first)."""
        with self._lock:
            entries = sorted(self._ladder.values(), key=lambda e: e.score, reverse=True)
            return [e.to_dict() for e in entries]

    def get_top_tier(self) -> List[str]:
        """Returns symbols in TOP tier (highest scored) — these are BUY candidates."""
        with self._lock:
            return [s for s, e in self._ladder.items() if e.tier == "TOP"]

    def get_bottom_tier(self) -> List[str]:
        """Returns symbols in BOTTOM tier — avoid buying, sell if held."""
        with self._lock:
            return [s for s, e in self._ladder.items() if e.tier == "BOTTOM"]

    def get_verdict(self, symbol: str) -> str:
        """Get the ladder verdict for a specific symbol."""
        with self._lock:
            entry = self._ladder.get(symbol.upper())
            return entry.verdict if entry else "HOLD"

    def is_buy_candidate(self, symbol: str) -> bool:
        """Returns True if symbol is in TOP tier with sufficient score."""
        with self._lock:
            entry = self._ladder.get(symbol.upper())
            if not entry:
                return False
            return entry.tier == "TOP" and entry.score >= self.min_score_to_buy

    def summary(self) -> Dict[str, Any]:
        """Returns a summary for dashboard display."""
        ladder = self.get_ladder()
        return {
            "total_symbols":  len(ladder),
            "top_tier_count": len([e for e in ladder if e["tier"] == "TOP"]),
            "bottom_count":   len([e for e in ladder if e["tier"] == "BOTTOM"]),
            "cycle_count":    self._cycle_count,
            "last_scan":      self._last_scan_ts,
            "top_5":          ladder[:5],
            "bottom_5":       ladder[-5:],
        }

    # ── Main scan loop ────────────────────────────────────────

    def scan_once(self) -> List[LadderEntry]:
        """
        Scores all symbols in parallel and updates the ladder.
        Returns the sorted ladder.
        """
        results: Dict[str, LadderEntry] = {}

        # Grab current holdings from engine for profit scoring
        holdings = {}
        if self.engine and hasattr(self.engine, "current_holdings"):
            holdings = self.engine.current_holdings or {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._score_symbol, sym, holdings): sym
                for sym in self.symbols
            }
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    entry = future.result(timeout=15)
                    if entry:
                        results[sym] = entry
                except Exception as e:
                    logger.debug(f"[LADDER] {sym} score failed: {e}")
                    # Keep the last known entry rather than dropping it
                    with self._lock:
                        if sym in self._ladder:
                            results[sym] = self._ladder[sym]

        # Apply tiering
        all_entries = sorted(results.values(), key=lambda e: e.score, reverse=True)
        n = len(all_entries)
        top_n    = max(1, int(n * self.top_tier_pct))
        bottom_n = max(1, int(n * self.bottom_tier_pct))

        for i, entry in enumerate(all_entries):
            if i < top_n and entry.score >= self.min_score_to_buy:
                entry.tier    = "TOP"
                entry.verdict = "BUY"
            elif i >= n - bottom_n:
                entry.tier    = "BOTTOM"
                entry.verdict = "SELL" if entry.symbol in holdings else "AVOID"
            else:
                entry.tier    = "NEUTRAL"
                entry.verdict = "HOLD"

        with self._lock:
            for sym, entry in results.items():
                self._ladder[sym] = entry

        self._cycle_count  += 1
        self._last_scan_ts  = time.time()

        logger.info(
            f"[LADDER] Cycle {self._cycle_count}: "
            f"{len(all_entries)} symbols scored | "
            f"TOP: {sum(1 for e in all_entries if e.tier=='TOP')} | "
            f"BOTTOM: {sum(1 for e in all_entries if e.tier=='BOTTOM')} | "
            f"Leader: {all_entries[0].symbol if all_entries else '—'} "
            f"({all_entries[0].score:.1f})" if all_entries else ""
        )

        return all_entries

    def _score_symbol(self, symbol: str, holdings: dict) -> Optional[LadderEntry]:
        """Score a single symbol. Called from thread pool."""
        if not self.engine:
            return None

        try:
            # Fetch current price, then get full signal from engine
            price = self.engine.get_live_price(symbol) if hasattr(self.engine, "get_live_price") else None
            if price is None:
                return None
            signal = self.engine._get_signal(symbol, price) if hasattr(self.engine, "_get_signal") else {}

            rsi   = signal.get("rsi")
            sma20 = signal.get("sma20")
            sma50 = signal.get("sma50")
            price = signal.get("price")

            # Volume ratio (engine may expose this)
            volume_ratio = signal.get("volume_ratio", 1.0)

            # 52-week range (from engine or Alpha Vantage if available)
            week52_low  = signal.get("week52_low")
            week52_high = signal.get("week52_high")

            # Unrealized profit if held
            unrealized_pct = 0.0
            if symbol in holdings and price:
                buy_price = holdings[symbol].get("price")
                if buy_price and buy_price > 0:
                    unrealized_pct = (price - buy_price) / buy_price * 100

            score, breakdown = self.scorer.score(
                rsi=rsi,
                sma20=sma20,
                sma50=sma50,
                price=price,
                volume_ratio=volume_ratio,
                week52_low=week52_low,
                week52_high=week52_high,
                unrealized_pct=unrealized_pct,
                rsi_buy_max=self.rsi_buy_max,
            )

            trend_pct = 0.0
            if price and week52_low and week52_high and week52_high > week52_low:
                trend_pct = (price - week52_low) / (week52_high - week52_low) * 100

            return LadderEntry(
                symbol=symbol,
                score=score,
                rsi=rsi,
                sma20=sma20,
                sma50=sma50,
                price=price,
                volume_ratio=volume_ratio,
                trend_pct=trend_pct,
                unrealized_pct=unrealized_pct,
                score_breakdown=breakdown,
                last_updated=time.time(),
            )

        except Exception as e:
            logger.debug(f"[LADDER] _score_symbol({symbol}) error: {e}")
            return None

    def run_forever(self, interval_seconds: int = 60):
        """
        Runs continuous ladder scanning.
        Designed to be called from a daemon thread alongside the main engine.
        interval_seconds: how often to re-score all symbols (default 60s)
        """
        self._running = True
        logger.info(f"[LADDER] Scanner started. {len(self.symbols)} symbols, "
                    f"rescoring every {interval_seconds}s")

        while self._running:
            try:
                self.scan_once()
            except Exception as e:
                logger.exception(f"[LADDER] scan_once error: {e}")

            # Sleep in small chunks so we can stop cleanly
            for _ in range(interval_seconds):
                if not self._running:
                    break
                time.sleep(1)

        logger.info("[LADDER] Scanner stopped.")

    def stop(self):
        self._running = False


# ════════════════════════════════════════════════════════════════
#  INTEGRATION HELPER
# ════════════════════════════════════════════════════════════════

def integrate_ladder_with_engine(engine, ladder_scanner: PortfolioLadderScanner):
    """
    Integrates the ladder scanner with the trading engine by storing
    the scanner reference on the engine instance directly.

    The engine's _get_signal method is NOT patched -- instead the
    ladder scanner is attached as engine.ladder_scanner so the engine
    can check it natively during its scan loop.

    This avoids all Python bound-method patching issues entirely.
    """
    # Simply attach the scanner to the engine as an attribute
    engine.ladder_scanner = ladder_scanner

    # Monkey-patch the buy() method to check ladder tier before buying
    original_buy = engine.buy.__func__ if hasattr(engine.buy, '__func__') else None
    original_scan_symbol = engine._scan_symbol if hasattr(engine, '_scan_symbol') else None

    # Store original _get_signal for reference
    engine._original_get_signal = engine._get_signal

    # Wrap at the scan level using a simple attribute check
    def is_ladder_approved(symbol: str) -> bool:
        """Returns True if symbol is approved by ladder scanner."""
        scanner = getattr(engine, 'ladder_scanner', None)
        if scanner is None:
            return True  # No scanner = always approved
        # First cycle: ladder may not have scored yet, allow through
        entry = scanner._ladder.get(symbol.upper())
        if entry is None or entry.last_updated == 0.0:
            return True  # Not yet scored -- allow
        return scanner.is_buy_candidate(symbol)

    # Attach the approval function to the engine
    engine.is_ladder_approved = is_ladder_approved

    logger.info(f"[LADDER] Integrated with engine via attribute attachment. "
                f"{len(ladder_scanner.symbols)} symbols will be ladder-gated. "
                f"Engine will check engine.is_ladder_approved(symbol) before buying.")


# ════════════════════════════════════════════════════════════════
#  BROTHER'S 61-STOCK PORTFOLIO — Default symbols
# ════════════════════════════════════════════════════════════════

# Replace or extend this list with the actual 61 portfolio symbols.
# The scanner handles any number — more symbols just means more parallel workers.
DEFAULT_PORTFOLIO = [
    # ── Mega Cap Tech ──────────────────────────────────────────
    "AAPL", "MSFT", "GOOG", "AMZN", "NVDA", "META", "TSLA",
    # ── Semiconductors ─────────────────────────────────────────
    "AMD",  "INTC", "AVGO", "TSM",  "ARM",  "QCOM", "MU",
    # ── Financials ─────────────────────────────────────────────
    "JPM",  "GS",   "MS",   "BAC",  "V",    "MA",   "PYPL",
    # ── Consumer / Retail ──────────────────────────────────────
    "AMZN", "HD",   "WMT",  "TGT",  "COST", "NKE",
    # ── Healthcare ─────────────────────────────────────────────
    "JNJ",  "UNH",  "PFE",  "MRNA", "ABBV", "LLY",
    # ── Energy ─────────────────────────────────────────────────
    "XOM",  "CVX",  "COP",  "SLB",
    # ── Growth / EV / Space ────────────────────────────────────
    "RIVN", "LCID", "ASTS", "IONQ", "PLTR", "SOFI",
    # ── ETFs (for diversification signals) ─────────────────────
    "SPY",  "QQQ",  "IWM",  "VTI",  "GLD",  "TLT",
    # ── Media / Streaming / Gaming ─────────────────────────────
    "NFLX", "DIS",  "RBLX", "SNAP",
    # ── Cloud / SaaS ───────────────────────────────────────────
    "CRM",  "NOW",  "SNOW", "DDOG", "NET",  "CRWD",
    # ── Other ──────────────────────────────────────────────────
    "COIN", "HOOD", "UBER", "LYFT", "SHOP",
]

# De-duplicate while preserving order
_seen = set()
DEFAULT_PORTFOLIO = [s for s in DEFAULT_PORTFOLIO if not (_seen.add(s) or s in _seen)]


if __name__ == "__main__":
    # Quick test run — prints ladder without a live engine
    logging.basicConfig(level=logging.INFO)
    print(f"\nDefault portfolio: {len(DEFAULT_PORTFOLIO)} symbols")
    print("Symbols:", ", ".join(DEFAULT_PORTFOLIO))
    print("\nPortfolioLadderScanner ready.")
    print("To use: import this module and call integrate_ladder_with_engine(engine, scanner)")
