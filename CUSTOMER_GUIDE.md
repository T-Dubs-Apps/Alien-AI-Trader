# 👽 Alien AI Trader — Customer Guide (Start Here)

Welcome! This guide explains, in plain language, everything you need to get the
app, run it, and understand what it does. **No coding, no tech background needed.**
If you can use a web browser, you can do this.

---

## ❓ Your Questions, Answered

### Where can I get it? How?
One link does it all:

> **https://alien-ai-trader-dashboard.onrender.com/get**

Open that page and click the big **“☁️ Deploy Your Personal Trader on Render”**
button. That’s the starting point. (Full step-by-step is below.)

### Is it easy to get?
Yes. It’s about **10 minutes**, mostly waiting while it sets itself up. You’ll:
1. Click a button, 2. make two **free** accounts, 3. paste a couple of keys, 4. done.
No installing programs, no code.

### What makes this trading app special?
- **It trades for you, automatically.** The AI scans the market, buys stocks that
  are climbing, and sells before they drop — then reinvests. This is the “ladder.”
- **It runs 24/7 in the cloud** — your computer doesn’t need to be on.
- **Safety first.** It starts in **paper mode** (fake money) so you risk nothing while
  you learn it. A built-in **Safety Shield** and **stop-losses** limit losses, and
  they’re included **free on every plan**.
- **You’re always in control** — switch it on/off, set how much it manages, and flip
  between practice and real money whenever you want.

### Can I use my Apple iPhone (or iPad) to set it up?
**Yes.** The whole cloud setup and the dashboard work in your phone’s web browser
(Safari or Chrome). You can deploy it, watch it, and change settings from your iPhone.
*(There’s also an optional Windows PC version, but you do not need it — the cloud path
works from any device.)*

### Can I access and make changes to my Render account?
**Yes — it’s 100% your own account.** You sign up at render.com, and you control
everything: your keys, your settings, starting/stopping the app. You can log in from
any device, anytime. Nothing is shared with us.

### How much does Render cost?
- **Free tier: $0.** Great for trying it out. On the free tier the app “sleeps” when
  not used and wakes up in a few seconds when you visit it.
- **Always-on (optional): about $7/month** if you want it awake 24/7 with no sleeping.
- The other services it uses — **Alpaca** (your brokerage) and **Alpha Vantage**
  (market data) — have **free** plans that are enough to get started.

### Will my subscription and settings survive app updates and restarts?
**Yes — automatically.** Every time the app updates, restarts, or recovers from a
hiccup, it **re-confirms your subscription by itself** and picks up right where it
left off. You never have to re-enter your license. Here’s how it stays that way,
and the one choice you get at setup:

- **Recognizing you (automatic, free on every plan).** During setup you save your
  **purchase email** as `LICENSE_EMAIL`. On every startup the app checks it and
  restores your plan straight from the payment record — so **paid stays paid** and
  **free stays free**, with no interruption, until *you* cancel, it expires, or a
  renewal payment is declined. Your open trades also come back on their own,
  because they’re read directly from your Alpaca brokerage account.

- **Remembering everything else — the recommended “Both” setup.** If you also want
  your **exact settings and any keys you typed into the app** to come back *exactly*
  as they were after any restart, turn on a small **persistent disk** in Render
  (set `DATA_DIR=/var/data` and attach the 1 GB disk — instructions in the deploy
  guide). We recommend this. It needs Render’s **paid (always-on) tier (~$7/mo)**.

  Without the disk, nothing breaks — your subscription and live keys still come back
  automatically; only settings you changed by hand revert to their defaults.

> 💡 **Why we recommend “Both.”** The email recovery keeps your subscription alive
> for free; the disk makes the app return to the *exact* state it was in before any
> update or crash. Together, there’s zero babysitting.

> 💳 **A note on costs.** Your Render account (including the optional always-on tier
> and disk) is **billed to you by Render** and is your responsibility — it’s your own
> private cloud deployment. The app subscription (below) is separate and is what you
> pay us for.

### How much does the app itself cost?
- **Paper trading (practice money): FREE forever.**
- **Live (real-money) trading** needs a subscription:
  - **Trader** — $19.99/month or $199/year
  - **Pro** — $59/month or $590/year (adds full-market scanning, more positions, and
    early “sell at the peak” exits)

