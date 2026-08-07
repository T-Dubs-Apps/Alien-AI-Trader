# 👽 Alien AI Trader — Complete Settings & Trading Guide

A plain‑English reference for **every setting**, what it does, and **how it affects your trading**. Print this and keep it next to you while you learn.

> **The one thing to remember:** the bot's job is to **buy stocks that are dipping inside an uptrend, protect them with automatic stop‑losses, and sell them near the top or at a profit target.** Every setting below just tunes *how cautious or aggressive* it is at doing that.

---

## How the bot works in 30 seconds

1. **Scans** stocks on a timer (your watchlist, or the whole market).
2. **Buys** when a stock looks like a good dip in an uptrend (and passes your filters).
3. **Watches** each holding continuously and tracks its highest price.
4. **Sells** when it hits a profit target, when momentum rolls over, or when a protective stop is triggered.

No setting turns off the safety stops — those always protect you.

---

## ⭐ The Risk Slider (1–10) — your master control

This is the single most important control. Moving it and pressing **Apply** overwrites **nine settings at once** — how picky it is about buying, how big each trade is, and how much of your cash it will deploy. **Level 5 is the balanced default.**

| Level | Name | Risk / trade | Max in one stock | Max invested | Cash held back | Behavior |
|------:|------|:-----------:|:---------------:|:------------:|:--------------:|----------|
| 1 | Very Conservative | 0.5% | 8% | 55% | 45% | Buys rarely, tiny positions, lots of cash safety |
| 2 | Conservative | 0.75% | 10% | 60% | 40% | |
| 3 | Cautious | 1.0% | 12% | 65% | 35% | |
| 4 | Moderate | 1.5% | 16% | 70% | 30% | |
| **5** | **Balanced (default)** | **2.0%** | **20%** | **75%** | **25%** | **Sensible middle ground** |
| 6 | Growth | 2.3% | 23% | 80% | 20% | |
| 7 | Assertive | 2.6% | 26% | 85% | 15% | |
| 8 | Aggressive | 3.0% | 29% | 90% | 10% | Adds "buy the drastic dip" entries |
| 9 | Very Aggressive | 3.5% | 32% | 95% | 5% | Drops the forecast‑up requirement |
| 10 | Maximum | 4.0% | 35% | 100% | 0% | Fully invested, no cash cushion, fewest filters |

**How it affects trading:** low numbers = fewer, smaller, safer trades with lots of cash in reserve. High numbers = more trades, bigger positions, and it invests nearly all your money. At **9–10** the "hard guard" blocks stop firing because it's allowed to deploy up to 100%.

---

## 1. Master switches

| Setting | Default | What it does & how it affects trading |
|---|---|---|
| **Auto‑Trade** | ON | The master on/off. ON = the bot places real buy/sell orders. OFF = it still scans and shows signals but **places no orders** (watch‑only). |
| **Paper / Live mode** | Paper | **Paper** = practice money, zero risk, for testing. **Live** = your real brokerage money (license‑gated). Always start on Paper. |
| **Market Hours Only** | ON | ON = trades only during regular market hours (9:30 AM–4:00 PM ET). OFF = also trades pre/after‑hours (thinner, riskier). |

---

## 2. How it decides to BUY

