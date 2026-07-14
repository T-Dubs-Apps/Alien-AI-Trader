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

## ⚙️ Adjusting the Settings (Trade Tab)

All settings can be changed live — no restart needed.

| Setting | Default | What it does |
|---------|---------|-------------|
| Trailing Stop % | 3% | How far from the peak before the AI sells |
| Stop-Loss % | 5% | Maximum loss from buy price before forced exit |
| Scan Interval | 15s | How often the AI scans every stock |
| Starting Capital $ | 0 | Total money the AI manages (0 = 1-share fixed mode) |
| Risk Per Trade % | 2% | Max % of capital on any single trade |
| Max Position % | 20% | Max % of capital in any single stock |
| Min Positions | 5 | Capital is spread across at least this many stocks |
| Max Trades/Hour | 30 | Rate limiter — prevents runaway trading |
| Max Positions | 5 | Max number of stocks held at once |
| RSI Buy Max | 50 | Only buy when RSI is below this number |
| RSI Sell Min | 70 | Signal-based sell when RSI exceeds this |
| Forecast Exit | ON | Sell early when forecast shows momentum reversing |
| Scan Entire Market | OFF | Scan all 8,000+ US stocks, not just your watchlist |

> **All settings are saved automatically.** If the app restarts, your settings are restored exactly as you left them.

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
3. `POLL_SECONDS=60` (steadier API usage than 15/30 second loops)
4. `SCAN_ALL_MARKET=false` initially (turn on only after validation)
5. `MAX_TRADES_PER_HOUR=6` (reduces overtrading and runaway behavior)
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
| `TRAILING_STOP_PCT` | `3.0` | % drop from peak before selling |
| `LOSS_THRESHOLD` | `5.0` | % drop from buy price before stop-loss |
| `FORECAST_EXIT_ENABLED` | `true` | Sell early on momentum reversal |
| `RUN_SECONDS` | `21540` | Session length — 5h 59m (under API limits) |
| `MAX_TRADES_PER_HOUR` | `6` | Trade throttle (recommended baseline) |
| `MARKET_HOURS_ONLY` | `true` | Pause strategy loop outside market hours |
| `SCAN_ALL_MARKET` | `false` | Scan all US equities for momentum movers |

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
