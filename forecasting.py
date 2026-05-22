"""
Alien AI Trader — Predictive Forecasting Module
Provides short-term price direction forecasting using:
  - Linear regression trend analysis
  - Multi-timeframe EMA momentum stacking
  - Combined forecast score (0-25) for ladder integration

Built by Troy Walker of T-Dub's Apps — 2026
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional


def linear_forecast(closes: pd.Series, periods_ahead: int = 5) -> Dict[str, Any]:
    """
    Linear regression forecast over the last N bars.
    Returns predicted price, trend direction, slope, and R-squared confidence.
    """
    n = len(closes)
    if n < 10:
        return {
            "direction": "neutral", "predicted_price": None, "current_price": None,
            "predicted_change_pct": 0.0, "slope_pct_per_bar": 0.0,
            "confidence": 0.0, "r_squared": 0.0,
        }

    x = np.arange(n, dtype=float)
    y = closes.values.astype(float)

    coeffs = np.polyfit(x, y, 1)
    slope  = coeffs[0]

    y_pred = np.polyval(coeffs, x)
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r_sq   = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    r_sq   = max(0.0, min(1.0, r_sq))

    predicted = float(np.polyval(coeffs, n + periods_ahead))
    current   = float(closes.iloc[-1])

    slope_pct = (slope / current * 100) if current > 0 else 0.0
    chg_pct   = ((predicted - current) / current * 100) if current > 0 else 0.0

    if slope_pct > 0.02:
        direction = "up"
    elif slope_pct < -0.02:
        direction = "down"
    else:
        direction = "neutral"

    return {
        "direction":           direction,
        "predicted_price":     round(predicted, 4),
        "current_price":       round(current, 4),
        "predicted_change_pct": round(chg_pct, 3),
        "slope_pct_per_bar":   round(slope_pct, 4),
        "confidence":          round(r_sq, 4),
        "r_squared":           round(r_sq, 4),
    }


def momentum_forecast(closes: pd.Series) -> Dict[str, Any]:
    """
    Multi-timeframe EMA stacking analysis.
    Stacked alignment (price > EMA5 > EMA10 > EMA20) signals sustained climb.
    """
    if len(closes) < 20:
        return {"climbing": False, "strength": 0.0, "phase": "unknown",
                "ema5": None, "ema10": None, "ema20": None}

    ema5  = float(closes.ewm(span=5,  adjust=False).mean().iloc[-1])
    ema10 = float(closes.ewm(span=10, adjust=False).mean().iloc[-1])
    ema20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
    current = float(closes.iloc[-1])

    stacked_up   = current > ema5 > ema10 > ema20
    stacked_down = current < ema5 < ema10 < ema20

    s5_20  = (ema5  - ema20) / ema20  if ema20  > 0 else 0.0
    s10_20 = (ema10 - ema20) / ema20  if ema20  > 0 else 0.0
    s5_10  = (ema5  - ema10) / ema10  if ema10  > 0 else 0.0

    if stacked_up:
        strength = min(1.0, (abs(s5_20) + abs(s10_20) + abs(s5_10)) * 10.0)
        phase    = "climbing"
    elif stacked_down:
        strength = 0.0
        phase    = "falling"
    else:
        # Convergence/divergence in progress
        strength = max(0.0, min(0.5, s5_20 * 5.0))
        phase    = "consolidating"

    return {
        "climbing": stacked_up,
        "strength": round(strength, 4),
        "phase":    phase,
        "ema5":     round(ema5,  4),
        "ema10":    round(ema10, 4),
        "ema20":    round(ema20, 4),
    }


def get_forecast(closes: pd.Series, periods_ahead: int = 5) -> Dict[str, Any]:
    """
    Combined forecast: linear regression + EMA momentum stacking.
    Returns a 0-25 composite forecast score and directional signals.

    score breakdown:
      Linear (up + confident)  → 0-15 pts
      Momentum (EMA stacking)  → 0-10 pts
    """
    lin = linear_forecast(closes, periods_ahead)
    mom = momentum_forecast(closes)

    # Linear score: direction must be up, weighted by confidence and slope magnitude
    lin_score = 0.0
    if lin["direction"] == "up":
        lin_score = 15.0 * lin["confidence"] * min(1.0, abs(lin["slope_pct_per_bar"]) * 30)
    elif lin["direction"] == "down":
        lin_score = -5.0 * lin["confidence"]

    # Momentum score: EMA stacking strength
    if mom["climbing"]:
        mom_score = mom["strength"] * 10.0
    elif mom["phase"] == "falling":
        mom_score = -5.0
    else:
        mom_score = mom["strength"] * 3.0

    total = round(max(0.0, min(25.0, lin_score + mom_score)), 2)

    # Determine overall forecast direction
    if lin["direction"] == "up" and mom["phase"] in ("climbing", "consolidating"):
        overall_direction = "up"
    elif lin["direction"] == "down" or mom["phase"] == "falling":
        overall_direction = "down"
    else:
        overall_direction = "neutral"

    return {
        "score":                total,
        "forecast_direction":   overall_direction,
        "forecast_phase":       mom["phase"],
        "linear":               lin,
        "momentum":             mom,
        "predicted_price":      lin.get("predicted_price"),
        "predicted_change_pct": lin.get("predicted_change_pct", 0.0),
    }
