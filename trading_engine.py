import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TradingEngine")

class TradingEngine:
    def __init__(self, activity_callback=None, *args, **kwargs):
        """
        Initializes the Trading Engine.
        Accepts activity_callback and captures any arbitrary **kwargs 
        to ensure seamless integration with host UI callers.
        """
        self.activity_callback = activity_callback
        self.options = kwargs
        self.is_online = False
        
        # Log successful initialization
        self.notify("TradingEngine initialized successfully.")

    def notify(self, message: str):
        """Helper to send logs to stdout and trigger the UI callback if present."""
        logger.info(message)
        if self.activity_callback and callable(self.activity_callback):
            try:
                self.activity_callback(message)
            except Exception as e:
                logger.error(f"Error executing activity_callback: {e}")

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
    engine = TradingEngine(activity_callback=lambda msg: print(f"[Callback Output] {msg}"))
    engine.start()