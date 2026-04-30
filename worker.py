import os
import signal
import time
import threading
import requests  # Added import for requests

# Define the undefined variables and functions
LADDER_INTERVAL = 5  # Placeholder, should be defined according to your needs

def shutdown(signum, frame):
    # Implement shutdown logic
    print(f"[WORKER] Received signal {signum}. Shutting down...")
    # Add shutdown logic here, if needed

def main():
    # Your main logic goes here
    pass  # Placeholder for the main function
   
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
        try:
            if dashboard_url:
                requests.post(f"{dashboard_url}/api/notifications", json={"level": "alert", "message": msg}, timeout=5)
        except Exception:
            pass
        engine.start()  # Ensure proper thread handling here
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
                if dashboard_url:
                    requests.post(f"{dashboard_url}/api/notifications", json={"level": "alert", "message": msg}, timeout=5)
            except Exception:
                pass
        print(f"[WORKER] Session #{restart_count} ended. "
              f"Sleeping 5s then launching session #{restart_count + 1} ...")
        time.sleep(5)

# Built by Troy Walker of T-Dub's Apps - 2026-04-26