# Remote Handoff Checklist (No Live Support Needed)

Use this when you cannot stay in contact with the customer during repair.

## 1) Deploy target commit

Deploy latest main branch in Render.

Current reliability commits included:
- 0137ea6 (startup does not stall offline on transient network/API errors)
- 1c45287 (mode-aware preflight for live vs paper)
- 3d6ce68 (password env compatibility + reconnecting startup state)
- 8c8564b (transient Alpaca retry handling)
- b3966ac (password normalization)

## 2) Required Render environment values

Set and save/deploy:
- DASHBOARD_PASSWORD
- FLASK_SECRET
- ALPHA_VANTAGE_KEY
- ALPACA_KEY
- ALPACA_SECRET
- ALPACA_LIVE_KEY
- ALPACA_LIVE_SECRET
- TRADING_MODE=live
- LIVE_TRADING_ENABLED=true
- LICENSE_SECRET (must not be default)
- LICENSE_EMAIL or LICENSE_GRANT (depending on license flow)

Important:
- Use Render Env Vars "Save and deploy" so env changes are included in the deployment.
- Avoid duplicate password vars. Preferred single source is DASHBOARD_PASSWORD.

## 3) Login and verify endpoints

After logging into dashboard, open these URLs:
- /api/engine/diag
- /api/engine/status
- /api/support/snapshot

Expected for live-ready state:
- diag.engine_can_start = true
- diag.alpaca_live.authorized = true
- settings/effective mode shows live
- status.state becomes starting or trading (not stuck offline)

## 4) If status is still offline

Interpretation guide:
- Message contains "temporary network/API issue": transient upstream issue; app should auto-retry and continue startup.
- Message contains "authorization failed": wrong key pair for selected endpoint.
- Message contains license reason: live is blocked by inactive/missing license.

## 5) One-message support payload to request from customer

Ask customer to send:
- Render service URL
- Current deployed commit ID from Render
- JSON outputs from:
  - /api/engine/diag
  - /api/engine/status
  - /api/support/snapshot
- Last 100 lines of Render logs after restart

This bundle is enough to diagnose nearly all offline/live-mode issues without a live call.

## 6) Safety notes for real-money mode

- Live mode should only be enabled when diag confirms live authorized.
- Keep paper keys and live keys as separate pairs.
- Never run with default LICENSE_SECRET in production.
