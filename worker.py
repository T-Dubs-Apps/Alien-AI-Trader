import os
import time
import signal
import sys
import threading

from trading_engine import TradingEngine
from portfolio_ladder import PortfolioLadderScanner, integrate_ladder_with_engine, DEFAULT_PORTFOLIO

# ── Runtime limits ────────────────────────────────────────────
# Default: 5 hours 59 minutes (just under Alpaca's 6-hour session limit)
RUN_SECONDS  = int(os.environ.get("RUN_SECONDS", str(5 * 60 * 60 + 59 * 60)))

# ── Concurrent scan workers ───────────────────────────────────
# 12 workers handles 61 symbols in parallel efficiently
SCAN_WORKERS = int(os.environ.get("SCAN_WORKERS", "12"))

# ── Ladder scanner settings ───────────────────────────────────
LADDER_INTERVAL  = int(os.environ.get("LADDER_INTERVAL",   "60"))
MIN_SCORE_TO_BUY = float(os.environ.get("MIN_SCORE_TO_BUY", "45.0"))
TOP_TIER_PCT     = float(os.environ.get("TOP_TIER_PCT",     "0.20"))
BOTTOM_TIER_PCT  = float(os.environ.get("BOTTOM_TIER_PCT",  "0.20"))


def build_symbol_list() -> list:
    """
    Build the symbol list from env var STOCK_LIST.
    Falls back to DEFAULT_PORTFOLIO (61 symbols) if not set.
    Users can override by setting STOCK_LIST=AAPL,GOOG,TSLA,...
    """
    env_list = os.environ.get("STOCK_LIST", "").strip()
    if env_list:
        symbols = [s.strip().upper() for s in env_list.split(",") if s.strip()]
        print(f"[WORKER] Using STOCK_LIST from env: {len(symbols)} symbols")
    else:
        symbols = DEFAULT_PORTFOLIO
        print(f"[WORKER] Using DEFAULT_PORTFOLIO: {len(symbols)} symbols")
    return symbols


def main():
    symbols = build_symbol_list()
    mode    = os.environ.get("ENGINE_MODE", "AI")

    print(f"[WORKER] Starting Alien AI Trader Worker")
    print(f"[WORKER] Symbols: {len(symbols)} | Mode: {mode} | "
          f"Run limit: {RUN_SECONDS // 3600}h {(RUN_SECONDS % 3600) // 60}m")

    # ── Create trading engine ─────────────────────────────────
    engine = TradingEngine(symbols, mode=mode)

    # ── Create portfolio ladder scanner ───────────────────────
    ladder = PortfolioLadderScanner(
        symbols=symbols,
        engine=engine,
        max_workers=SCAN_WORKERS,
        top_tier_pct=TOP_TIER_PCT,
        bottom_tier_pct=BOTTOM_TIER_PCT,
        min_score_to_buy=MIN_SCORE_TO_BUY,
        rsi_buy_max=float(os.environ.get("RSI_BUY_MAX", "55.0")),
    )

    # ── Wire ladder into engine signal gating ─────────────────
    integrate_ladder_with_engine(engine, ladder)
    print(f"[WORKER] Ladder scanner integrated -- only TOP {TOP_TIER_PCT * 100:.0f}% "
          f"of {len(symbols)} symbols will be BUY candidates per cycle")

    # ── Shutdown handler ──────────────────────────────────────
    def shutdown(*_):
        print("[WORKER] Shutdown signal received -- stopping engine and scanner.")
        ladder.stop()
        engine.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT,  shutdown)

    # ── Start engine ──────────────────────────────────────────
    engine.start()

    # ── Start ladder scanner in daemon thread ─────────────────
    ladder_thread = threading.Thread(
        target=ladder.run_forever,
        kwargs={"interval_seconds": LADDER_INTERVAL},
        daemon=True,
        name="LadderScanner"
    )
    ladder_thread.start()
    print(f"[WORKER] Ladder scanner running (rescores every {LADDER_INTERVAL}s)")

    # ── Run engine loop in daemon thread ──────────────────────
    engine_thread = threading.Thread(
        target=engine.run_forever,
        daemon=True,
        name="TradingEngine"
    )
    engine_thread.start()

    # ── Monitor loop ──────────────────────────────────────────
    start = time.time()
    while True:
        now = time.time()

        # Restart engine thread if it dies unexpectedly
        if not engine_thread.is_alive():
            print("[WORKER] Engine thread died -- restarting.")
            engine.start()
            engine_thread = threading.Thread(
                target=engine.run_forever,
                daemon=True,
                name="TradingEngine"
            )
            engine_thread.start()

        # Restart ladder thread if it dies
        if not ladder_thread.is_alive():
            print("[WORKER] Ladder scanner thread died -- restarting.")
            ladder_thread = threading.Thread(
                target=ladder.run_forever,
                kwargs={"interval_seconds": LADDER_INTERVAL},
                daemon=True,
                name="LadderScanner"
            )
            ladder_thread.start()

        # Print ladder top 5 every 30 seconds
        if int(now) % 30 == 0:
            try:
                summary = ladder.summary()
                top_names = [e["symbol"] for e in summary.get("top_5", [])]
                if top_names:
                    print(f"[WORKER] Ladder top 5: {' -> '.join(top_names)}")
            except Exception:
                pass

        # Enforce RUN_SECONDS limit (clean shutdown before Alpaca session expires)
        if now - start >= RUN_SECONDS:
            print(f"[WORKER] RUN_SECONDS limit reached "
                  f"({RUN_SECONDS // 60}min) -- shutting down cleanly.")
            ladder.stop()
            engine.stop()
            sys.exit(0)

        time.sleep(2)


if __name__ == "__main__":
    main()

# Built by Troy Walker of T-Dub's Apps - 2026-04-26
