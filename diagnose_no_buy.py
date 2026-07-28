#!/usr/bin/env python3
"""
diagnose_no_buy.py -- Alien AI Trader

Answers ONE question: "Why isn't the engine buying?"

It runs a single, READ-ONLY scan cycle over your watchlist (and optionally the
full-market momentum candidates) and prints, for every symbol, the exact result
of each gate a BUY must pass -- the same gates the live engine uses in
evaluate() / buy(). It NEVER submits an order.

For each symbol you get:
  * live price + how many daily bars came back (SMA50 needs >= 50)
  * every indicator (RSI, SMA20/50, MACD, Bollinger, VWAP) and its verdict
  * which of the 5 confluence checks passed/failed
  * the rocket-breakout OR-path result
  * the soft gates: sentiment, forecast-required, open slot, auto-trade
  * a one-line CONCLUSION: would it buy, and if not, the first blocking reason

Usage (from the app folder, with your Alpaca keys available):
    python diagnose_no_buy.py            # watchlist only
    python diagnose_no_buy.py --market   # also pull full-market candidates
    python diagnose_no_buy.py --keys keys.bat   # load keys from a bat file first

Keys are read from the environment. If they aren't set, the script will try to
load them from keys.bat in the current folder (set NAME=VALUE lines).

Built by Troy Walker of T-Dub's Apps -- 2026
"""

import os
import re
import sys
import time

CHECK = "PASS"
CROSS = "FAIL"


def _load_keys_from_bat(path: str) -> int:
    """Parse `set NAME=VALUE` lines from a .bat and load into os.environ.
    Only sets vars that are not already present. Returns count loaded."""
    if not path or not os.path.exists(path):
        return 0
    loaded = 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = re.match(r"\s*set\s+([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$", line, re.IGNORECASE)
            if not m:
                continue
            name, value = m.group(1), m.group(2)
            if name and value and name not in os.environ:
                os.environ[name] = value
                loaded += 1
    return loaded


def _fmt(v, nd=2):
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return "n/a"


