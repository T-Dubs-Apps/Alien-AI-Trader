from crash_notifier import send_crash_notification
import os
import time
import signal
import sys
import threading
import requests

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


def heartbeat_loop(engine: TradingEngine, dashboard_url: str, interval: int = 10):
    """
    Sends a heartbeat to the dashboard every N seconds regardless of market hours.
    This keeps the UI live feed and worker status indicator green at all times.
    """
    while True:
        try:
            with engine.lock:
                positions = {
                    sym: {"price": h["price"], "qty": h["qty"]}
                    for sym, h in engine.current_holdings.items()
                }
                invested = sum(h["qty"] * h["price"] for h in engine.current_holdings.values())

            payload = {
                "running":      engine.running,
                "mode":         engine.trading_mode,
                "stock_list":   engine.stock_list,
                "profit":       round(engine.profit, 4),
                "positions":    positions,
                "signals":      dict(engine._symbol_signals),
                "message":      "heartbeat",
                "poll_seconds": engine.poll_seconds,
                "trade_count":  len(engine.trade_log),
                "capital": {
                    "initial":   round(engine.initial_capital, 2),
                    "available": round(engine._available_capital, 2),
                    "invested":  round(invested, 2),
                    "total":     round(engine._available_capital + invested, 2),
                    "mode":      "pool" if engine.initial_capital > 0 else "fixed_qty",
                },
                "trailing_stop_pct":    round(engine.trailing_stop_pct * 100, 2),
                "loss_threshold":       round(engine.loss_threshold * 100, 2),
                "scan_all_market":      engine.scan_all_market,
                "max_positions":        engine.max_positions,
                "min_positions":        engine.min_positions,
                "trading_mode":         engine.trading_mode,
                "live_trading_enabled": engine.live_enabled,
                "auto_trade":           engine.auto_trade,
                "risk_settings": {
                    "risk_per_trade_pct": engine.risk_per_trade_pct,
                    "max_position_pct":   engine.max_position_pct,
                    "risk_per_trade_usd": engine.risk_per_trade_usd,
                    "rsi_buy_max":        engine.rsi_buy_max,
                    "rsi_sell_min":       engine.rsi_sell_min,
                    "sma_spread_min":     engine.sma_spread_min,
                },
            }
            requests.post(f"{dashboard_url}/api/worker/heartbeat", json=payload, timeout=5)
        except Exception as e:
            print(f"[HEARTBEAT] Failed to ping dashboard: {e}")
        time.sleep(interval)


def build_symbol_list() -> list:
    """
    Build the symbol list from env var STOCK_LIST.
    Falls back to DEFAULT_PORTFOLIO (61 symbols) if not set.
    Users can override by setting STOCK_LIST=AAPL,GOOG,TSLA,...
    """
    env_list = os.environ.get("STOCK_LIST", "").strip()
    if env_list:
        symbols = [s.strip().upper() for s in env_list.split(",") if s.strip()]
        if not symbols:
            print("[WORKER] No stocks selected in STOCK_LIST — will scan full market.")
        else:
            print(f"[WORKER] Using STOCK_LIST from env: {len(symbols)} symbols")
    else:
        symbols = DEFAULT_PORTFOLIO
        print(f"[WORKER] Using DEFAULT_PORTFOLIO: {len(symbols)} symbols")
    # If no symbols, force scan_all_market ON in engine
    if not symbols:
        os.environ["SCAN_ALL_MARKET"] = "true"
    return symbols


