# 👽 Alien AI Trader

A real-time AI-powered stock trading dashboard with automated buy/sell logic, live WebSocket updates, RSI + SMA technical analysis, trailing stop, compound reinvestment, portfolio ladder scoring, and multi-channel mobile alerts.

Built by **Troy Walker of T-Dub's Apps — 2026**

---

## 🚀 Quick Start (New Users — Start Here)

### Step 1 — Install (first time only)
```
Right-click INSTALL.ps1 → Run with PowerShell
```
This automatically:
- Checks for Python 3.10+ and installs it if missing (via winget or python.org)
- Upgrades pip
- Creates a `.venv` virtual environment
- Installs all dependencies from `requirements.txt`
- Checks for your API keys configuration

### Step 2 — Set Up Your API Keys
```
Double-click: RUN-SETUP-WIZARD.bat
```
The Setup Wizard walks you through registering for each service step by step,
opens each registration page in your browser automatically, and writes your
`keys.bat` file for you. No manual editing required.

Services you'll need (the wizard explains each one):
| Service | Purpose | Approval Time |
|---------|---------|--------------|
| [Alpaca](https://alpaca.markets) | Stock trading API | Instant (paper) / up to 1 week (live) |
| [Alpha Vantage](https://alphavantage.co) | Market data & indicators | Instant |
| [Pushover](https://pushover.net) | Push notifications to phone | Instant |
| [Twilio](https://twilio.com) | SMS / phone call alerts | Instant |
| [Pushbullet](https://pushbullet.com) | Device sync notifications | Instant |

> **Tip:** Start with Alpaca Paper Trading — it's instant and uses fake money.
> Live trading approval can take up to a week.

### Step 3 — Launch
```
Double-click: START.bat
```
This activates the venv, loads your keys, starts both the dashboard and worker,
and opens your browser automatically.

**Local dashboard:** http://localhost:5000
**Render dashboard:** https://alien-ai-trader-dashboard.onrender.com

---

## 🧠 How the AI Trading Engine Works

### 1. Portfolio Ladder Scoring (New)

The engine now runs a **Portfolio Ladder Scanner** alongside the trading engine.
Every scan cycle, all symbols in your portfolio (up to 61+) receive a composite
**Ladder Score** from 0–100:

| Component | Weight | What It Measures |
|-----------|--------|-----------------|
| RSI Score | 25 pts | RSI in buying-dip sweet spot (35–55) |
| Momentum Score | 25 pts | SMA20/SMA50 crossover strength + spread % |
| Volume Score | 20 pts | Volume surge above 20-day average |
| Trend Score | 15 pts | Price position within 52-week high/low range |
| Profit Score | 15 pts | Unrealized gain bonus if currently held |

Stocks are ranked **highest → lowest** score every cycle (the "ladder"):

- **TOP tier** (top 20%): BUY candidates — engine focuses capital here
- **NEUTRAL** (middle 60%): Hold / monitor — no new buys
- **BOTTOM tier** (bottom 20%): Avoid / sell if held

This creates the **ladder climbing effect** — capital flows to the strongest
movers and away from the weakest, compounding upward over the session.

### 2. Continuous Market Scanning

The engine scans your full portfolio every **N seconds** (configurable, default 15s).

In **Scan All Market** mode it also pulls all active US equity symbols from Alpaca,
batch-fetches price snapshots, filters for volume > 200k and > 0.5% daily gain,
and adds the **top 30 momentum movers** to each cycle.

### 3. Live Price Feed

For each symbol:
- **Alpaca** first (real-time latest trade price)
- Falls back to **Alpha Vantage** if Alpaca fails
- Prices cached 8 seconds to avoid rate limits

### 4. Technical Analysis — RSI + SMA Crossover

For every symbol the engine pulls the last **60 one-minute bars** and calculates:

| Indicator | What It Measures |
|-----------|-----------------|
| **RSI-14** | Momentum. Above 70 = overbought, below 30 = oversold |
| **SMA-20** | 20-bar Simple Moving Average — short-term trend |
| **SMA-50** | 50-bar Simple Moving Average — medium-term trend |

### 5. Buy / Sell Signal Logic (Improved)

The original RSI < 70 threshold was too loose — it was buying near tops.
Now uses stricter filters:

| Signal | Condition | Meaning |
|--------|-----------|---------|
| **BUY** | SMA20 > SMA50 by ≥ 0.1% spread **AND** RSI < 50 **AND** Ladder = TOP tier | Confirmed uptrend with dip entry |
| **SELL** | SMA20 < SMA50 **OR** RSI > 70 | Trend reversing — exit |
| **HOLD** | Everything else | No clear edge |

> **Key change:** RSI must be below 50 (not 70) and the SMA crossover must have
> a real spread (not razor-thin). This dramatically reduces false buy signals.

### 6. Trailing Stop — Let Winners Run

- Tracks the **highest price since purchase** (the "peak")
- Sells when price **drops X% below that peak**
- Default: **3%** (adjustable live in the UI)

```
Example with 3% trailing stop:
  Buy  @ $100.00
  Peak @ $130.00  →  sell trigger = $126.10
  Peak @ $150.00  →  sell trigger = $145.50
  Price drops to $145.50  →  SELL
  Captured 45.5% gain instead of a fixed 10%
```

An **absolute stop-loss floor** (default 5%) also fires if the stock never rises.

### 7. Smart Position Sizing (New)

Set **Starting Capital $** in the dashboard to enable compound pool mode.
The engine now automatically scales trade sizes to your capital — no more
single large bets:

| Setting | Default | Effect at $100 Capital |
|---------|---------|----------------------|
| Risk Per Trade % | 2% | Max $2.00 risked per trade |
| Max Position % | 20% | Max $20.00 in any one stock |
| Min Positions | 5 | Capital spreads across ≥ 5 stocks |
| Hard $ Cap | 0 (off) | Optional absolute dollar ceiling |

**Example with $100:** Instead of one $99 bet, the engine places multiple
$2–$20 positions across the top-scored ladder stocks. A string of losses
can't wipe you out.

The math scales automatically — a user with $50,000 gets proportionally
larger positions using the same percentage rules.

### 8. Capital Pool & Compound Reinvestment

- On every sell, **100% of proceeds go back into the pool automatically**
- Engine immediately hunts for the next top-ladder stock and reinvests
- Gains compound with every cycle: $100 → $145 → $210 → ...
- Dashboard shows **Session ROI %** and **All-Time High** portfolio peak

### 9. Auto Trade Execution

**Buying:**
Signal = BUY + TOP ladder tier + open slot + capital available → market buy via Alpaca

**Selling — three exits (in priority order):**

| Exit | Trigger | Default |
|------|---------|---------|
| **Trailing Stop** | Price drops X% from peak | 3% |
| **Absolute Stop-Loss** | Price drops X% from buy entry | 5% |
| **Signal Exit** | SELL signal fires while profitable | — |

### 10. Safety Controls

- **Paper mode by default** — no real money until `TRADING_MODE=live` AND `LIVE_TRADING_ENABLED=true`
- **Trade throttle** — max 30 trades/hour (configurable)
- **Position cap** — max N simultaneous holdings (configurable)
- **Ladder gate** — engine blocked from buying BOTTOM-tier stocks even if RSI dips
- **Multi-channel alerts** — Pushbullet, Pushover, Twilio SMS/call on every major event

### 11. Live Settings — No Restart Needed

All settings adjustable from the **Trade tab** in the dashboard, take effect
on the next scan cycle:

**Core:**
- Trailing Stop % · Stop-Loss % · Scan Interval · Starting Capital $
- Max Positions · Scan All Market · Max Trades/Hour

**Position Sizing (New):**
- Risk Per Trade % · Max Position % · Min Positions · Hard $ Cap/Trade

**Signal Filters (New):**
- RSI Buy Max · RSI Sell Min · SMA Spread Min %

### 12. Real-Time Dashboard

Every cycle the engine pushes capital balance, open positions, RSI/SMA signals,
ladder scores, trade count, Session ROI %, and portfolio peak via **WebSocket**
to all open browser windows simultaneously.

---

## 📊 Signal & Ladder Flow

```
Every N seconds (configurable, default 15s)
     |
     +-- [poll live settings] ← picks up UI changes with no restart
     |
     +-- [Scan All Market ON?]
     |     +-- Alpaca all assets → batch snapshots → filter → top 30 movers added
     |
     v
[Portfolio Ladder Scanner — parallel, every 60s]
     +-- Score all 61 symbols: RSI + Momentum + Volume + Trend + Profit
     +-- Rank highest → lowest (the "ladder")
     +-- Tag TOP 20% as BUY candidates / BOTTOM 20% as AVOID
     |
     v
[Thread Pool — up to 12 parallel workers]
     +-- AAPL: price → RSI/SMA → Ladder check → BUY / trailing-stop / hold
     +-- TSLA: price → RSI/SMA → Ladder check → BUY / trailing-stop / hold
     +-- ... (all 61 portfolio symbols + market candidates simultaneously)
     |
     +-- BUY  → size position by risk % → deduct from capital pool → record peak
     +-- TRAILING STOP → SELL → add proceeds to pool → hunt next top-ladder target
     +-- STOP-LOSS     → SELL → protect remaining capital
     |
     v
[Heartbeat → WebSocket push → live dashboard]
     → prices, capital, ROI %, positions, RSI badges, ladder scores, alerts
```

---

## 🌐 Render Deployment

This app runs as two services on Render via `render.yaml` blueprint:

| Service | Type | What It Does |
|---------|------|-------------|
| `alien-ai-trader-dashboard` | Web Service | Flask dashboard + API + WebSocket |
| `alien-ai-trader-worker` | Background Worker | Trading engine + ladder scanner |

**Environment variables** are set in the Render dashboard for each service.
The Setup Wizard prints a copy-paste block for all required variables.

---

## ⚙️ Environment Variables

### Required
| Variable | Description |
|----------|-------------|
| `ALPACA_KEY` | Alpaca API Key ID |
| `ALPACA_SECRET` | Alpaca Secret Key |
| `ALPACA_BASE_URL` | `https://paper-api.alpaca.markets` (paper) or `https://api.alpaca.markets` (live) |
| `ALPHA_VANTAGE_KEY` | Alpha Vantage API key |
| `PUSHOVER_TOKEN` | Pushover app API token |
| `PUSHOVER_USER` | Pushover user key |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token |
| `TWILIO_FROM_NUMBER` | Twilio phone number (E.164 format: +1XXXXXXXXXX) |
| `TWILIO_TO_NUMBER` | Your cell number (E.164 format: +1XXXXXXXXXX) |
| `PUSHBULLET_API_KEY` | Pushbullet access token |

### Trading & Execution
| Variable | Default | Description |
|----------|---------|-------------|
| `TRADING_MODE` | `paper` | `paper` or `live` |
| `LIVE_TRADING_ENABLED` | `false` | Second safety switch for live trading |
| `ENGINE_MODE` | `AI` | `AI`, `SMA`, or `manual` |
| `POLL_SECONDS` | `15` | Scan interval (seconds) |
| `SCAN_WORKERS` | `12` | Parallel threads (12 recommended for 61 symbols) |
| `MAX_POSITIONS` | `5` | Maximum simultaneous open positions |
| `SCAN_ALL_MARKET` | `false` | Hunt all US equities for momentum |
| `MARKET_SCAN_CANDIDATES` | `30` | Top momentum stocks from market scan |
| `ORDER_QTY` | `1` | Shares per order (fixed qty mode only) |
| `MAX_TRADES_PER_HOUR` | `30` | Trade throttle |
| `RUN_SECONDS` | `21540` | Session length (5h 59m — just under Alpaca limit) |

### Capital & Position Sizing (New)
| Variable | Default | Description |
|----------|---------|-------------|
| `INITIAL_CAPITAL` | `0` | Starting capital $ (0 = fixed qty mode) |
| `RISK_PER_TRADE_PCT` | `2.0` | % of capital to risk per trade |
| `MAX_POSITION_PCT` | `20.0` | Max % of capital in any single stock |
| `MIN_POSITIONS` | `5` | Minimum positions to spread capital across |
| `RISK_PER_TRADE_USD` | `0` | Hard dollar cap per trade (0 = disabled) |

### Signal Filters (New)
| Variable | Default | Description |
|----------|---------|-------------|
| `RSI_BUY_MAX` | `50.0` | RSI must be below this to BUY |
| `RSI_SELL_MIN` | `70.0` | RSI must be above this to SELL |
| `SMA_SPREAD_MIN` | `0.1` | Min SMA20/SMA50 spread % for valid crossover |
| `TRAILING_STOP_PCT` | `3.0` | Sell if price drops this % from peak |
| `LOSS_THRESHOLD` | `5.0` | Absolute stop-loss % below buy price |

### Portfolio Ladder (New)
| Variable | Default | Description |
|----------|---------|-------------|
| `LADDER_INTERVAL` | `60` | Seconds between full portfolio re-scores |
| `MIN_SCORE_TO_BUY` | `45.0` | Minimum ladder score required to buy |
| `TOP_TIER_PCT` | `0.20` | Top X% of portfolio = BUY candidates |
| `BOTTOM_TIER_PCT` | `0.20` | Bottom X% = avoid / sell if held |

### Infrastructure
| Variable | Default | Description |
|----------|---------|-------------|
| `PRICE_CACHE_TTL` | `8` | Seconds to cache each price |
| `HEARTBEAT_EVERY_SECONDS` | `10` | Dashboard heartbeat frequency |
| `WORKER_STALE_AFTER_SECONDS` | `60` | Mark worker offline after N seconds silence |
| `FLASK_SECRET` | auto | Flask session secret key |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Web server | Flask + Flask-SocketIO |
| Real-time push | Socket.IO (WebSocket) |
| Market data | Alpaca Trade API + Alpha Vantage |
| Technical analysis | pandas (RSI-14, SMA-20, SMA-50) |
| Portfolio scoring | Custom ladder scorer (RSI + Momentum + Volume + Trend + Profit) |
| Charts | Chart.js (sparklines per card) |
| UI | Bootstrap 5 + Font Awesome |
| Mobile alerts | Pushbullet · Pushover · Twilio SMS/Call |
| Licensing | Stripe + SendGrid + Twilio |
| Deployment | Render (web service + background worker via blueprint) |

---

## 📁 Project Structure

```
Alien AI Trader disc/          ← repo root
├── dashboard.py               ← Flask web server + Socket.IO + all API routes
├── trading_engine.py          ← AI brain: signals, buy/sell, trailing stop, position sizing
├── worker.py                  ← Background worker: runs engine + ladder scanner
├── portfolio_ladder.py        ← Portfolio ladder scorer: ranks all symbols 0-100 (New)
├── setup_wizard.py            ← Interactive API key setup wizard (New)
├── config_loader.py           ← Loads API keys from env / config.json
├── license_api.py             ← Stripe licensing, SendGrid email, Twilio SMS
├── price_map.json             ← Symbol → display name map
├── requirements.txt           ← Python dependencies
├── keys.bat                   ← Your private API keys (gitignored — never commit!)
├── keys.bat.template          ← Template for keys.bat
├── INSTALL.ps1                ← Windows installer: Python + pip + venv (New)
├── START.bat                  ← One-click launcher: venv + keys + dashboard + worker (New)
├── RUN-SETUP-WIZARD.bat       ← Runs the API key setup wizard (New)
├── SETUP.bat                  ← Legacy first-time setup script
├── start-alien-ai-trader.bat  ← Legacy launch script
├── render.yaml                ← Render blueprint (web + worker services)
├── README.md                  ← This file — living blueprint of the app
└── templates/
    └── dashboard.html         ← Single-page dashboard UI
```

---

## 🔒 Security Notes

**Never commit these files to GitHub:**
```
keys.bat
.env
.env.local
```

Make sure your `.gitignore` includes them. The Setup Wizard and `gitignore_additions.txt`
handle this automatically.

---

## 📱 Mobile Alerts

The app sends alerts through three channels simultaneously:

| Channel | When | Setup |
|---------|------|-------|
| **Pushbullet** | Every trade, every signal | pushbullet.com → Settings → Access Token |
| **Pushover** | Stop-loss hits, crashes (breaks Do Not Disturb) | pushover.net → Create App |
| **Twilio** | After-hours crash calls to your phone | twilio.com → Console |

---

## ⚠️ Disclaimer

This software is for educational and paper trading purposes. The authors are not
financial advisors. Always test thoroughly in paper trading mode before enabling
live trading. Past performance of any algorithm does not guarantee future results.
Real money trading involves substantial risk of loss.

---

## ☁️ Cloud Sync for User Data (Planned/Optional)

**Cloud sync for backtest results and settings is now an optional feature.**
- Each registered/licensed user can choose to enable cloud sync for their own account.
- Backtest results, logs, and settings can be securely uploaded to the user’s personal cloud (not shared with other users or the app author).
- Cloud sync is OFF by default and must be enabled in the dashboard settings by the user.
- (Coming soon) Users will be able to view, download, and restore their results from any device after logging in.

> **Note:** No user data is ever uploaded to a central/shared cloud unless the user explicitly enables it. All cloud storage is per-user and tied to their license/account.

---

## 🆕 Major Enhancements (2026)

### Dashboard Tabs
| Tab | Description |
|-----|-------------|
| **Watchlist** | Live prices + RSI/SMA signals for your personal stock list |
| **Live Feed** | Real-time stream of AI decisions and market events |
| **Alerts** | Push notifications from the trading engine |
| **Trade** | Manual order panel + risk settings |
| **Top 20** | AI's best market candidates ranked by ladder score (score bars, tier color, RSI, verdict) |
| **Portfolio** | Capital summary (initial / available / invested / total) + live P&L on every open position |
| **Backtest** | Upload a CSV of historical price data → run the RSI+SMA strategy → see total return, win rate, max drawdown, and equity curve chart |
| **Settings** | Worker status, engine config, cloud sync |

### How to Use the Backtest Tab
1. Go to the **Backtest** tab
2. Enter a **Symbol** (e.g. `AAPL`)
3. Set a **Start Date** and **End Date**
4. Upload a **CSV file** with columns `date` and `close` (daily closing prices)
5. Click **Run Backtest** — results appear instantly below the form:
   - Total Return ($)
   - Win Rate (%)
   - Max Drawdown ($)
   - Trade count
   - Equity curve chart

### Whole-Market Scanning + Capital-Based Price Filter (New)
- **`SCAN_ALL_MARKET=true`** (default) — the AI scans all active US equities on Alpaca for momentum, not just your watchlist
- **Capital-based price filter** — the AI only considers stocks priced below `total_capital / min_positions`, so it automatically targets affordable stocks as capital grows:
  - $10 capital → stocks up to ~$2
  - $50 capital → stocks up to ~$10
  - $1,000 capital → stocks up to ~$200
  - Compounds upward automatically as profits reinvest

### Scan All Market Toggle — Persistence
- The **"Scan Entire Market"** switch on the Trade tab is saved server-side
- It stays on when you switch devices or open a new browser window — any device connecting picks up the current server state via WebSocket
- Default is **ON** (set via `SCAN_ALL_MARKET=true` in `render.yaml` and Render env vars)
- To make it permanently on: ensure `SCAN_ALL_MARKET=true` is set in your Render dashboard env vars for both services

### Other Improvements
- Advanced signal filters: MACD, Bollinger Bands, VWAP
- Dynamic position sizing (volatility & streak-based)
- AI model integration (pluggable ML signals)
- News & sentiment analysis (blocks bad trades)
- Auto-recovery: crash notifications & dashboard logging
- Robust notification system (Pushbullet, Pushover, Twilio)
- All settings live-editable from dashboard (no restart)
- Modular architecture for easy upgrades

---
