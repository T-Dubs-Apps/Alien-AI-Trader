# 👽 Alien AI Trader

> **AI-powered stock trading on autopilot. It scans the market, picks the strongest climbers, buys on the way up, and sells before the drop.**

Built by **Troy Walker · T-Dub's Apps · 2026**

---

## ⬇️ Download — One Click to Get Started

**[→ Download latest ZIP from GitHub](https://github.com/T-Dubs-Apps/Alien-AI-Trader/archive/refs/heads/main.zip)**

No account required. No coding. Just download, extract, and double-click.

---

## 🔗 GitHub Repository

> **https://github.com/T-Dubs-Apps/Alien-AI-Trader**

Share that link with anyone who wants to install Alien AI Trader.

### Three ways to get the app from GitHub

**Option A — Download as ZIP (easiest, no Git needed)**
1. Go to **https://github.com/T-Dubs-Apps/Alien-AI-Trader**
2. Click the green **`< > Code`** button
3. Click **"Download ZIP"
4. Extract the ZIP and double-click `LAUNCH.bat`

**Option B — Direct ZIP link (share this with customers)**
```
https://github.com/T-Dubs-Apps/Alien-AI-Trader/archive/refs/heads/main.zip
```
This link always downloads the latest version.

**Option C — Clone with Git (for developers)**
```bash
git clone https://github.com/T-Dubs-Apps/Alien-AI-Trader.git
cd Alien-AI-Trader
```
Then run `LAUNCH.bat` or `INSTALL.ps1`.

---

## 🧭 Cloud or Your PC? — Which Should You Run?

There are two ways to run Alien AI Trader. **New users should start on their own PC.**

| | 💻 **On your PC** (recommended to start) | ☁️ **On Render** (cloud, 24/7) |
|---|---|---|
| **It actually runs** | Yes — while your PC is on, the engine scans and trades **non-stop**. Easiest way to watch it buy and sell. | Yes, around the clock — **but** the free tier **sleeps after ~15 min idle**, which pauses trading. |
| **Keeping it awake** | Nothing to do. | Needs a **paid instance**, or set `DASHBOARD_BASE_URL` so the built-in **keep-alive** self-ping holds it open. |
| **Cost / accounts** | Free. No hosting account. | Free tier available; paid removes spin-down. |
| **Your keys** | Never leave your computer. | Stored in your own private Render service. |
| **Best for** | Trying it out, seeing it work, full control. | Leaving it running long-term with your PC off. |

> **Why the PC is best for a new user:** the trading engine runs *inside* the app process. On a home PC that process runs continuously, so the AI keeps scanning and can actually place trades you can watch. On Render's **free** tier the service spins down when idle and the engine stops — so a brand-new user is far more likely to see it work by running it locally first, then moving to Render (paid, or with the keep-alive) once they're happy.

### 🔗 Links

| What | Link |
|------|------|
| **Get the Trader** (choose Cloud **or** PC — has everything) | `https://alien-ai-trader-dashboard.onrender.com/get` |
| **Trader on your PC** (download ZIP) | `https://github.com/T-Dubs-Apps/Alien-AI-Trader/archive/refs/heads/main.zip` |
| **Trader on Render** (deploy your own cloud copy) | `https://render.com/deploy?repo=https://github.com/T-Dubs-Apps/Alien-AI-Trader` |
| **Trader on GitHub** (source) | `https://github.com/T-Dubs-Apps/Alien-AI-Trader` |

---

## 🆕 What's New — July 2026

- **Autonomous buying, unblocked.** Fixed the causes of the engine not buying on its own: the impossible VWAP confluence gate, a dead Alpha Vantage bars fallback, and a free-tier spin-down that put the engine to sleep. Added a **keep-alive** self-ping (`KEEP_ALIVE_ENABLED`, needs `DASHBOARD_BASE_URL`).
- **Stops actually apply.** `LOSS_THRESHOLD` / `TRAILING_STOP_PCT` now accept a whole percent *or* a fraction (`4.0` and `0.04` both mean 4%), closing a boot-time window where stops read as 400%/220%.
- **Market scan on by default.** `SCAN_ALL_MARKET` now defaults to `true`, with the engine's built-in Alpaca throttles (workers capped at 2, candidates at 10, 60s floor).
- **Candlesticks page no longer rate-limits.** `/api/candles` is cached per symbol/timeframe and serves the last good bars on a `429` instead of the old "too many requests" error; the LIVE view pauses while the tab is hidden.
- **Deploy on Render without errors.** New users only need to enter `DASHBOARD_PASSWORD` — `ALLOWED_ORIGINS` and `ADMIN_API_TOKEN` are no longer fatal (they have safe fallbacks and `ADMIN_API_TOKEN` is auto-generated).
- **New tuning switches.** `SENTIMENT_GATE_ENABLED` and `FORECAST_GATE_ENABLED` let you relax the two soft entry gates if the engine is being too picky.
- **Diagnostic tool.** `python diagnose_no_buy.py --market` prints, per stock, exactly which gate is blocking a buy (read-only, never trades). Needs valid Alpaca paper keys.

---

## 🚀 Getting Started — 4 Simple Steps

> **Total time: about 5–10 minutes (most of it waiting for packages to download)**

---

### Step 1 — Download the ZIP

1. Click the download link above
2. A file called `AlienAITrader-v1.0.0.zip` (or similar) will download to your computer
3. Find it in your **Downloads** folder

---

### Step 2 — Extract the ZIP

1. Right-click the downloaded ZIP file
2. Click **"Extract All..."**
3. Click **Extract** (the default location is fine)
4. A new folder called `Alien-AI-Trader-main` will appear — open it

> **What is "extracting"?**
> A ZIP file is like a compressed envelope. Extracting unpackages everything inside it onto your computer.

---

### Step 3 — Run the Installer (1 click)

**Double-click `LAUNCH.bat`**

A black window will open. It will ask you what to do:

```
  [1] INSTALL — Copy to your PC and run full setup
  [2] RUN NOW — I already installed, just launch the app
  [3] SETUP KEYS — Re-run the API key wizard
  [4] OPEN README — Read the full documentation
  [5] EXIT

  Enter 1-5:
```

**Type `1` and press Enter.** The installer will now do everything automatically:

| What's happening | Why |
|-----------------|-----|
| Checking Windows version | Needs Windows 10 or higher |
| Installing Python 3.12 (if missing) | The programming language the app runs on |
| Choosing your install location | Default is your Desktop — just press Enter |
| Copying files | Moves everything to your chosen folder |
| Creating a virtual environment | Isolates the app's libraries from other software |
| Installing Python packages | Flask, Alpaca API, Pandas, etc. |
| Running the API Key Wizard | Sets up your free accounts (explained below) |
| Creating a Desktop shortcut | So you can launch the app daily with one click |

> **You do not need to understand any of this.** Just follow the on-screen prompts. The installer explains every step in plain English as it goes.

---

### Step 4 — Enter Your API Keys

During install, the **Setup Wizard** will open. It walks you through signing up for each service — it opens the signup pages in your browser, tells you exactly what to copy, and writes your keys file automatically.

You need accounts at these free services:

| Service | What it does | Cost |
|---------|-------------|------|
| [Alpaca Markets](https://alpaca.markets) | Executes your stock trades and provides real-time prices | Free |
| [Alpha Vantage](https://alphavantage.co) | Provides technical indicator data (RSI, SMA, etc.) | Free |
| [Pushover](https://pushover.net) | Sends push notifications to your phone | Free trial, then ~$5 one-time |
| [Twilio](https://twilio.com) | Sends SMS texts and phone call alerts | Free trial credit |
| [Pushbullet](https://pushbullet.com) | Syncs alerts across all your devices | Free |

> **Start with Alpaca Paper Trading.** Paper trading uses fake money so you can test the AI without any risk. It is approved instantly. You can flip to live trading later once you are comfortable.

> **Alerts are optional.** If you skip Pushover / Twilio / Pushbullet for now, the app still works — you just won't get phone alerts.

---

## ✅ Installation Complete — You're Ready!

After the installer finishes, you'll see:
```
  ✦  Installation Complete!  👽

  How to launch Alien AI Trader:
    • Double-click 'Alien AI Trader' on your Desktop
```

**You now have two Desktop icons:**

| Icon | What it does |
|------|--------------|
| **Alien AI Trader** | Opens the app. One double-click — the dashboard opens in your browser and the engine runs quietly in the background. No console windows, nothing to read. |
| **Alien AI Trader — Setup** | Re-run the installer or API-key wizard. Only needed when setting up or updating keys. |

**For everyday use, just double-click "Alien AI Trader."**

Your dashboard will open automatically at: **http://localhost:5000**

---

## 📅 Daily Use

### Starting the app
Double-click **"Alien AI Trader"** on your Desktop. The app starts silently — no console window — and your browser opens automatically to **http://localhost:5000**. The dashboard and trading engine run quietly in the background.

Double-clicking the icon again while it's already running just re-opens the dashboard; it won't start a second copy.

### Stopping the app
Because it runs in the background, there's no window to close. To stop it completely, open **Task Manager** (Ctrl+Shift+Esc), find **Python** under Processes, and click **End task**. Leaving it running is fine — it's lightweight and only trades during market hours.

### Re-running setup or updating your API keys
Double-click the **"Alien AI Trader — Setup"** icon (or `LAUNCH.bat`) and choose **[3] Setup Keys**.

---

## 🖥️ The Dashboard — What You're Looking At

When the app opens in your browser, you'll see several tabs:

| Tab | What it shows |
|-----|--------------|
| **Watchlist** | Live prices + AI signal (BUY / SELL / HOLD) for your stocks |
| **Live Feed** | Real-time stream of every AI decision as it happens |
| **Alerts** | Trade notifications pushed from the AI engine |
| **Trade** | Settings panel — adjust stop-loss %, capital, risk levels |
| **Top 20** | The AI's best-ranked stocks right now, scored 0–100 |
| **Portfolio** | Your capital balance, open positions, and live profit/loss |
| **Backtest** | Test the AI's strategy on historical data before going live |
| **Settings** | Engine status and advanced configuration |

### The most important controls

**Auto-Trade switch** (top of the Trade tab)
- **ON** = the AI places real orders automatically
- **OFF** = the AI scans and shows signals but does NOT trade

> Start with Auto-Trade **OFF** and watch what the AI would do for a few days before turning it on.

**Starting Capital $** (Trade tab)
- Set this to the amount of money you want the AI to manage
- Example: enter `1000` and the AI will trade with up to $1,000, sizing each position automatically
- Leave at `0` to use fixed 1-share orders instead

**Paper vs Live Trading**
- The app **always starts in Paper Mode** — all trades use fake money, so you cannot lose anything.
- Switching to **Live (real money)** happens **right inside the app** — no config files to edit. Go to **Settings → Trading Mode** and flip **Paper → Live** (you'll be asked to type `LIVE` to confirm).
- Live requires **two things**: an **active license** and your **live Alpaca keys**. Missing either? The toggle safely stays on Paper.
- **We strongly recommend staying in Paper Mode until you have watched the AI trade for at least a week.**
- 👉 Full walkthrough: **[Turning On Live Trading](#-turning-on-live-trading)** below.

---

## 💳 Plans & Pricing

Paper trading is **free forever**. A subscription unlocks **live (real-money) trading**, and **Pro** adds power features.

| Plan | Price | What you get |
|------|-------|--------------|
| **Free** | $0 | Full AI on **paper** (practice money), watchlist, backtesting |
| **Trader** | **$19.99/mo** or **$199/yr** | Everything in Free **+ live real-money trading**, up to **5** open positions |
| **Pro** | **$59/mo** or **$590/yr** | Everything in Trader **+ Scan Entire Market (~8,000 stocks), up to 15 positions, and Forecast Exit** |

> 🛡️ The **Portfolio Safety Shield** (loss protection) is included on **every** plan, including Free — safety is never behind a paywall.

**To subscribe:** in the app go to **Settings → License**, pick a plan, and check out (or use the store page at **`/get`** on your cloud dashboard). After payment you'll get an email — enter that email in **Settings → License → Activate** to unlock.

---

## 🟢 Turning On Live Trading

The app ships **safe**: it always boots in paper and will not touch real money until you deliberately turn it on. The full path:

1. **Get your live Alpaca keys.** Create/upgrade an Alpaca **live trading** account, then generate a **live** API key + secret. (Live accounts require identity verification — that's Alpaca's process, not ours.)
2. **Add your live keys:**
   - **Cloud (Render):** your service → **Environment** → add `ALPACA_LIVE_KEY` and `ALPACA_LIVE_SECRET`. Render restarts automatically.
   - **Local PC:** re-run **LAUNCH.bat → [3] Setup Keys** — the wizard now collects both paper and live keys in one pass.
3. **Activate your license.** In **Settings → License**, enter the email you used at checkout → **Activate**. The badge flips to 🟢 **Licensed**.
4. **Flip the switch.** In **Settings → Trading Mode**, change **Paper → Live** and type **`LIVE`** to confirm. A red banner confirms you're on real money.

If the license **or** the live keys are missing, the toggle refuses Live and stays on Paper — by design. To return to practice money, switch **Live → Paper** anytime (no confirmation needed).

---

## 🧠 How the AI Decides What to Buy and Sell

The AI does not guess. It uses multiple layers of analysis before placing any trade.

### Layer 1 — Technical Indicators

For every stock, the AI pulls the last 60 minutes of price bar data and calculates:

| Indicator | What it measures | How it's used |
|-----------|-----------------|--------------|
| **RSI-14** | How fast a stock is moving (momentum) | Must be below 50 to BUY — catching dips, not chasing peaks |
| **SMA-20** | 20-bar average price — short-term trend | Must be above SMA-50 (golden cross) to BUY |
| **SMA-50** | 50-bar average price — medium-term trend | Death cross (SMA20 < SMA50) triggers SELL |
| **MACD** | Convergence of moving averages | Must be bullish (MACD above signal line) to BUY |
| **Bollinger Bands** | Price volatility range | Price must be inside the bands — avoids breakout fakes |
| **VWAP** | Volume-weighted average price | Price must be near VWAP — avoids off-market spikes |

All six conditions must be true at the same time before the AI will buy.

### Layer 2 — Predictive Forecasting

Before buying, the AI runs two forecasting models on the stock's recent price data:

- **Linear Regression Forecast** — fits a trend line to recent prices and predicts where the stock will be in 5 bars. If the predicted direction is "up" with high confidence, the forecast approves the trade.
- **EMA Stacking (Momentum)** — checks whether short-term averages (EMA5, EMA10, EMA20) are stacked in the right order (price > EMA5 > EMA10 > EMA20). This pattern confirms a stock is in a sustained climb, not just a random spike.

**The AI will only buy if the forecast confirms the stock is still climbing.** If the forecast shows the momentum has already peaked, the trade is skipped.

### Layer 3 — Portfolio Ladder Scoring

---

## Production Hardening + Failover Runbook

This section is the operator checklist for secure production operation and rapid recovery.

### 1) Security hardening baseline

Set these Render env vars on the active service before going live:

- DASHBOARD_PASSWORD: strong unique password (required)
- FLASK_SECRET: generated by Render
- ALLOWED_ORIGINS: exact domain(s), comma-separated (for example: https://your-dashboard.example.com)
- ADMIN_API_TOKEN: strong token for sensitive ops APIs
- OWNER_FREEZE_TOKEN: owner lockdown token
- AUDIT_SIGNING_KEY: long random key used to sign the tamper-evident audit stream
- AUTO_FREEZE_ON_ANOMALY: true
- STRICT_PRODUCTION_GUARDS: true (recommended fail-closed startup policy)

Why this matters:

- Dashboard and control APIs require authentication
- Cross-origin API calls are blocked unless explicitly allowlisted
- Security/ops APIs require admin authorization
- Critical writes are signed in an append-only audit stream
- Suspicious write-plane behavior can auto-freeze trading
- In production, startup fails if DASHBOARD_PASSWORD, ALLOWED_ORIGINS, or ADMIN_API_TOKEN are missing
- In strict mode, ALLOWED_ORIGINS must be HTTPS origins (http://localhost and http://127.0.0.1 allowed for local testing only)

### 2) Backup + passive replica setup

On the active service set:

- BACKUP_ENABLED=true
- BACKUP_INTERVAL_SECONDS=900
- BACKUP_RETENTION=96
- BACKUP_REPLICA_URL=https://<your-passive-service-domain>
- BACKUP_REPLICA_TOKEN=<shared-secret>
- BACKUP_ENCRYPTION_KEY=<fernet-key>

On the passive service set:

- DISABLE_ENGINE_AUTOSTART=1
- BACKUP_ENABLED=false
- REPLICA_RECEIVE_TOKEN=<same shared-secret>
- DATA_DIR=/var/data with persistent disk attached

Notes:

- Active snapshots are encrypted before offsite replication
- Passive stores encrypted replicas for disaster recovery
- Audit stream is included in snapshots

### 3) Quarterly failover drill (mandatory)

1. Verify active health endpoint and audit integrity:
  - GET /health
  - GET /api/audit/verify (with admin auth)
2. Confirm passive is receiving replicas:
  - Check passive logs for /api/backup/replica success
3. Simulate failover:
  - Point DNS/router to passive service
  - Set DISABLE_ENGINE_AUTOSTART=0 on passive
  - Restart passive service
4. Validate post-promotion:
  - Engine status is healthy
  - Trading mode and safeguards are correct
  - /api/audit/verify passes
5. Declare incident mode and keep owner freeze enabled until manual sign-off.

### 4) Incident response quick actions

If you suspect abuse, compromise, or unstable behavior:

1. Enable owner freeze immediately (UI or /api/owner/freeze)
2. Rotate secrets: ADMIN_API_TOKEN, OWNER_FREEZE_TOKEN, FLASK_SECRET, broker keys
3. Keep auto-trade disabled until audit verification passes
4. Export support payload and audit status for investigation
5. Promote passive node only after root-cause containment

### 5) Financial custody boundary

Important: this app can protect configuration, logs, and control-plane operations.
Broker cash and custody assets are controlled by Alpaca systems and account controls.
Use MFA, least-privilege API keys, and provider-side security controls at all times.

Every stock in the watchlist is scored from **0 to 100** every scan cycle:

| Score Component | Weight | What it rewards |
|----------------|--------|----------------|
| RSI score | 20 pts | RSI in the buying-dip sweet spot (35–55) |
| Momentum score | 20 pts | SMA crossover strength |
| Volume score | 15 pts | Volume surge above the 20-day average (confirms the move is real) |
| Trend score | 15 pts | Price in the middle of its 52-week range (not at the very top) |
| Profit score | 15 pts | Bonus if the AI is already holding this stock and it's up |
| Forecast score | 15 pts | Linear regression + EMA stacking prediction |

Stocks are ranked highest to lowest — this is the **Ladder**. Only the **top 20%** are approved as BUY candidates. Even if all the technical signals say BUY, the AI will not enter a stock sitting in the bottom half of the ladder.

### Layer 4 — News Sentiment

The AI checks recent news headlines for each stock. If the sentiment score is negative, the BUY is blocked — no matter what the charts say.

---

## 📈 The Ladder Effect — Buy the Climb, Sell the Peak

The core strategy is simple:

1. **Buy on a confirmed upward climb** — all indicators + forecast must agree the stock is rising
2. **Hold while it keeps climbing** — the trailing stop follows the price upward, locking in gains
3. **Sell before or during the peak** — two mechanisms protect your profits:

### Trailing Stop (your main protection)
- The AI tracks the **highest price reached** since purchase (the "peak")
- When the price drops more than X% below that peak, the AI sells automatically
- Default: 3% drop from peak triggers a sell
- You can adjust this in the Trade tab

```
Example with 3% trailing stop:
  Buy  @ $100.00
  Peak @ $140.00  →  sell trigger moves to $135.80
  Peak @ $160.00  →  sell trigger moves to $155.20
  Price drops to $155.20  →  AI SELLS
  You captured a +55.2% gain
```

### Forecast Exit (sells before the trailing stop fires)
When the AI detects that momentum has **reversed** — the forecast flips from "up" to "down" and the EMA pattern shows the stock is now in a "falling" phase — it sells immediately, before the price actually drops enough to trigger the trailing stop. This gets you out closer to the actual top.

You can toggle this on/off in the Trade tab under **"Forecast Exit."**

### Stop-Loss (worst case protection)
If a stock drops more than X% from your buy price without ever rising, the AI exits immediately. Default: 5% loss from entry. This prevents a bad trade from getting worse.

---

## ⚙️ Complete Settings Reference & Trading Guide

All settings can be changed live from the Trade tab — no restart needed, and everything is saved automatically. This section explains **every setting, what it does, and how it affects your trading.** *(Also available as a printable standalone file: [`SETTINGS_GUIDE.md`](SETTINGS_GUIDE.md).)*

> **The one thing to remember:** the bot's job is to **buy stocks that are dipping inside an uptrend, protect them with automatic stop‑losses, and sell them near the top or at a profit target.** Every setting just tunes *how cautious or aggressive* it is at doing that. **No setting turns off the safety stops** — those always protect you.

### How the bot works in 30 seconds

1. **Scans** stocks on a timer (your watchlist, or the whole market).
2. **Buys** when a stock looks like a good dip in an uptrend and passes your filters.
3. **Watches** each holding continuously and tracks its highest price.
4. **Sells** at a profit target, when momentum rolls over, or when a protective stop triggers.

### ⭐ The Risk Slider (1–10) — your master control

Moving it and pressing **Apply** overwrites **nine settings at once** — how picky it is about buying, how big each trade is, and how much of your cash it deploys. **Level 5 is the balanced default.**

| Level | Name | Risk / trade | Max in one stock | Max invested | Cash held back |
|------:|------|:-----------:|:---------------:|:------------:|:--------------:|
| 1 | Very Conservative | 0.5% | 8% | 55% | 45% |
| 2 | Conservative | 0.75% | 10% | 60% | 40% |
| 3 | Cautious | 1.0% | 12% | 65% | 35% |
| 4 | Moderate | 1.5% | 16% | 70% | 30% |
| **5** | **Balanced (default)** | **2.0%** | **20%** | **75%** | **25%** |
| 6 | Growth | 2.3% | 23% | 80% | 20% |
| 7 | Assertive | 2.6% | 26% | 85% | 15% |
| 8 | Aggressive | 3.0% | 29% | 90% | 10% |
| 9 | Very Aggressive | 3.5% | 32% | 95% | 5% |
| 10 | Maximum | 4.0% | 35% | 100% | 0% |

Low numbers = fewer, smaller, safer trades with lots of cash in reserve. High numbers = more trades, bigger positions, nearly all your money invested. At **8+** it adds "buy the drastic dip" entries; at **9–10** it waives the forecast‑up requirement and the exposure guard stops blocking (it may deploy up to 100%).

### 1. Master switches

| Setting | Default | What it does & how it affects trading |
|---|---|---|
| **Auto‑Trade** | ON | Master on/off. ON = places real buy/sell orders. OFF = scans and shows signals but places no orders (watch‑only). |
| **Paper / Live mode** | Paper | **Paper** = practice money, zero risk. **Live** = real brokerage money (license‑gated). Always start on Paper. |
| **Market Hours Only** | ON | ON = trades only 9:30 AM–4:00 PM ET. OFF = also trades pre/after‑hours (thinner, riskier). |

### 2. How it decides to BUY

| Setting | Default | What it does & how it affects trading |
|---|---|---|
| **Scan Entire Market** | ON | ON = hunts the whole US market (rotating through all qualified stocks so it covers everything over time). OFF = only your watchlist. |
| **RSI Buy Max** | 60 | RSI = overbought/oversold gauge (0–100). Only buys when RSI is **below** this — it buys **dips**, not tops. Lower = pickier. |
| **SMA Spread Min** | 0.1% | Requires the fast 20‑day average to be this far above the slow 50‑day average before buying — confirms an uptrend. Higher = demands a stronger trend. |
| **Max Positions** | 5 | Most stocks held at once. Higher = more diversification, smaller slices. |
| **Min Positions** | 5 | Spreads capital: divides your money by this to cap how expensive one share can be. Higher = cheaper stocks, spread thinner. |
| **Rocket Breakout Mode** | ON | Also chases **explosive momentum movers**, not just dips. Sub‑settings: Min Day Change % (12), Volume Surge × (1.5), Min Avg Volume (150k), Max % Above SMA20 (35), Lookback Bars (20). |
| **Forecast filter** | ON | For **risky** stocks it won't buy unless the price forecast points **up** — the "don't catch a falling knife" guard. Waived at slider 9–10. |

### 3. How MUCH it buys (position sizing)

| Setting | Default | What it does & how it affects trading |
|---|---|---|
| **Starting Capital $** | 0 (auto) | The money pool it manages. **0 = auto** (sizes to your real balance). A number caps it to that amount. |
| **Risk Per Trade %** | 2% | Share of capital per trade. 2% of $1,000 ≈ $20/trade. Higher = bigger bets. |
| **Max Position %** | 20% | No single stock may exceed this share of capital — prevents over‑concentration. |
| **Risk Per Trade $** | 0 | Optional **fixed dollar** amount per trade instead of a % (0 = use the %). |

### 4. How it SELLS — protecting gains and taking profit

Several exits work together; whichever triggers first wins.

| Setting | Default | What it does & how it affects trading |
|---|---|---|
| **Trailing Stop %** | 6% | Rides **up** with the price and sells if it falls this % **from its peak** since you bought. Your main "let it run, then protect the gain" tool. Tighter (3%) = sells closer to the peak but exits on smaller wiggles. |
| **Trailing Activation %** | 3% | The trailing stop only **switches on** after the stock is up this much, and its trigger is floored at your cost — so **the trailing stop never sells below what you paid.** |
| **Stop‑Loss %** | 8% | The disaster floor: sells if a stock drops this % below your buy price. The **only** exit allowed to sell below cost. |
| **Take‑Profit %** | 0 (off) | Auto‑sells once up this %. The most reliable "sell high" — locks in a set gain before any drop. Trade‑off: caps a bigger run. |
| **Min Hold (min)** | Cash 5 / Margin 360 | Smallest time to hold before the **smart** exits (take‑profit, forecast, signal) may fire. Emergency stop‑loss/trailing always fire. Cash keeps it low for same‑day exits; margin high to avoid day‑trade (PDT) flags. |
| **Forecast Exit** | ON | Sells **before** the trailing stop when the forecast says momentum peaked — aims to exit nearer the top. |
| **RSI Sell Min** | 70 | Sells (while in profit) when RSI climbs above this — overbought, likely to pull back. |

### 5. Safety guards (hard limits)

| Setting | Default | What it does & how it affects trading |
|---|---|---|
| **Max Gross Exposure %** | slider (75% at L5) | The most of your capital that may be invested at once. Blocks new buys past this. Scales with the risk slider (100% at level 10). |
| **Min Cash Reserve %** | slider (25% at L5) | Minimum cash kept un‑invested — the mirror of the above. |
| **Portfolio Safety Shield** | Off (0) | Whole‑account circuit breaker: if your **total portfolio value** falls to this dollar amount, it **halts all new buys.** Set the dollar floor to enable; 0 = off. Resume Buffer $ (200) = how far it must recover before buying resumes. |
| **Max Trades / Hour** | 30 | Rate limiter so it can never go on a runaway spree. |

### 6. Range Trader (opt‑in "buy low, sell high")

Buys near the **bottom** of a stock's daily range and sells near the **top**. **Always OFF by default** — it turns itself off on every restart, page refresh, and at market close, so it never runs unattended. Settings: Enable (off), Mode (auto/manual/both), Drop window (2 h, in 30‑min steps), Buy on drop # (4, adjustable), Drop size % (1%), Also run after‑hours (off).

### 7. Scan & account

| Setting | Default | What it does & how it affects trading |
|---|---|---|
| **Scan Interval (sec)** | 60 | How often it checks the market. Minimum 60s to stay under the data provider's rate limit. |
| **Account Type** | Cash | **Cash** = no day‑trade limit, spends only settled funds (safer, fast same‑day exits). **Margin** = day‑trade rules under $25k, holds longer. Match your real brokerage account. |

### 📖 Glossary — trading terms in plain English

- **RSI (Relative Strength Index):** 0–100 gauge of overbought (high) vs oversold (low). The bot buys low RSI (dips), sells high RSI (overbought).
- **SMA (Simple Moving Average):** average price over N days. SMA20 crossing above SMA50 = "golden cross" = uptrend; the reverse = "death cross."
- **VWAP (Volume‑Weighted Average Price):** volume‑weighted "fair value" line. Buying at/below it = buying a discount, not chasing.
- **MACD:** momentum indicator; line above its signal line = bullish momentum.
- **Bollinger Bands:** a price envelope; near the lower band = cheap, near the upper = stretched.
- **Trailing stop:** a sell trigger that rides **up** with price and fires when it falls a set % from the peak.
- **Stop‑loss / Take‑profit:** a fixed floor below / target above your buy price.
- **Exposure / Cash reserve:** the % of your money invested vs. held safe.
- **PDT (Pattern Day Trader):** a US rule limiting frequent same‑day round‑trips on **margin** accounts under $25k. Cash accounts are exempt — which is why they can sell faster.
- **Dip / pullback:** a temporary drop inside a larger uptrend — what the bot tries to buy.

### ✅ A safe starting configuration

- **Mode:** Paper until you trust it · **Risk Slider:** 5 (Balanced)
- **Trailing Stop:** 6% · **Stop‑Loss:** 8% · **Take‑Profit:** 5% (optional)
- **Min Hold:** 5 min (cash) · **Max Positions:** 5
- **Scan Entire Market:** ON · **Auto‑Trade:** ON
- **Portfolio Safety Shield:** set a dollar floor you won't drop below

> **No setting can guarantee a profit** — markets move on their own. What these settings *do* guarantee is that the bot buys with discipline and always protects each position with automatic stops.

---

## 🔔 Mobile Alerts

The app can notify your phone when trades happen, when a stock crashes after hours, or when your portfolio hits a new all-time high.

| Channel | Alert type | Setup |
|---------|-----------|-------|
| **Pushbullet** | Every trade, every signal | pushbullet.com → Settings → Access Token |
| **Pushover** | Crash alerts (breaks Do Not Disturb) | pushover.net → Create App |
| **Twilio** | Phone call during after-hours crash | twilio.com → Console |

---

## ☁️ Runs in the Cloud Too (Easiest for Most People)

Most people run Alien AI Trader **in the cloud on Render** — nothing to install, no PC left on, and the AI trades 24/7.

**Store / download page:** **https://alien-ai-trader-dashboard.onrender.com/get**

From there you can:
- **⬇️ Download Your Personal Trader** — grab the installer for a home-PC setup, or
- **☁️ Deploy Your Own on Render** — one click spins up **your own** private cloud copy. Render prompts you for your keys (Alpaca paper + optional live, Alpha Vantage); paste them in and deploy.

Your instance is **entirely yours** — your keys, your account, your trades. Nothing is shared. See the **Render Deployment** section below for the manual route.

---

## 🌐 Render Cloud Deployment (Advanced)

This section is for users who want to run the app in the cloud. Skip this if you just want to run it on your own PC.

The app deploys as a **single service** on Render via `render.yaml` — the AI trading
engine runs inside the dashboard process, so there is nothing else to set up (and
nothing else to pay for):

| Service | Type | What it does |
|---------|------|-------------|
| `alien-ai-trader-dashboard` | Web Service | Flask dashboard + API + WebSocket + AI trading engine |

**Steps:**
1. Fork this repository on GitHub (or use your own copy)
2. Go to [render.com](https://render.com) → New → Blueprint
3. Connect your forked repo
4. Render will find `render.yaml` and create the service automatically
5. Set your environment variables (API keys) in the Render dashboard

> **Critical Render tip (easy to miss):** after changing Environment Variables,
> use Render's **Save and deploy** (or **Save, rebuild and deploy**) button in
> the Env Vars panel. Triggering a deploy from the top-level manual deploy menu
> can redeploy the previous code commit without applying your new env values.

**After changing keys, always verify in this order:**
1. Open Render Env Vars and confirm the saved values are still present.
2. Deploy via **Save and deploy** (or **Save, rebuild and deploy**).
3. Check `https://YOUR-SERVICE.onrender.com/api/engine/diag`.
4. Confirm `alpaca_paper.authorized=true` before trusting trading status.

> **Tip:** every user can run their own private cloud copy this way — your keys,
> your account, your trades. Nothing is shared.

If you want the app to behave more like a self-monitoring system, see
[AI_GUARDIAN_ROADMAP.md](AI_GUARDIAN_ROADMAP.md) for the recommended build order.

### Recommended Blueprint Defaults (Production-Safe)

These defaults are chosen to maximize stability, reduce accidental risk, and
keep API usage predictable for most users:

1. `TRADING_MODE=paper` and `LIVE_TRADING_ENABLED=false`
2. `MARKET_HOURS_ONLY=true` (strategy loop pauses when market is closed)
3. `POLL_SECONDS=60` (steadier API usage than 15/30 second loops; this is also the engine's hard floor)
4. `SCAN_ALL_MARKET=true` (full-market momentum scanning is now **on by default**; the engine caps scan workers at 2 and candidates at 10 so it stays within Alpaca's limits)
5. `MAX_TRADES_PER_HOUR=20` (throttle; still well under burst limits)
6. `RUN_SECONDS=21540` (5h59m recycle keeps sessions healthy while reconciling positions on restart)

Why this profile works:

1. Keeps all new deployments safe in paper mode by default.
2. Prevents off-hours surprises unless the user explicitly enables them.
3. Reduces API burst and timeout risk across many customer blueprints.
4. Gives the safest baseline before scaling to live mode.

---

## ⚙️ All Environment Variables (Advanced Reference)

### Required API Keys
| Variable | Where to get it |
|----------|----------------|
| `ALPACA_KEY` | alpaca.markets → **Paper** API Keys |
| `ALPACA_SECRET` | alpaca.markets → **Paper** API Keys |
| `ALPACA_LIVE_KEY` | alpaca.markets → **Live** API Keys — *optional; enables the in-app Live toggle* |
| `ALPACA_LIVE_SECRET` | alpaca.markets → **Live** API Keys — *optional* |
| `ALPHA_VANTAGE_KEY` | alphavantage.co → Free API Key |
| `PUSHOVER_TOKEN` | pushover.net → Create App |
| `PUSHOVER_USER` | pushover.net → Your User Key |
| `TWILIO_ACCOUNT_SID` | twilio.com → Console |
| `TWILIO_AUTH_TOKEN` | twilio.com → Console |
| `TWILIO_FROM_NUMBER` | Your Twilio phone number (+1XXXXXXXXXX) |
| `TWILIO_TO_NUMBER` | Your personal phone number (+1XXXXXXXXXX) |
| `PUSHBULLET_API_KEY` | pushbullet.com → Settings → Access Token |

### Trading Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `TRADING_MODE` | `paper` | **Boot mode only.** The real control is the in-app **Paper↔Live toggle** (license-gated). Leave as `paper`. |
| `LIVE_TRADING_ENABLED` | `false` | Legacy safety flag. Live is now gated by your **license + live keys**, not this. |
| `POLL_SECONDS` | `60` | Scan interval in seconds (recommended baseline for stability) |
| `MAX_POSITIONS` | `5` | Max simultaneous open positions |
| `INITIAL_CAPITAL` | `0` | Starting capital $ (0 = fixed 1-share mode) |
| `RISK_PER_TRADE_PCT` | `2.0` | % of capital risked per trade |
| `MAX_POSITION_PCT` | `20.0` | Max % in any single stock |
| `TRAILING_STOP_PCT` | `3.0` | % drop from peak before selling. **Accepts a whole percent OR a fraction** — `2.2` and `0.022` both mean 2.2%. |
| `LOSS_THRESHOLD` | `5.0` | % drop from buy price before stop-loss. Same percent-or-fraction rule as above. |
| `FORECAST_EXIT_ENABLED` | `true` | Sell early on momentum reversal |
| `RUN_SECONDS` | `21540` | Session length — 5h 59m (under API limits) |
| `MAX_TRADES_PER_HOUR` | `20` | Trade throttle |
| `MARKET_HOURS_ONLY` | `true` | Pause strategy loop outside market hours |
| `SCAN_ALL_MARKET` | `true` | Scan all US equities for momentum movers (**on by default**) |
| `SENTIMENT_GATE_ENABLED` | `true` | Blocks a buy on negative news. Set `false` to relax if the engine isn't entering. |
| `FORECAST_GATE_ENABLED` | `true` | Requires an up-forecast on high-risk entries. Set `false` to relax. |
| `KEEP_ALIVE_ENABLED` | `true` | Self-pings your public URL so a free-tier host doesn't spin down and stop trading. Needs `DASHBOARD_BASE_URL` set to your public URL. |
| `KEEP_ALIVE_INTERVAL_SECONDS` | `600` | How often the keep-alive ping fires (seconds). |
| `DASHBOARD_BASE_URL` | *(unset)* | Your public app URL (e.g. `https://your-app.onrender.com`). Required for the keep-alive; also used for internal links. |

---

## 📁 Project Files (Reference)

```
Alien_AI_Trader/
├── Alien AI Trader.vbs     ← Silent launcher (what the Desktop icon runs)
├── _server.bat             ← Runs the app hidden (used by the launcher)
├── _open_browser.bat       ← Opens the dashboard once the server is ready
├── LAUNCH.bat              ← Setup / installer menu
├── START.bat               ← Visible launcher (fallback)
├── INSTALL.ps1             ← Full automated installer
├── dashboard.py            ← Web server + dashboard + API + AI trading engine
├── trading_engine.py       ← AI brain: signals, buy/sell, position sizing
├── license_signing.py      ← Verifies your license is genuine (public key)
├── portfolio_ladder.py     ← Ladder scorer: ranks all stocks 0-100
├── forecasting.py          ← Predictive forecasting: regression + EMA stacking
├── setup_wizard.py         ← API key setup wizard
├── config_loader.py        ← Loads keys from env or config.json
├── backtest.py             ← Strategy backtesting engine
├── requirements.txt        ← Python package list
├── render.yaml             ← Cloud deployment blueprint (Render.com)
├── keys.bat                ← YOUR private API keys (never share this file!)
├── legacy/
│   └── worker.py           ← Old standalone engine (no longer used — kept for reference)
└── templates/
    └── dashboard.html      ← Dashboard web interface
```

---

## 🔒 Security — Keep Your Keys Safe

**Never share these files with anyone:**
- `keys.bat` — contains all your API keys
- `.env` — alternative key storage
- `config.json` — your configuration

These files are excluded from GitHub automatically by `.gitignore`. The app will never upload them anywhere.

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Web server | Flask + Flask-SocketIO |
| Real-time updates | Socket.IO (WebSocket) |
| Trading execution | Alpaca Trade API |
| Market data | Alpha Vantage |
| Technical analysis | Pandas (RSI-14, SMA, MACD, Bollinger, VWAP) |
| Predictive forecasting | NumPy linear regression + EMA stacking |
| Portfolio scoring | Custom ladder scorer (0-100 composite) |
| Charts | Chart.js |
| UI | Bootstrap 5 + Font Awesome |
| Mobile alerts | Pushbullet · Pushover · Twilio |
| Cloud deployment | Render.com (single web service blueprint) |

---

## ⚠️ Disclaimer

This software is for educational and paper trading purposes only. Troy Walker and T-Dub's Apps are not financial advisors. Always test thoroughly in **paper trading mode** before enabling live trading. Past performance of any algorithm does not guarantee future results. Real-money trading involves substantial risk of loss. Trade responsibly.

---

## 🔤 Glossary — Trading Terms & Features Explained

A plain-English reference for every trading concept and feature used in the app — useful for explaining to someone else (like a family member) what the AI is actually doing.

### Technical Indicators (Layer 1)

| Term | What it means | How this app uses it |
|---|---|---|
| **RSI (Relative Strength Index)** | A 0–100 score measuring how fast a stock has been rising or falling recently. Low = oversold/dip, high = overbought/peaked. | Calculated as RSI-14 (14-bar lookback). Must be below 50 to BUY (catching dips, not chasing highs). Selling kicks in above the RSI Sell Min setting (default 70). |
| **SMA (Simple Moving Average)** | The average price over the last X bars — smooths out noise to show the underlying trend. | Uses SMA-20 (short-term) and SMA-50 (medium-term). SMA-20 above SMA-50 = uptrend confirmation. |
| **Golden Cross** | When a short-term average (SMA-20) crosses above a longer-term average (SMA-50) — a classic bullish trend signal. | Required for a BUY. A "SMA Spread Min %" setting filters out weak, razor-thin crossovers so the app doesn't act on noise. |
| **Death Cross** | The opposite of a golden cross — SMA-20 drops below SMA-50, signaling the trend has turned down. | Triggers a SELL signal. |
| **MACD (Moving Average Convergence Divergence)** | Compares two moving averages to show whether momentum is building or fading. | Must be "bullish" (MACD line above its signal line) before the AI will BUY. |
| **Bollinger Bands** | A price channel built around a moving average that widens and narrows with volatility. | Price must stay inside the bands to BUY — keeps the AI from chasing a sudden breakout spike that might reverse. |
| **VWAP (Volume-Weighted Average Price)** | The average price a stock has traded at today, weighted by how much volume traded at each price. | Price must stay near VWAP to BUY — avoids buying into off-market or low-volume price spikes. |

All six of the above must agree before the AI buys anything — it's an "all conditions must be true" filter, not a majority vote.

### Forecasting (Layer 2)

| Term | What it means | How this app uses it |
|---|---|---|
| **Linear Regression Forecast** | A statistical best-fit line drawn through recent prices, used to project where the price is headed next. | Predicts the price 5 bars ahead. If it points up with high confidence, the forecast approves the trade. |
| **EMA (Exponential Moving Average)** | Like an SMA, but weights recent prices more heavily — reacts faster to new price action. | Uses EMA5, EMA10, EMA20. |
| **EMA Stacking** | When EMA5 > EMA10 > EMA20 > current trend is genuinely climbing in an orderly way, not just spiking. | Confirms sustained momentum rather than a random one-bar pop, before the AI will buy. |

### Portfolio Ladder Scoring (Layer 3)

| Term | What it means |
|---|---|
| **The Ladder** | Every stock on the watchlist gets scored 0–100 each scan cycle, then ranked top to bottom. Only the top 20% of the ranking are eligible to BUY — even if a stock passes every other check, it's skipped if it's not near the top of the ladder. |
| **Volume Score** | Rewards a stock when its trading volume surges above its 20-day average — a sign the move is backed by real buying interest, not a fluke. |
| **Trend Score** | Rewards stocks trading in the middle of their 52-week price range, rather than ones already near their yearly high. |
| **Profit Score** | A bonus if the AI is already holding the stock and it's currently profitable. |

### News Sentiment (Layer 4)

| Term | What it means |
|---|---|
| **Sentiment Score** | A score derived from recent news headlines about a stock. A negative score blocks a BUY outright, regardless of how good the charts look. |

### Exit Strategy ("The Ladder Effect")

| Term | What it means |
|---|---|
| **Trailing Stop** | The AI tracks the highest price reached since you bought ("the peak") and automatically sells once price falls a set % below that peak (default 3%). This locks in gains as a stock climbs, without capping the upside. |
| **Forecast Exit** | Sells immediately when the forecast and EMA stacking flip from "rising" to "falling" — gets you out near the actual top, before the trailing stop would have triggered. Toggleable in the Trade tab. |
| **Stop-Loss** | A hard safety net: if price falls a set % below your original purchase price (default 5%) without ever rising, the AI exits immediately. Caps the damage from a trade that simply never worked out. |

### Order & Account Terms

| Term | What it means |
|---|---|
| **GTC (Good-Til-Cancelled)** | An order type that stays open until it's filled or manually cancelled (rather than expiring at end of day). Used for protective stop orders placed when the market is closed. |
| **Paper Trading** | Simulated trading with fake money — free, used for testing strategies with zero financial risk. |
| **Live Trading** | Real trades placed with real money through your actual Alpaca brokerage account. Requires a license to unlock. |
| **ROI (Return on Investment)** | Your session's profit or loss, shown as a percentage of your starting capital. |
| **Position Sizing** | How much money the AI puts into each trade — governed by Risk Per Trade %, Max Position %, and Min/Max Positions settings, so no single stock can blow up the whole portfolio. |
| **Drawdown** | The drop from a portfolio's peak value to a subsequent low — a measure of "how bad did it get" during a losing stretch. Reported in backtests. |
| **Watchlist** | The list of stocks you've chosen for the AI to actively monitor and trade (as opposed to "Scan Entire Market," which checks all ~8,000 US stocks). |

### Alerts & Connectivity

| Term | What it means |
|---|---|
| **DND (Do Not Disturb)** | Your phone's silent-mode setting. Pushover alerts are configured to break through DND so you don't miss a crash alert even with your phone silenced. |
| **Heartbeat** | A periodic "I'm still alive" signal the background worker sends to the dashboard, so the UI can tell whether the trading engine is actually running or has silently died. |
| **Crash Alert** | A phone call/text triggered when a held stock is dropping sharply after hours, when the AI itself can't place a protective trade because the market is closed. |

---

## ❓ Frequently Asked Questions

**Q: Do I need to know how to code?**
No. The installer handles everything automatically. You just follow the on-screen prompts.

**Q: Is this free?**
**Paper trading is free forever** — full AI, no cost, no risk. **Live (real-money) trading** requires a subscription: **Trader** ($19.99/mo or $199/yr) or **Pro** ($59/mo or $590/yr) — see [Plans & Pricing](#-plans--pricing). The data services it uses (Alpaca, Alpha Vantage) have free tiers; Twilio/Pushover phone alerts are optional with small costs.

**Q: Can I lose real money?**
Not in Paper Mode (the default). Paper trading uses fake money. You have to manually switch to Live Mode, which requires an approved Alpaca live trading account.

**Q: What stocks does the AI trade?**
By default it monitors Apple, Google, Tesla, Microsoft, and Amazon. You can add any US stock ticker in the Settings tab. Turn on "Scan Entire Market" to let the AI hunt through all 8,000+ US equities.

**Q: How does the 5h 59m restart work?**
Alpaca's free API has hourly usage limits. The engine automatically recycles its scan session every 5 hours and 59 minutes to stay within those limits. When it restarts, it reads your open positions back from your Alpaca account, so the dashboard returns exactly as it was — your holdings and settings carry over. Only the internal scan session resets.

**Q: What if the app crashes?**
The engine has a built-in crash recovery supervisor. If the trading engine or ladder scanner thread dies unexpectedly, it is automatically restarted and you get an alert.

**Q: Why does the dashboard say "Paused"?**
The engine only trades during US market hours (9:30 AM–4:00 PM Eastern, Monday–Friday). Outside those hours it shows a yellow **Paused** badge and waits — this is normal and saves API usage. It resumes automatically when the market opens.

**Q: Can I run this on a Mac or Linux?**
The installer (LAUNCH.bat, INSTALL.ps1) is Windows-only. The Python code itself runs on any platform — Mac/Linux users can run `python dashboard.py` in a terminal after installing requirements with `pip install -r requirements.txt`. The trading engine starts automatically inside it.

---

*Built with care by Troy Walker · T-Dub's Apps · 2026*