def main():
    symbols = build_symbol_list()
    mode = os.environ.get("ENGINE_MODE", "AI")

    print(f"[WORKER] Starting Alien AI Trader Worker")
    print(f"[WORKER] Symbols: {len(symbols)} | Mode: {mode} | "
          f"Run limit: {RUN_SECONDS // 3600}h {(RUN_SECONDS % 3600) // 60}m")

    # If no symbols, force scan_all_market ON
    scan_all_market = os.environ.get("SCAN_ALL_MARKET", "false").lower() == "true" or not symbols

    # ── Create trading engine ─────────────────────────────────
    engine = TradingEngine(symbols, mode=mode)
    engine.scan_all_market = scan_all_market

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
        sys.exit(0)   # SIGTERM from Render = intentional stop, exit is correct here

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # ── Start engine ──────────────────────────────────────────
    engine.start()

    # ── Start dedicated heartbeat thread (keeps UI live 24/7) ─
    dashboard_url = (
        os.environ.get("DASHBOARD_BASE_URL") or
        os.environ.get("DASHBOARD_URL") or ""
    ).rstrip("/")
    heartbeat_interval = int(os.environ.get("HEARTBEAT_EVERY_SECONDS", "10"))
    if dashboard_url:
        hb_thread = threading.Thread(
            target=heartbeat_loop,
            args=(engine, dashboard_url, heartbeat_interval),
            daemon=True,
            name="Heartbeat"
        )
        hb_thread.start()
        print(f"[WORKER] Heartbeat thread running → {dashboard_url} every {heartbeat_interval}s")
    else:
        print("[WORKER] WARNING: DASHBOARD_BASE_URL not set — UI will not receive live updates")

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
            msg = "[WORKER] Engine thread died -- restarting."
            print(msg)
            send_crash_notification(msg)
            # Dashboard log
            try:
                dashboard_url = os.environ.get("DASHBOARD_BASE_URL") or os.environ.get("DASHBOARD_URL") or ""
                if dashboard_url:
                    requests.post(f"{dashboard_url}/api/notifications", json={"level": "alert", "message": msg}, timeout=5)
            except Exception:
                pass
            engine.start()
            engine_thread = threading.Thread(
                target=engine.run_forever,
                daemon=True,
                name="TradingEngine"
            )
            engine_thread.start()

        # Restart ladder thread if it dies
        if not ladder_thread.is_alive():
            msg = "[WORKER] Ladder scanner thread died -- restarting."
            print(msg)
            send_crash_notification(msg)
            try:
                dashboard_url = os.environ.get("DASHBOARD_BASE_URL") or os.environ.get("DASHBOARD_URL") or ""
                if dashboard_url:
                    requests.post(f"{dashboard_url}/api/notifications", json={"level": "alert", "message": msg}, timeout=5)
            except Exception:
                pass
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
                    print(f"[WORKER] Ladder top 5: {' -> '.join(top_names)} (scan_all_market={engine.scan_all_market})")
                else:
                    print("[WORKER] No top 5 found. Likely no market candidates or scan issue.")
            except Exception as ex:
                print(f"[WORKER] Ladder summary error: {ex}")

        # Enforce RUN_SECONDS limit (clean session recycle before Alpaca session expires)
        if now - start >= RUN_SECONDS:
            print(f"[WORKER] RUN_SECONDS limit reached "
                  f"({RUN_SECONDS // 60}min) -- recycling session cleanly.")
            ladder.stop()
            engine.stop()
            time.sleep(3)   # brief pause so threads can flush
            return          # outer loop will restart main() automatically

        time.sleep(2)


if __name__ == "__main__":
    # ── Outer restart loop ────────────────────────────────────────────────────
    # Render does NOT auto-restart a worker that exits cleanly (sys.exit(0)).
    # Instead we loop forever here — when the session limit is reached, main()
    # returns, we sleep 5 seconds, then launch a fresh session automatically.
    # The worker process NEVER exits unless Render kills it (deploy, crash, etc.)
    restart_count = 0
    while True:
        restart_count += 1
        print(f"[WORKER] {'Starting' if restart_count == 1 else 'Restarting'} "
              f"session #{restart_count} ...")
        try:
            main()
        except SystemExit:
            pass
        except Exception as e:
            msg = f"[WORKER] Unexpected crash in session #{restart_count}: {e}"
            print(msg)
            send_crash_notification(msg)
            try:
                dashboard_url = os.environ.get("DASHBOARD_BASE_URL") or os.environ.get("DASHBOARD_URL") or ""
                if dashboard_url:
                    requests.post(f"{dashboard_url}/api/notifications", json={"level": "alert", "message": msg}, timeout=5)
            except Exception:
                pass
        print(f"[WORKER] Session #{restart_count} ended. "
              f"Sleeping 5s then launching session #{restart_count + 1} ...")
        time.sleep(5)

# Built by Troy Walker of T-Dub's Apps - 2026-04-26