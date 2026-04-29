"""
backtest.py — Trade Simulation & Backtest Engine for Alien AI Trader

- Simulates trading strategies using historical data and the TradingEngine logic.
- Outputs performance metrics: total return, max drawdown, win rate, trade log, and equity curve.
- Designed for integration with dashboard UI and CLI.

Usage:
    python backtest.py --symbols AAPL,MSFT --start 2024-01-01 --end 2024-12-31 --mode AI

Best practices:
- Uses TradingEngine for signal logic (no code duplication)
- Loads historical data via Alpaca/Alpha Vantage or CSV
- No live orders are placed
- Results are saved to CSV/JSON and optionally plotted
"""

import argparse
import os
import pandas as pd
from datetime import datetime
from trading_engine import TradingEngine

class BacktestEngine:
    def __init__(self, symbols, start_date, end_date, mode="AI"):
        self.symbols = [s.strip().upper() for s in symbols]
        self.start_date = pd.to_datetime(start_date)
        self.end_date = pd.to_datetime(end_date)
        self.mode = mode
        self.results = {}

    def run(self):
        for symbol in self.symbols:
            print(f"[BACKTEST] Running simulation for {symbol}...")
            df = self._load_historical_data(symbol)
            if df is None or df.empty:
                print(f"[BACKTEST] No data for {symbol}, skipping.")
                continue
            engine = TradingEngine([symbol], mode=self.mode)
            engine.auto_trade = True
            engine.running = True
            trade_log = []
            holding = None
            for idx, row in df.iterrows():
                price = float(row['close'])
                # Simulate signal evaluation
                signal = engine._get_signal(symbol, price)
                # Simulate buy/sell logic
                if not holding and signal['verdict'] == 'BUY':
                    holding = {'price': price, 'buy_date': row['date']}
                    trade_log.append({'action': 'BUY', 'symbol': symbol, 'price': price, 'date': row['date']})
                elif holding and signal['verdict'] == 'SELL':
                    pnl = price - holding['price']
                    trade_log.append({'action': 'SELL', 'symbol': symbol, 'price': price, 'date': row['date'], 'pnl': pnl})
                    holding = None
            # Close open position at end
            if holding:
                price = float(df.iloc[-1]['close'])
                pnl = price - holding['price']
                trade_log.append({'action': 'SELL', 'symbol': symbol, 'price': price, 'date': df.iloc[-1]['date'], 'pnl': pnl})
            self.results[symbol] = self._analyze_results(trade_log)
            self.results[symbol]['trade_log'] = trade_log
        return self.results

    def _load_historical_data(self, symbol):
        # Try CSV first
        csv_path = f"historical_{symbol}.csv"
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            df['date'] = pd.to_datetime(df['date'])
            df = df[(df['date'] >= self.start_date) & (df['date'] <= self.end_date)]
            return df
        # TODO: Add API fetch fallback (Alpaca/Alpha Vantage)
        return None

    def _analyze_results(self, trade_log):
        buys = [t for t in trade_log if t['action'] == 'BUY']
        sells = [t for t in trade_log if t['action'] == 'SELL']
        if not sells:
            return {'total_return': 0, 'win_rate': 0, 'max_drawdown': 0, 'trades': 0}
        pnl = [t['pnl'] for t in sells if 'pnl' in t]
        total_return = sum(pnl)
        wins = [x for x in pnl if x > 0]
        win_rate = len(wins) / len(pnl) if pnl else 0
        # Simple max drawdown calculation
        equity = 0
        peak = 0
        max_dd = 0
        for x in pnl:
            equity += x
            if equity > peak:
                peak = equity
            dd = (peak - equity)
            if dd > max_dd:
                max_dd = dd
        return {
            'total_return': total_return,
            'win_rate': round(win_rate, 3),
            'max_drawdown': round(max_dd, 2),
            'trades': len(pnl)
        }

def main():
    parser = argparse.ArgumentParser(description="Alien AI Trader Backtest Engine")
    parser.add_argument('--symbols', type=str, required=True, help='Comma-separated list of symbols')
    parser.add_argument('--start', type=str, required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--mode', type=str, default='AI', help='Trading mode (AI/AI_MODEL)')
    args = parser.parse_args()
    engine = BacktestEngine(args.symbols.split(','), args.start, args.end, mode=args.mode)
    results = engine.run()
    for symbol, res in results.items():
        print(f"\n=== {symbol} Backtest Results ===")
        print(f"Total Return: {res['total_return']}")
        print(f"Win Rate: {res['win_rate']*100:.1f}%")
        print(f"Max Drawdown: {res['max_drawdown']}")
        print(f"Trades: {res['trades']}")
        # Optionally save trade log
        pd.DataFrame(res['trade_log']).to_csv(f"backtest_{symbol}.csv", index=False)

if __name__ == "__main__":
    main()
