import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TradingEngine")

class TradingEngine:
    def __init__(self, activity_callback=None, *args, **kwargs):
        """
        Initializes the Trading Engine.
        Captures all kwargs and the callback to ensure seamless integration.
        """
        self.activity_callback = activity_callback
        self.options = kwargs
        self.is_online = False
        
        self.notify("TradingEngine initialized successfully.")

    def notify(self, message: str):
        """
        Sends logs to stdout and dynamically satisfies the UI callback signature.
        """
        logger.info(message)
        cb = self.activity_callback
        
        if not (cb and callable(cb)):
            return
            
        try:
            # Attempt 1: App UI expects (status, message) or (event, message)
            cb("SYSTEM_INFO", message)
        except TypeError:
            try:
                # Attempt 2: App UI expects an explicitly named keyword argument
                cb(message=message)
            except TypeError:
                try:
                    # Attempt 3: Fallback to single standard positional argument
                    cb(message)
                except Exception as e:
                    logger.error(f"Callback execution failed: {e}")

    def start(self):
        """Starts the trading engine processing loop."""
        self.is_online = True
        self.notify("Engine Status: Online")

    def stop(self):
        """Stops the trading engine processing loop."""
        self.is_online = False
        self.notify("Engine Status: Offline")

if __name__ == "__main__":
    # Test execution block
    engine = TradingEngine(activity_callback=lambda event, msg: print(f"[{event}] {msg}"))
    engine.start()