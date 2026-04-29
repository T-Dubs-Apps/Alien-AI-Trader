# Dynamic Position Sizing — Streaks & Volatility

# This module provides helper functions for dynamic position sizing based on recent win/loss streaks and market volatility.
# To be imported and used by TradingEngine.

import numpy as np

def calc_volatility(closes, period=20):
    """Calculate rolling volatility (standard deviation of log returns)."""
    if len(closes) < period + 1:
        return 0.02  # fallback: 2% if not enough data
    log_returns = np.log(closes / closes.shift(1)).dropna()
    return float(log_returns.rolling(period).std().iloc[-1])

def adjust_risk_for_streak(base_risk_pct, trade_log, streak_window=5, min_risk=0.5, max_risk=5.0):
    """Adjust risk per trade based on recent win/loss streak (last N trades)."""
    if not trade_log or len(trade_log) < streak_window:
        return base_risk_pct
    recent = trade_log[-streak_window:]
    wins = sum(1 for t in recent if t.get('action')=='SELL' and t.get('profit',0)>0)
    losses = streak_window - wins
    # If on a win streak, increase risk up to max_risk; on a loss streak, decrease to min_risk
    if wins == streak_window:
        return min(base_risk_pct * 1.5, max_risk)
    elif losses == streak_window:
        return max(base_risk_pct * 0.5, min_risk)
    return base_risk_pct

def adjust_risk_for_volatility(base_risk_pct, volatility, min_risk=0.5, max_risk=5.0):
    """Adjust risk per trade based on volatility (lower risk in high-vol environments)."""
    # Example: If vol > 4%, cut risk in half; if vol < 1%, allow higher risk
    if volatility > 0.04:
        return max(base_risk_pct * 0.5, min_risk)
    elif volatility < 0.01:
        return min(base_risk_pct * 1.5, max_risk)
    return base_risk_pct
