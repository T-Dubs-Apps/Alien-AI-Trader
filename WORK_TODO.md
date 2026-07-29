# Alien AI Trader — Work / To-Do List

_Prepared 2026-07-29 during an autonomous work window. Nothing here is destructive.
Items are tagged **[auto]** (safe for me to do without you) or **[you]** (needs your
keys, Render access, or a decision). Priorities: **P0** = do first / affects "does it
trade", **P1** = important, **P2** = nice-to-have._

---

## ✅ Done this session (already committed & deployed to `main` → Render)

- **Stop-loss units fix** — `LOSS_THRESHOLD` / `TRAILING_STOP_PCT` now accept a whole
  percent *or* a fraction (`4.0` and `0.04` both = 4%). Closed the boot window where
  they read as 400% / 220%.
- **Keep-alive** — self-ping so a free-tier host doesn't spin down and stop the engine
  (`KEEP_ALIVE_ENABLED`, needs `DASHBOARD_BASE_URL`).
- **Soft-gate toggles** — `SENTIMENT_GATE_ENABLED`, `FORECAST_GATE_ENABLED` (default on).
- **`diagnose_no_buy.py`** — read-only per-stock "why no buy" report.
- **Candlesticks rate-limit** — `/api/candles` cached per symbol/timeframe, serves last
  good bars on a 429, honest messaging, pauses LIVE when tab hidden, and a cache size cap.
- **Market scan on by default** — `SCAN_ALL_MARKET` default `true` (throttles intact).
- **Deploy-without-errors** — only `DASHBOARD_PASSWORD` is required now; `ALLOWED_ORIGINS`
  / `ADMIN_API_TOKEN` are non-fatal with safe fallbacks; blueprint auto-generates the token.
- **PC-first `/get` landing** + README "Cloud or PC?" section and all four links.
- Merged `candlesticks-page` → `main` (candlesticks page is now on production).

---

## 🎯 P0 — Effectiveness: make it visibly buy & sell (the core goal)

- **[you] Confirm valid Alpaca PAPER keys are on Render** and the dashboard shows live
  prices. No prices = no data = it can never buy. Local `keys.bat` keys are known-invalid.
- **[you] Set `DASHBOARD_BASE_URL`** on the Render service to your public URL so the
  keep-alive actually works (otherwise a free instance still sleeps and stops trading).
- **[you] During market hours, watch the Buy Decisions panel** (or run
  `python diagnose_no_buy.py --market` with valid keys). It shows `BUY_EXECUTED` or the
  exact blocking gate. Paste it to me and I'll fix that specific cause.
- **[you→me] If it over-filters**, set `SENTIMENT_GATE_ENABLED=false` and
  `FORECAST_GATE_ENABLED=false` and widen `STOCK_LIST`. I can also add a one-click
  "Aggressive / prove-it-buys" preset.
- **[you] Verify the Render deploy of `63a50b3` went green** (`/health` OK). Render keeps
  the previous version if a deploy fails its health check, so the live site is protected.

## 🔒 P0/P1 — Security

- **[you] Confirm `DASHBOARD_PASSWORD` is set** on every deployment — it's now the single
  hard gate to the controls.
- **[auto→verify] `render.owner.yaml` is now on public `main`** — I confirmed it holds only
  `sync:false` placeholders (no secrets). Worth a second glance from you.
- **[you] Ensure signing/secret keys are set on Render**: `LICENSE_PRIVATE_KEY`,
  `AUDIT_SIGNING_KEY`, `FLASK_SECRET` (generated). Back up `license_private_key.pem`.
- **[auto] Audit all state-changing endpoints** (orders, settings, live-keys, toggles) for
  auth + write-throttle coverage; report gaps. (Read-only review — I can do this.)

## 🧱 P1 — Stability

- **[auto] Add a pytest suite** (pytest is installed, no tests exist today) covering the
  pure logic: percent/fraction normalizers, candles cache TTL + eviction,
  `_is_rate_limit_error`, the risk-profile table, and the buy-gate predicates.
- **[auto] Fix slow/hanging boot for local testing** — the app makes network calls at
  import (license/broker), which blocks `import dashboard`. Move those behind lazy init or
  an offline `--check` mode so it boots (and is testable) without connectivity.
- **[you] External uptime pinger** (UptimeRobot / cron-job.org hitting `/health` every
  10 min) as a belt-and-suspenders complement to the in-process keep-alive — an in-process
  ping can't *wake* an already-slept service.
- **[auto] Supervisor coverage** — verify the engine supervisor also restarts the ladder +
  heartbeat threads if they die, not just the engine thread.

## 🖥️ P1 — Usability

- **[auto] Make "Buy Decisions" prominent** on the main dashboard so a user can always see
  *why* it isn't buying — this is the #1 confusion point.
- **[auto] UI note about persisted settings** — the running app reads
  `trading_settings.json`; changing env vars / code defaults won't move a running instance.
  Add a one-line hint on the Settings page.
- **[auto] Tidy `/get`** — the older "Prefer to run on your home PC?" card is now partly
  redundant with the new comparison card.

## 🔗 P1 — Hub links (pending; needs the Hub repo)

- **[you/me] Add the Trader card with all four links to the Hub**
  (`t-dubs-apps.github.io/alien-ai-apps-hub`, repo `T-Dubs-Apps/alien-ai-apps-hub`).
  I don't have that repo locally; paste-ready snippet is in my chat message, or give me the
  go-ahead to clone and edit it. Links:
  - Get the Trader (all): `https://alien-ai-trader-dashboard.onrender.com/get`
  - PC (ZIP): `https://github.com/T-Dubs-Apps/Alien-AI-Trader/archive/refs/heads/main.zip`
  - Render deploy: `https://render.com/deploy?repo=https://github.com/T-Dubs-Apps/Alien-AI-Trader`
  - GitHub: `https://github.com/T-Dubs-Apps/Alien-AI-Trader`

## ✨ P2 — Enhancements / repairs

- **[auto] Beginner "Aggressive" preset** that relaxes the soft gates + widens candidates so
  a new user can watch it trade quickly, then dial back.
- **[auto] Candle cache is per-process** (fine at `workers=1`); note it if you ever scale
  gunicorn workers — would want a shared cache then.
- **[auto] Reconcile doc drift** — `MAX_TRADES_PER_HOUR` was `6` in the README vs `20` in
  the manifest; I set both to `20`. Confirm that's what you want.
- **[you] Replace local `keys.bat`** with valid paper keys so `diagnose_no_buy.py` and local
  runs work.

---

### What I plan to keep doing autonomously (non-destructive) while you're out
1. Write the pytest suite for the pure logic (**[auto]**, P1 stability).
2. Read-only security audit of state-changing endpoints (**[auto]**, P0/P1) — report only.
3. Small usability tidy-ups on `/get` and a Settings note (**[auto]**, P1) — low risk.

I will **not** touch anything that could be destructive, rotate/expose keys, delete data,
or place trades. Anything needing your keys, Render dashboard, or a product decision is left
for your go-ahead.
