import os
import time
import signal
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from trading_engine import TradingEngine

# How long this worker process should run before cycling (default: ~6 hours)
RUN_SECONDS = int(os.environ.get("RUN_SECONDS", str(5 * 60 * 60 + 59 * 60)))

# Concurrent scan workers — how many symbols to process in parallel
SCAN_WORKERS = int(os.environ.get("SCAN_WORKERS", "8"))


def main():
    symbols = [
        s.strip().upper()
        for s in os.environ.get("STOCK_LIST", "AAPL,GOOG,TSLA,MSFT,AMZN").split(",")
        if s.strip()
    ]
    mode = os.environ.get("ENGINE_MODE", "AI")

    engine = TradingEngine(symbols, mode=mode)

    def shutdown(*_):
        print("[WORKER] Shutdown signal received — stopping engine.")
        engine.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    engine.start()

    # Run the engine loop in a daemon thread so the main thread can enforce RUN_SECONDS
    t = threading.Thread(target=engine.run_forever, daemon=True)
    t.start()

    start = time.time()
    while True:
        if not t.is_alive():
            print("[WORKER] Engine thread died — restarting.")
            engine.start()
            t = threading.Thread(target=engine.run_forever, daemon=True)
            t.start()

        if time.time() - start >= RUN_SECONDS:
            print("[WORKER] RUN_SECONDS limit reached — shutting down cleanly.")
            engine.stop()
            sys.exit(0)

        time.sleep(2)


if __name__ == "__main__":
    main()

# Built by Troy Walker of T-Dub's Apps - 2026-04-22