### Has anybody made money with it? Can you prove it?
**Straight answer: this app is brand new, and there is no verified real-money track
record yet.** It has been tested in **paper (simulated) mode**, not with a long history
of real trades. We will **never show you fake screenshots or made-up profits** — that
wouldn’t be fair to you.

**Please understand:** trading real money always carries **risk of loss**. Simulated or
past results **do not guarantee** future results. The honest, smart way to judge this
app is to **run it in free paper mode yourself** and watch how it does before you ever
risk a real dollar.

### What’s the best amount to invest to make money?
We are **not financial advisors**, and no one can honestly promise you profits or tell
you a “right” amount. The only universal rule that protects you:

> **Only ever use money you can afford to lose — and start small.**

Begin in **paper mode** (free, zero risk). When you switch to real money, start with a
small amount you’re completely comfortable losing, and only increase it once you’ve seen
how the app behaves for yourself.

### Is there an instruction manual?
Yes — **this guide**, plus a fuller **README** here:
> https://github.com/T-Dubs-Apps/Alien-AI-Trader#readme

The app also guides you on-screen as you go.

### Who can help me install it or set up my account?
- This guide and the on-screen steps walk you through everything.
- Need a person? **Contact support: mr.troy.walker.62@gmail.com** (or simply reply
  to your purchase receipt email). We’re happy to help you get set up.

---

## 🛒 Step-by-Step: Get the App Running (the easy cloud way)

> You’ll make two **free** accounts along the way: **Render** (hosts your app) and
> **Alpaca** (your stock brokerage). Plus a free **Alpha Vantage** data key. That’s it.

**Step 1 — Open the store page.**
Go to **https://alien-ai-trader-dashboard.onrender.com/get** on your phone or computer.

**Step 2 — Click “☁️ Deploy Your Personal Trader on Render.”**
This opens Render. If you don’t have a Render account, create one (it’s free) — you can
sign up with Google or email.

**Step 3 — Get your free keys** (the page has one-tap links):
- **Alpaca** (your brokerage): create a free account, choose **Paper Trading**, and copy
  your **API Key** and **Secret**.
- **Alpha Vantage** (market data): grab a free **API key** (takes ~30 seconds).

**Step 4 — Paste the keys into Render’s setup boxes.**
Render will ask for them before it builds. Paste your Alpaca key + secret and your Alpha
Vantage key. **Leave any other boxes blank.**

**Step 5 — Click Deploy and wait a few minutes.**
Render builds your own private copy of the app.

**Step 6 — Open your app.**
Render gives you your own web address. Open it — 🎉 you’re now running the AI trader in
**paper mode (practice money), free and risk-free.** Watch it work!

---

## 🟢 Turning On Real-Money (Live) Trading — When You’re Ready

Take your time in paper mode first. When you decide to go live:

1. **Subscribe.** In the app: **Settings → License → Subscribe** (Trader or Pro).
2. **Activate.** You’ll get an email. In the app: **Settings → License → Activate** with
   that email → the badge turns 🟢 **Licensed**.
3. **Add your live keys — right in the app.** In **Settings → Trading Mode**, flip
   **Paper → Live**. If you don’t have live keys yet, the app pops up a panel with
   buttons to get your **Alpaca live keys** — paste them in and click **Save & Go Live**.
   (No need to visit Render’s settings for this.)
4. **Confirm.** You’ll type `LIVE` to confirm you understand it’s real money.

You can switch back to **Paper** anytime, instantly.

---

## 🛡️ Your Safety Net (Always On)
- The app **always starts in paper mode** — it will not touch real money until you
  deliberately turn it on.
- **Stop-losses** and the **Safety Shield** automatically limit losses (free on every plan).
- **You’re in charge:** pause it, stop it, or set how much money it manages, anytime.

---

## ⚠️ Important Disclaimer
Alien AI Trader is a software tool, **not** financial advice, and Troy Walker / T-Dub’s
Apps are **not** financial advisors. Trading real money involves a **real risk of loss**.
Simulated or past performance does **not** guarantee future results. Always test in paper
mode first, and never trade money you cannot afford to lose. You are responsible for your
own trading decisions.

---

*👽 Alien AI Trader · Built by Troy Walker · T-Dub’s Apps · 2026*