| Setting | Default | What it does & how it affects trading |
|---|---|---|
| **Scan Entire Market** | ON | ON = hunts the whole US market for opportunities (rotating through all qualified stocks so it covers everything over time). OFF = only watches your typed‑in watchlist. |
| **RSI Buy Max** | 60 | RSI measures "overbought vs oversold" (0–100). The bot only buys when RSI is **below** this number — i.e. it buys **dips**, not tops. Lower = pickier (deeper dips only). |
| **SMA Spread Min** | 0.1% | Requires the fast average (20‑day) to be at least this far above the slow average (50‑day) before buying — confirms a real uptrend. Higher = demands a stronger trend. |
| **Max Positions** | 5 | The most stocks it will hold at once. Higher = more diversification, smaller slices each. |
| **Min Positions** | 5 | Used to spread your capital: it divides your money by this number to cap how expensive a single share can be. Higher = buys cheaper stocks, spreads thinner. |
| **Rocket Breakout Mode** | ON | Lets it also chase **explosive momentum movers** (not just dips). The four settings below tune how big a move qualifies. |
| ↳ Min Day Change % | 12% | Stock must be up at least this much today to count as a "rocket." |
| ↳ Volume Surge ×  | 1.5× | Today's volume must be this many times its normal volume. |
| ↳ Min Avg Volume | 150,000 | Ignores thinly‑traded stocks below this average volume (avoids illiquid traps). |
| ↳ Max % Above SMA20 | 35% | Won't chase a stock that's already stretched more than this above its average (anti‑"buying the top"). |
| ↳ Lookback Bars | 20 | How many recent bars it measures the breakout over. |
| **Forecast filter** | ON | For **risky** stocks (volatile / thinly traded), it refuses to buy unless its price forecast points **up**. This is the "don't catch a falling knife" guard. Automatically **waived at slider 9–10**. |

---

## 3. How MUCH it buys (position sizing)

| Setting | Default | What it does & how it affects trading |
|---|---|---|
| **Starting Capital $** | 0 (auto) | The pool of money the bot manages. **0 = auto** — it sizes to your real account balance. Set a number to cap it to that amount. |
| **Risk Per Trade %** | 2% | How much of your capital to put toward each trade. 2% of $1,000 = ~$20 per trade. Higher = bigger bets. |
| **Max Position %** | 20% | No single stock may exceed this share of your capital — prevents over‑concentrating in one name. |
| **Risk Per Trade $** | 0 | An optional **fixed dollar** amount per trade instead of a percentage (0 = use the % instead). |

---

## 4. How it SELLS — protecting gains and taking profit

This is the part that actually locks in money. Several exits work together; whichever triggers first wins.

| Setting | Default | What it does & how it affects trading |
|---|---|---|
| **Trailing Stop %** | 6% | Follows the stock **up** and sells if it falls this % **from its highest point** since you bought. This is your main "let it run, then protect the gain" tool. Tighter (e.g. 3%) sells closer to the peak but exits on smaller wiggles. |
| **Trailing Activation %** | 3% | The trailing stop only **switches on** after the stock is up this much. Before that, only the hard stop‑loss can sell — and the trailing trigger is floored at your cost, so **the trailing stop never sells below what you paid**. |
| **Stop‑Loss %** | 8% | The disaster floor: if a stock drops this % below your buy price, it sells to cap the loss. This is the **only** exit allowed to sell below cost. |
| **Take‑Profit %** | 0 (off) | Auto‑sells the moment a position is up this %. The most reliable "sell high" — it locks in a set gain before any drop. Trade‑off: it caps a bigger run. (e.g. set 5 to bank +5% winners.) |
| **Min Hold (min)** | Cash: 5 / Margin: 360 | Smallest time to hold before the **smart** exits (take‑profit, forecast, signal) may fire. Emergency stop‑loss and trailing always fire regardless. Cash accounts keep it low for same‑day "sell high"; margin keeps it high to avoid day‑trade (PDT) flags. |
| **Forecast Exit** | ON | Sells **before** the trailing stop fires when the forecast says momentum has peaked and is rolling over — aims to exit nearer the top. |
| **RSI Sell Min** | 70 | Triggers a sell signal (while in profit) when RSI climbs above this — i.e. the stock is overbought and likely to pull back. |

---

## 5. Safety guards (hard limits)

| Setting | Default | What it does & how it affects trading |
|---|---|---|
| **Max Gross Exposure %** | slider‑set (75% at L5) | The most of your capital that may be invested at once. Blocks new buys past this. Scales with the risk slider (100% at level 10). |
| **Min Cash Reserve %** | slider‑set (25% at L5) | The minimum cash to keep un‑invested. The mirror of the setting above. |
| **Portfolio Safety Shield** | Off (0) | A whole‑account circuit breaker: if your **total portfolio value** falls to this dollar amount, it **halts all new buys**. Set the dollar threshold to turn it on; 0 = off. |
| ↳ Resume Buffer $ | 200 | After the shield trips, the portfolio must recover by this much before buying resumes (prevents flip‑flopping). |
| **Max Trades / Hour** | 30 | A rate limiter so it can never go on a runaway trading spree. |

