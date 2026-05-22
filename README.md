# 👽 Alien AI Trader

> **AI-powered stock trading on autopilot. It scans the market, picks the strongest climbers, buys on the way up, and sells before the drop.**

Built by **Troy Walker · T-Dub's Apps · 2026**

---

## ⬇️ Download — One Click to Get Started

**[→ Click here to download the latest version (ZIP)](../../releases/latest)**

No account required. No coding. Just download, extract, and double-click.

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
4. A new folder called `Alien_AI_Trader` will appear — open it

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
    • OR double-click START.bat
```

**From now on, just double-click the "Alien AI Trader" shortcut on your Desktop.**

Your dashboard will open automatically at: **http://localhost:5000**

---

## 📅 Daily Use

### Starting the app
Double-click **"Alien AI Trader"** on your Desktop.

Two windows will open (the Dashboard server and the Trading Worker). Your browser will open automatically to the dashboard. **Do not close those windows** while the app is running.

### Stopping the app
Close both console windows — the one labeled **Dashboard** and the one labeled **Worker**.

### Re-running setup or updating your API keys
Double-click `LAUNCH.bat` and choose **[3] Setup Keys**.

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
| **Settings** | Worker status and advanced configuration |

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
- The app starts in **Paper Mode** — all trades use fake money, so you cannot lose anything
- To switch to live trading, you must explicitly set `TRADING_MODE=live` in your settings AND enable `LIVE_TRADING_ENABLED=true`
- **We strongly recommend staying in Paper Mode until you have watched the AI trade for at least a week**

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

## ☁️ Runs in the Cloud Too

If you want the AI trading 24/7 without your PC being on, you can deploy it to **Render.com** for free.

The cloud dashboard is already live at:
**https://alien-ai-trader-dashboard.onrender.com**

To deploy your own instance, see the **Render Deployment** section below.

---

## 🌐 Render Cloud Deployment (Advanced)

This section is for users who want to run the app in the cloud. Skip this if you just want to run it on your own PC.

The app deploys as two services on Render via `render.yaml`:

| Service | Type | What it does |
|---------|------|-------------|
| `alien-ai-trader-dashboard` | Web Service | Flask dashboard + API + WebSocket |
| `alien-ai-trader-worker` | Background Worker | Trading engine + ladder scanner |

**Steps:**
1. Fork this repository on GitHub
2. Go to [render.com](https://render.com) → New → Blueprint
3. Connect your forked repo
4. Render will find `render.yaml` and create both services automatically
5. Set your environment variables (API keys) in the Render dashboard

---

## ⚙️ All Environment Variables (Advanced Reference)

### Required API Keys
| Variable | Where to get it |
|----------|----------------|
| `ALPACA_KEY` | alpaca.markets → API Keys |
| `ALPACA_SECRET` | alpaca.markets → API Keys |
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
| `TRADING_MODE` | `paper` | `paper` or `live` |
| `LIVE_TRADING_ENABLED` | `false` | Second safety switch — must be `true` for live |
| `POLL_SECONDS` | `15` | Scan interval in seconds |
| `MAX_POSITIONS` | `5` | Max simultaneous open positions |
| `INITIAL_CAPITAL` | `0` | Starting capital $ (0 = fixed 1-share mode) |
| `RISK_PER_TRADE_PCT` | `2.0` | % of capital risked per trade |
| `MAX_POSITION_PCT` | `20.0` | Max % in any single stock |
| `TRAILING_STOP_PCT` | `3.0` | % drop from peak before selling |
| `LOSS_THRESHOLD` | `5.0` | % drop from buy price before stop-loss |
| `FORECAST_EXIT_ENABLED` | `true` | Sell early on momentum reversal |
| `RUN_SECONDS` | `21540` | Session length — 5h 59m (under API limits) |
| `SCAN_ALL_MARKET` | `false` | Scan all US equities for momentum movers |

---

## 📁 Project Files (Reference)

```
Alien_AI_Trader/
├── LAUNCH.bat              ← Start here — installer menu
├── START.bat               ← Daily launch (after install)
├── INSTALL.ps1             ← Full automated installer
├── dashboard.py            ← Web server + dashboard + API
├── trading_engine.py       ← AI brain: signals, buy/sell, position sizing
├── worker.py               ← Background runner: engine + ladder scanner
├── portfolio_ladder.py     ← Ladder scorer: ranks all stocks 0-100
├── forecasting.py          ← Predictive forecasting: regression + EMA stacking
├── setup_wizard.py         ← API key setup wizard
├── config_loader.py        ← Loads keys from env or config.json
├── backtest.py             ← Strategy backtesting engine
├── requirements.txt        ← Python package list
├── render.yaml             ← Cloud deployment blueprint (Render.com)
├── keys.bat                ← YOUR private API keys (never share this file!)
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
| Cloud deployment | Render.com (web + worker blueprint) |

---

## ⚠️ Disclaimer

This software is for educational and paper trading purposes only. Troy Walker and T-Dub's Apps are not financial advisors. Always test thoroughly in **paper trading mode** before enabling live trading. Past performance of any algorithm does not guarantee future results. Real-money trading involves substantial risk of loss. Trade responsibly.

---

## ❓ Frequently Asked Questions

**Q: Do I need to know how to code?**
No. The installer handles everything automatically. You just follow the on-screen prompts.

**Q: Is this free?**
The app is free. The services it connects to (Alpaca, Alpha Vantage) have free tiers that are sufficient for paper trading. Twilio and Pushover have small one-time costs for phone alerts — these are optional.

**Q: Can I lose real money?**
Not in Paper Mode (the default). Paper trading uses fake money. You have to manually switch to Live Mode, which requires an approved Alpaca live trading account.

**Q: What stocks does the AI trade?**
By default it monitors Apple, Google, Tesla, Microsoft, and Amazon. You can add any US stock ticker in the Settings tab. Turn on "Scan Entire Market" to let the AI hunt through all 8,000+ US equities.

**Q: How does the 5h 59m restart work?**
Alpaca's free API has hourly usage limits. The worker automatically restarts every 5 hours and 59 minutes to stay within those limits. Your settings, open positions, and trade history are all preserved — only the internal scan session resets.

**Q: What if the app crashes?**
The worker has a built-in crash recovery loop. If the trading engine or ladder scanner thread dies unexpectedly, the worker automatically restarts it and sends you an alert.

**Q: Can I run this on a Mac or Linux?**
The installer (LAUNCH.bat, INSTALL.ps1) is Windows-only. The Python code itself runs on any platform — Mac/Linux users can run `python dashboard.py` and `python worker.py` directly in separate terminals after installing requirements with `pip install -r requirements.txt`.

---

*Built with care by Troy Walker · T-Dub's Apps · 2026*
