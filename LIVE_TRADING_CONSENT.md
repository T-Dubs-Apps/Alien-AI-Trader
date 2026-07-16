# Live Trading Consent

Important: This is a draft consent text for implementation in UI and logs. Obtain legal review before relying on it in production.

## Consent Modal Title
Live Trading Consent (Real Funds)

## Consent Body (Recommended)
By enabling Live Trading, you acknowledge and agree that:

1. Real money is at risk and losses can occur rapidly.
2. Live trading results may differ from paper trading due to market conditions, slippage, spread, liquidity, and execution behavior.
3. You are solely responsible for all orders placed through your broker account.
4. You have reviewed and configured your risk controls (position sizing, max positions, stop-loss, trailing stop, and automation toggles).
5. You understand this software does not guarantee profit and does not eliminate market risk.
6. You understand this software is a tool and not a promise of performance.

## Required Acknowledgement Checkbox
I understand and accept the risks of enabling live trading with real funds.

## Confirmation Button Text
Enable Live Trading

## Cancel Button Text
Keep Paper Trading

## UX Controls (Recommended)

- Require explicit checkbox before enabling.
- Require re-confirmation every time user switches Paper -> Live.
- Display a persistent LIVE badge while live mode is active.
- Log user ID/session, timestamp, deployment ID, and selected risk profile.

## Audit Event Template (JSON)
```json
{
  "event": "live_trading_consent",
  "timestamp": "ISO-8601",
  "deployment": "service-name-or-id",
  "mode_before": "paper",
  "mode_after": "live",
  "acknowledged": true,
  "risk_snapshot": {
    "max_positions": 0,
    "stop_loss_pct": 0,
    "trailing_stop_pct": 0,
    "max_trades_per_hour": 0
  }
}
```

## Revoke/Disable Guidance
Users should be able to immediately switch back to paper mode and/or disable auto-trade without restarting the deployment.