def main():
    args = sys.argv[1:]
    want_market = "--market" in args
    keys_path = "keys.bat"
    if "--keys" in args:
        i = args.index("--keys")
        if i + 1 < len(args):
            keys_path = args[i + 1]

    n = _load_keys_from_bat(keys_path)
    if n:
        print(f"[keys] Loaded {n} var(s) from {keys_path} (only ones not already set).")

    # Don't let importing the app start the engine/backup threads.
    os.environ.setdefault("DISABLE_ENGINE_AUTOSTART", "1")

    try:
        from trading_engine import TradingEngine
    except Exception as e:
        print(f"[fatal] Could not import trading_engine: {e}")
        sys.exit(1)

    try:
        from news_sentiment import get_symbol_sentiment
    except Exception:
        get_symbol_sentiment = None

    stock_list = [s.strip().upper()
                  for s in os.environ.get("STOCK_LIST", "AAPL,GOOG,TSLA,MSFT,AMZN").split(",")
                  if s.strip()]

    print("=" * 74)
    print("  ALIEN AI TRADER -- WHY-NO-BUY DIAGNOSTIC (read-only, no orders placed)")
    print("=" * 74)
    print(f"  Watchlist: {', '.join(stock_list)}")

    def _silent(*a, **k):
        return None

    try:
        eng = TradingEngine(stock_list=stock_list,
                            mode=os.environ.get("ENGINE_MODE", "AI"),
                            alert_callback=_silent,
                            activity_callback=_silent)
    except Exception as e:
        print(f"\n[fatal] Engine failed to initialize (usually bad/missing Alpaca keys): {e}")
        print("        Set ALPACA_KEY / ALPACA_SECRET / ALPACA_BASE_URL (paper) and retry.")
        sys.exit(1)

    rsi_buy_max = getattr(eng, "rsi_buy_max", 60.0)
    sma_spread_min = getattr(eng, "sma_spread_min", 0.0)
    vwap_prem = getattr(eng, "vwap_max_premium_pct", 15.0)
    max_positions = getattr(eng, "max_positions", 5)
    auto_trade = getattr(eng, "auto_trade", True)
    rocket_on = getattr(eng, "rocket_breakout_enabled", True)
    held = len(getattr(eng, "current_holdings", {}) or {})

    print(f"  Engine config: rsi_buy_max<{rsi_buy_max}  sma_spread_min>={sma_spread_min}%  "
          f"vwap_premium<= {vwap_prem}%  max_positions={max_positions}  "
          f"auto_trade={auto_trade}  rocket_breakout={rocket_on}")
    print(f"  Open positions right now: {held}/{max_positions}")

    symbols = list(stock_list)
    if want_market:
        try:
            cand = eng._get_market_candidates(max_candidates=getattr(eng, "_market_scan_candidates", 10))
            extra = [c for c in cand if c not in symbols]
            symbols += extra
            print(f"  Full-market candidates added: {', '.join(extra) if extra else '(none returned)'}")
        except Exception as e:
            print(f"  [warn] Could not pull market candidates: {e}")

    print("=" * 74)

    would_buy = []
    reasons = {}

    for sym in symbols:
        print(f"\n### {sym}")
        price = None
        try:
            price = eng.get_live_price(sym)
        except Exception as e:
            print(f"   price: ERROR {e}")
        if price is None:
            print("   [BLOCKED] price_unavailable -- no live price from broker/fallback feeds.")
            print("             (bad keys, symbol halted, or the data feed is down)")
            reasons["price_unavailable"] = reasons.get("price_unavailable", 0) + 1
            continue

        signal = eng._get_signal(sym, price)
        bars = "?"
        try:
            df = eng._get_bars_df(sym)
            bars = 0 if df is None or df.empty else len(df)
        except Exception:
            pass

        di = signal.get("data_issue")
        print(f"   price=${_fmt(price)}  bars={bars}  verdict={signal.get('verdict')}"
              + (f"  DATA_ISSUE={di}" if di else ""))

        rsi = signal.get("rsi"); sma20 = signal.get("sma20"); sma50 = signal.get("sma50")
        macd = signal.get("macd"); macd_sig = signal.get("macd_signal")
        bu = signal.get("boll_upper"); bl = signal.get("boll_lower"); vwap = signal.get("vwap")
        print(f"   RSI={_fmt(rsi)} SMA20={_fmt(sma20,3)} SMA50={_fmt(sma50,3)} "
              f"MACD={_fmt(macd,3)}/{_fmt(macd_sig,3)} Boll=[{_fmt(bl,2)},{_fmt(bu,2)}] "
              f"VWAP={_fmt(vwap,2)} fc={signal.get('forecast_direction')}")

        if di:
            print(f"   [BLOCKED] {di} -- indicators can't be computed "
                  f"(need >= 50 daily bars for SMA50; got {bars}).")
            reasons[di] = reasons.get(di, 0) + 1
            continue

        # Reproduce the 5-part confluence (mirrors _get_signal lines ~1619-1642)
        have_all = all(v is not None for v in (sma20, sma50, rsi, macd, macd_sig, bu, bl, vwap))
        if have_all:
            spread_pct = abs(sma20 - sma50) / sma50 * 100 if sma50 else 0.0
            c_golden = sma20 > sma50 and spread_pct >= sma_spread_min
            c_rsi = rsi < rsi_buy_max
            c_macd = macd > macd_sig
            c_boll = (price > bl) and (price < bu)
            c_vwap = price <= vwap * (1.0 + vwap_prem / 100.0)
            for name, ok, detail in [
                ("golden_cross", c_golden, f"SMA20>{_fmt(sma50,2)}? spread={_fmt(spread_pct,2)}% >= {sma_spread_min}%"),
                ("rsi_below_max", c_rsi, f"{_fmt(rsi)} < {rsi_buy_max}"),
                ("macd_bullish", c_macd, f"{_fmt(macd,3)} > {_fmt(macd_sig,3)}"),
                ("within_bollinger", c_boll, f"{_fmt(bl,2)} < {_fmt(price)} < {_fmt(bu,2)}"),
                ("not_vwap_extended", c_vwap, f"{_fmt(price)} <= {_fmt(vwap,2)}*{1+vwap_prem/100:.2f}"),
            ]:
                print(f"      [{CHECK if ok else CROSS}] {name:<18} {detail}")

        buy_verdict = signal.get("verdict") == "BUY"
        if not buy_verdict:
            first_fail = "no_buy_signal"
            print(f"   [BLOCKED] {first_fail} -- confluence not met and rocket-breakout "
                  f"({'on' if rocket_on else 'off'}) did not trigger. Verdict stayed "
                  f"{signal.get('verdict')}.")
            reasons[first_fail] = reasons.get(first_fail, 0) + 1
            continue

        # --- BUY verdict reached: walk the execution gates (read-only) ---
        print("   verdict=BUY -- checking execution gates:")

        # Slot
        slot_ok = held < max_positions
        print(f"      [{CHECK if slot_ok else CROSS}] open_slot            holdings {held} < {max_positions}")

        # Sentiment (respects SENTIMENT_GATE_ENABLED)
        sent_ok = True
        sentiment_on = getattr(eng, "sentiment_gate_enabled", True)
        if get_symbol_sentiment is not None and sentiment_on:
            try:
                sc = get_symbol_sentiment(sym).get("sentiment_score", 0)
                sent_ok = not (sc < 0)
                print(f"      [{CHECK if sent_ok else CROSS}] sentiment            score={_fmt(sc,3)} (blocks if < 0)")
            except Exception as e:
                print(f"      [ ?? ] sentiment            could not evaluate ({e})")
        elif not sentiment_on:
            print(f"      [{CHECK}] sentiment            gate disabled (SENTIMENT_GATE_ENABLED=false)")

        # Forecast-required (respects FORECAST_GATE_ENABLED)
        fc_ok = True
        forecast_on = getattr(eng, "forecast_gate_enabled", True)
        try:
            required, why = eng._forecast_required_for_entry(signal, price)
            if not forecast_on:
                required = False
                print(f"      [{CHECK}] forecast_required    gate disabled (FORECAST_GATE_ENABLED=false)")
            elif required:
                fc_ok = signal.get("forecast_direction") == "up"
                print(f"      [{CHECK if fc_ok else CROSS}] forecast_required    high-risk ({', '.join(why)}); "
                      f"needs forecast=up, got {signal.get('forecast_direction')}")
            else:
                print(f"      [{CHECK}] forecast_required    not required for this entry")
        except Exception as e:
            print(f"      [ ?? ] forecast_required    could not evaluate ({e})")

        # Auto-trade
        print(f"      [{CHECK if auto_trade else CROSS}] auto_trade           {auto_trade}")

        # Ladder (fails open until scored)
        ladder_ok = True
        try:
            checker = getattr(eng, "is_ladder_approved", None)
            if checker:
                ladder_ok = bool(checker(sym))
                print(f"      [{CHECK if ladder_ok else CROSS}] ladder_top_tier      {'approved' if ladder_ok else 'NOT top tier / below min score'}")
            else:
                print(f"      [{CHECK}] ladder_top_tier      no ladder attached (allowed)")
        except Exception as e:
            print(f"      [ ?? ] ladder_top_tier      could not evaluate ({e})")

        gates = [("open_slot", slot_ok), ("sentiment", sent_ok),
                 ("forecast_required", fc_ok), ("auto_trade", auto_trade),
                 ("ladder_top_tier", ladder_ok)]
        failed = [g for g, ok in gates if not ok]
        if failed:
            print(f"   [BLOCKED] would NOT buy -- failed gate(s): {', '.join(failed)}")
            for g in failed:
                reasons[g] = reasons.get(g, 0) + 1
        else:
            print(f"   [WOULD BUY] {sym} @ ${_fmt(price)} -- all gates pass.")
            would_buy.append(sym)

    print("\n" + "=" * 74)
    print("  SUMMARY")
    print("=" * 74)
    print(f"  Symbols scanned : {len(symbols)}")
    print(f"  Would BUY now   : {', '.join(would_buy) if would_buy else '(none)'}")
    if reasons:
        print("  Top blocking reasons:")
        for r, c in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print(f"      {c:>3}x  {r}")
    if not would_buy:
        print("\n  If EVERY symbol shows 'no_buy_signal', the strategy simply has no valid")
        print("  setup right now -- try --market for more candidates, or widen STOCK_LIST.")
        print("  If you see 'price_unavailable'/'bars_unavailable' everywhere, it's a data")
        print("  feed / API-key problem, not the strategy. If it's a specific gate")
        print("  (forecast_required, sentiment, ladder_top_tier), that gate is the cause.")
    print("=" * 74)


if __name__ == "__main__":
    main()
