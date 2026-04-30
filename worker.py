import os
import signal
import time
import threading
import requests

# Built by Troy Walker of T-Dub's Apps - 2026-04-26

RUN_SECONDS = int(os.environ.get("RUN_SECONDS", "3300"))
LADDER_INTERVAL = int(os.environ.get("LADDER_INTERVAL", "5"))


def shutdown(signum, frame):
    print(f"[WORKER] Received signal {signum}. Shutting down...")
    try:
        ladder.stop()
    except Exception:
        pass
    try:
        engine.stop()
    except Exception:
        pass
    raise SystemExit(0)


def safe_dashboard_notify(dashboard_url, level, message):
    if not dashboard_url:
        return
    try:
        requests.post(
            f"{dashboard_url}/api/notifications",
            json={"level": level, "message": message},
            timeout=5,
        )
    except Exception:
        pass


def main():
    dashboard_url = (
        os.environ.get("DASHBOARD_BASE_URL")
        or os.environ.get("DASHBOARD_URL")
        or ""
    ).rstrip("/")

    heartbeat_interval = int(os.environ.get("HEARTBEAT_EVERY_SECONDS", "10"))

    engine.start()

    if dashboard_url:
        hb_thread = threading.Thread(
            target=heartbeat_loop,
            args=(engine, dashboard_url, heartbeat_interval),
            daemon=True,
            name="Heartbeat",
        )
        hb_thread.start()
        print(
            f"[WORKER] Heartbeat thread running → "
            f"{dashboard_url} every {heartbeat_interval}s"
        )
    else:
        print("[WORKER] WARNING: DASHBOARD_BASE_URL not set — UI will not receive live updates")

    ladder_thread = threading.Thread(
        target=ladder.run_forever,
        kwargs={"interval_seconds": LADDER_INTERVAL},
        daemon=True,
        name="LadderScanner",
    )
    ladder_thread.start()
    print(f"[WORKER] Ladder scanner running (rescores every {LADDER_INTERVAL}s)")

    engine_thread = threading.Thread(
        target=engine.run_forever,
        daemon=True,
        name="TradingEngine",
    )
    engine_thread.start()

    start = time.time()
    last_ladder_print = 0

    while True:
        now = time.time()

        if not engine_thread.is_alive():
            msg = "[WORKER] Engine thread died -- restarting."
            print(msg)
            send_crash_notification(msg)
            safe_dashboard_notify(dashboard_url, "alert", msg)

            engine.start()
            engine_thread = threading.Thread(
                target=engine.run_forever,
                daemon=True,
                name="TradingEngine",
            )
            engine_thread.start()

        if not ladder_thread.is_alive():
            msg = "[WORKER] Ladder scanner thread died -- restarting."
            print(msg)
            send_crash_notification(msg)
            safe_dashboard_notify(dashboard_url, "alert", msg)

            ladder_thread = threading.Thread(
                target=ladder.run_forever,
                kwargs={"interval_seconds": LADDER_INTERVAL},
                daemon=True,
                name="LadderScanner",
            )
            ladder_thread.start()

        if now - last_ladder_print >= 30:
            last_ladder_print = now
            try:
                summary = ladder.summary()
                top_names = [e["symbol"] for e in summary.get("top_5", [])]
                if top_names:
                    print(
                        f"[WORKER] Ladder top 5: {' -> '.join(top_names)} "
                        f"(scan_all_market={engine.scan_all_market})"
                    )
                else:
                    print("[WORKER] No top 5 found. Likely no market candidates or scan issue.")
            except Exception as ex:
                print(f"[WORKER] Ladder summary error: {ex}")

        if now - start >= RUN_SECONDS:
            print(
                f"[WORKER] RUN_SECONDS limit reached "
                f"({RUN_SECONDS // 60}min) -- recycling session cleanly."
            )
            ladder.stop()
            engine.stop()
            time.sleep(3)
            return

        time.sleep(2)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    restart_count = 0

    while True:
        restart_count += 1
        print(
            f"[WORKER] {'Starting' if restart_count == 1 else 'Restarting'} "
            f"session #{restart_count} ..."
        )

        try:
            main()
        except SystemExit:
            raise
        except Exception as e:
            msg = f"[WORKER] Unexpected crash in session #{restart_count}: {e}"
            print(msg)

            try:
                send_crash_notification(msg)
            except Exception:
                pass

        print(
            f"[WORKER] Session #{restart_count} ended. "
            f"Sleeping 5s then launching session #{restart_count + 1} ..."
        )
        time.sleep(5)