---

## 6. Range Trader (opt‑in "buy low, sell high")

A separate mode that buys near the **bottom** of a stock's daily range and sells near the **top**. **Always OFF by default** — it turns itself off on every restart, page refresh, and at market close, so it never runs unattended.

| Setting | Default | What it does |
|---|---|---|
| **Enable Range Trader** | OFF | Turns the mode on for the current session only. |
| **Mode** | Auto | Auto = scans & trades on its own · Manual = only stocks you hand it (coming soon) · Both. |
| **Drop window** | 2 hours | The time window it measures the range and counts dips over (30‑min steps). |
| **Buy on drop #** | 4 | Waits for this many dips within the window before buying the low. Adjustable. |
| **Drop size %** | 1% | How big a pullback counts as one "drop." |
| **Also run after‑hours** | OFF | If on, the same rules apply in extended hours; otherwise it stops at market close. |

---

## 7. Scan & account

| Setting | Default | What it does & how it affects trading |
|---|---|---|
| **Scan Interval (sec)** | 60 | How often it checks the market. Minimum 60s to stay under the data provider's rate limit. |
| **Account Type** | Cash | **Cash** = no day‑trade limit, spends only settled funds (safer, allows fast same‑day exits). **Margin** = day‑trade rules apply under $25k, so it holds longer. Pick what your brokerage account actually is. |

---

## 📖 Glossary — trading terms in plain English

- **RSI (Relative Strength Index):** a 0–100 gauge of overbought (high) vs oversold (low). The bot buys low RSI (dips), sells high RSI (overbought).
- **SMA (Simple Moving Average):** the average price over N days. **SMA20** (fast) crossing above **SMA50** (slow) = a "golden cross" = uptrend. The reverse is a "death cross."
- **VWAP (Volume‑Weighted Average Price):** the average price weighted by volume — a "fair value" line. Buying at/below VWAP means buying a discount, not chasing.
- **MACD:** a momentum indicator; when its line is above its signal line, momentum is bullish.
- **Bollinger Bands:** a price envelope; near the lower band = cheap, near the upper band = stretched.
- **Trailing stop:** a sell trigger that rides **up** with the price and fires only when the stock falls a set % from its peak.
- **Stop‑loss:** a fixed floor below your buy price that caps the worst‑case loss.
- **Take‑profit:** a fixed target above your buy price that banks a gain automatically.
- **Exposure:** the % of your money currently invested. **Cash reserve** is the rest, held safe.
- **PDT (Pattern Day Trader):** a US rule limiting frequent same‑day round‑trips on **margin** accounts under $25k. Cash accounts are exempt — which is why cash accounts can sell faster.
- **Dip / pullback:** a temporary price drop inside a larger uptrend — the thing the bot tries to buy.

---

## ✅ A safe starting configuration

If you're new, start here and adjust as you learn:

- **Mode:** Paper (practice) until you trust it
- **Risk Slider:** 5 (Balanced) — move up only once comfortable
- **Trailing Stop:** 6% · **Stop‑Loss:** 8% · **Take‑Profit:** 5% (optional)
- **Min Hold:** 5 min (cash) · **Max Positions:** 5
- **Scan Entire Market:** ON · **Auto‑Trade:** ON
- **Portfolio Safety Shield:** set a dollar floor you're not willing to drop below

> No setting can guarantee a profit — markets move on their own. What these settings *do* guarantee is that the bot buys with discipline and always protects each position with automatic stops.

---

*Alien AI Trader · built by Troy Walker / T‑Dub's Apps. Settings can be changed live from the Trade tab — no restart needed, and everything is saved automatically.*
