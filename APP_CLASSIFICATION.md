# Alien AI Trader — What This App Is (and Is Not)

**Purpose of this document.** A plain-English description of how Alien AI Trader is
built and distributed, so that (a) users understand what they are running, and (b) a
reviewing attorney can quickly assess how it should be classified. This is the author's
own description of the software, **not legal advice**, and it makes **no guarantee** of
any regulatory status — that determination is for a qualified securities attorney.

_Author: Troy Walker, T-Dub's Apps. Last updated: 2026-08-11._

---

## Short version

Alien AI Trader is **self-deployed trading software**. Each user runs **their own
private copy** and connects **their own brokerage account (Alpaca) with their own API
keys**. The author does **not** hold, custody, move, or manage anyone's money, and has
**no access** to any user's account, keys, or funds.

On Alpaca's own product split, that makes this a **Trading API** application (a tool an
individual points at their own account) — **not** a **Broker API** application (software
a business runs to operate a brokerage *for other people*).

---

## What this app IS

- **A trading tool.** It reads market data and, based on settings the **user** chooses
  (which stocks, risk limits, stop-losses, on/off), places orders **through the user's
  own broker account**.
- **Self-deployed / bring-your-own-keys.** The user installs or deploys their own copy
  (on their PC, or their own Render cloud account) and enters their **own** Alpaca and
  Alpha Vantage API keys into **their own** instance.
- **Owned and controlled by the user.** As stated in the deployment blueprint: *"This
  deployment is YOURS. It runs in your Render account, on your keys, under your control.
  The author cannot see it, reach it, or change it."*
- **Paper-first and opt-in for live.** It always starts in paper (practice-money) mode.
  Live real-money trading requires the user to (1) hold a paid license, (2) add their own
  separate live keys, and (3) turn it on themselves — three deliberate steps.

## What this app is NOT

- **NOT a broker or a Broker API application.** The author does not open accounts for
  users, does not custody or route funds, and is not the intermediary to the market.
- **NOT a money manager / discretionary adviser over user accounts.** The author never
  has access to, or control over, any user's account. Each user configures and runs their
  own copy and makes their own decision to trade.
- **NOT a promise of profit.** No guarantee of gains, no "risk-free," no "always wins."
  Trading carries real risk of loss; past/simulated results do not predict future results.
- **NOT a custodian.** No user money ever passes through the author or the software vendor.

---

## Architecture facts that support the "Trading API / self-deploy" classification

1. **Per-user deployment.** There is no single central service that holds many users'
   accounts. Every user runs an isolated copy (`APP_ROLE=client`). The author's own
   deployment serves only the store/license pages and never touches a customer's trading
   instance.
2. **Bring-your-own-keys.** Keys are entered by the user into their own instance
   (`/api/keys/setup`) and stored only there. The author never receives them.
3. **No cross-account access.** The app talks to **one** Alpaca account — the one whose
   keys the user entered — via Alpaca's **Trading API** (`api.alpaca.markets` /
   `paper-api.alpaca.markets`). It does not use Alpaca's Broker API.
4. **User control.** Start/stop, risk settings, symbol list, and paper↔live are all in
   the user's hands, in their own copy.

---

## ⚠️ The one boundary that would change the classification

If Alien AI Trader is ever offered as a **hosted, multi-user service** — i.e. **one
deployment the author operates** that many users connect **their** Alpaca accounts to —
that is a different model and Alpaca treats it differently:

- Alpaca then requires **OAuth2** (users *authorize* access; they do not paste raw keys),
  and
- **written approval from Alpaca** to enable live trading on behalf of other users, plus
  disclosure that the app is commercial.

See <https://alpaca.markets/oauth> and
<https://docs.alpaca.markets/us/docs/using-oauth2-and-trading-api>. **Do not build a
hosted/multi-user version without completing that process first.** (This boundary is also
noted in code, in the `keys_setup` handler in `dashboard.py`.)

---

## Safeguards already in place

- `RISK_DISCLOSURE.md`, `LIVE_TRADING_CONSENT.md`, `COMPLIANCE_PACK.md`,
  `LEGAL_REVIEW_PACKET.md` shipped with the app.
- Repeated "**we are not financial advisors**" and "no guarantee of profit" statements in
  the README and customer guide.
- Paper-mode default; live trading gated behind a license + separate keys + a manual switch.
- Portfolio Safety Shield and stop-losses included on every plan.

---

## For a reviewing attorney — questions worth confirming

1. Given the self-deploy / bring-your-own-keys architecture above, is classifying this as
   a **Trading API tool** (rather than Broker API) consistent with Alpaca's terms and with
   applicable regulation?
2. Does distributing automated-trading **software** (where the vendor never holds funds or
   exercises discretion over user accounts) implicate **investment-adviser** (RIA)
   registration, and if so, what changes are needed to stay clear of it?
3. Are the current disclaimers and marketing claims adequate, or should any language be
   revised to avoid implying guaranteed performance or discretionary management?
4. What specific steps (OAuth registration, approvals, disclosures) would be required
   **before** offering any hosted / multi-user version?

**How to give the reviewer access:** the full source, this document, and all compliance
files are public at the project's GitHub repository — sharing that URL lets an attorney
read everything without any account or special access.
