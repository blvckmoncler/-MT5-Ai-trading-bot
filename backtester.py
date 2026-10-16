"""Backtesting harness for the AMD strategy.

This script walks historical candles, replays the strategy against the data,
and logs results for later review. It is useful for checking whether the
rule-based system behaves as expected before live execution.
"""

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - allows project import without MT5 installed
    mt5 = None

import pandas as pd
from datetime import datetime, timedelta

from .config import (
    SYMBOL, BIAS_TIMEFRAME, POI_TIMEFRAME, CONFIRM_TIMEFRAME,
    DISPLACEMENT_MULTIPLIER, LOCAL_SWEEP_LOOKBACK, SWING_LOOKBACK,
    FIB_TARGET_EXTENSION, MIN_RISK_REWARD, MIN_SETUP_SCORE,
    POI_TIMEOUT_BARS, CONFIRM_TIMEOUT_BARS, RISK_PERCENT, LOT_SIZE, MAX_SPREAD_PIPS,
    STARTING_BALANCE, BACKTEST_START, BACKTEST_END
)
from .phase3_mt5_connection import initialize_mt5, get_pip_size, get_historical_range_data
from .ict import AMDWeeklyStrategy
from .phase4_rule_based_bot import calculate_lot_size, pip_value_per_lot


def run_backtest():
    if mt5 is None:
        raise RuntimeError("MetaTrader5 is required to run the backtester.")
    if not initialize_mt5():
        return

    symbol_info = mt5.symbol_info(SYMBOL)
    if symbol_info is None:
        print(f"Error: Symbol {SYMBOL} is not found.")
        return

    pip_size = get_pip_size(symbol_info)

    print(f"Syncing historical data streams for {SYMBOL} backtest execution...")
    bias_df = get_historical_range_data(SYMBOL, BIAS_TIMEFRAME, BACKTEST_START, BACKTEST_END)
    h4_df = get_historical_range_data(SYMBOL, POI_TIMEFRAME, BACKTEST_START, BACKTEST_END)
    h1_df = get_historical_range_data(SYMBOL, CONFIRM_TIMEFRAME, BACKTEST_START, BACKTEST_END)

    if bias_df is None or h4_df is None or h1_df is None or len(h1_df) < 200:
        print("Historical synchronization failure: Insufficient dataset depth.")
        return

    print(f"4H:    {len(bias_df)} candles")
    print(f"1H:    {len(h4_df)} candles")
    print(f"5M:    {len(h1_df)} candles")
    print(f"Range: {h1_df['time'].min()} -> {h1_df['time'].max()}")

    strategy = AMDWeeklyStrategy(
        displacement_multiplier=DISPLACEMENT_MULTIPLIER,
        local_sweep_lookback=LOCAL_SWEEP_LOOKBACK,
        swing_lookback=SWING_LOOKBACK,
        fib_target_extension=FIB_TARGET_EXTENSION,
        min_rr=MIN_RISK_REWARD,
        min_setup_score=MIN_SETUP_SCORE,
        poi_timeout_bars=POI_TIMEOUT_BARS,
        confirm_timeout_bars=CONFIRM_TIMEOUT_BARS,
    )

    balance = STARTING_BALANCE
    equity_curve = [balance]
    trades = []
    open_trade = None

    # Step through historical execution loop via the 1H confirmation timeline.
    i = 80

    while i < len(h1_df) - 1:
        candle = h1_df.iloc[i]
        current_time = candle['time']

        # --- Position Management Block ---
        if open_trade is not None:
            if open_trade['direction'] == 'BUY':
                hit_sl = candle['low'] <= open_trade['sl']
                hit_tp = candle['high'] >= open_trade['tp']
            else:
                hit_sl = candle['high'] >= open_trade['sl']
                hit_tp = candle['low'] <= open_trade['tp']

            if hit_sl or hit_tp:
                outcome = 'LOSS' if hit_sl else 'WIN'
                exit_price = open_trade['sl'] if hit_sl else open_trade['tp']

                price_move_pips = abs(
                    exit_price - open_trade['entry_price']
                ) / pip_size

                pnl = (
                    open_trade['volume']
                    * price_move_pips
                    * open_trade['pip_value_per_lot']
                )

                if outcome == 'LOSS':
                    pnl = -pnl

                balance += pnl
                equity_curve.append(balance)

                trades.append({
                    'entry_time': open_trade['entry_time'],
                    'exit_time': current_time,
                    'direction': open_trade['direction'],
                    'entry_price': open_trade['entry_price'],
                    'exit_price': exit_price,
                    'outcome': outcome,
                    'pnl': pnl,
                    'balance_after': balance,
                })

                open_trade = None

            i += 1
            continue

        slice_bias = bias_df[bias_df['time'] <= current_time].reset_index(drop=True)
        slice_h4 = h4_df[h4_df['time'] <= current_time].reset_index(drop=True)
        
        slice_h1 = h1_df[h1_df["time"] <= current_time].reset_index(drop=True)

        if len(slice_bias) >= 20 and len(slice_h4) >= 20 and len(slice_h1) >= 20:
            signal = strategy.update(
                slice_bias,
                slice_h4,
                slice_h1,
                current_time,
            )

            if signal is not None:
                sl_pips = signal["risk_price"] / pip_size
                pip_value = pip_value_per_lot(symbol_info, pip_size)

                if sl_pips > 0 and pip_value > 0:
                    volume = calculate_lot_size(
                        symbol_info, sl_pips, RISK_PERCENT, balance
                    )

                    open_trade = {
                        "entry_time": current_time,
                        "direction": signal["signal"],
                        "entry_price": signal["entry"],
                        "sl": signal["sl"],
                        "tp": signal["tp"],
                        "volume": volume,
                        "pip_value_per_lot": pip_value,
                    }

                    print(
                        f"Opened {signal['signal']} at {signal['entry']:.2f}, "
                        f"SL={signal['sl']:.2f}, TP={signal['tp']:.2f}, "
                        f"volume={volume:.2f}"
                    )

        i += 1

    print_summary(trades, equity_curve)
    if trades:
        pd.DataFrame(trades).to_csv("backtest_amd_log.csv", index=False)


def print_summary(trades, equity_curve):
    if not trades:
        print("\nNo structural trades were verified within this sequence window.")
        return

    wins = [t for t in trades if t['outcome'] == 'WIN']
    win_rate = len(wins) / len(trades) * 100
    final_balance = equity_curve[-1]
    total_return = (final_balance - STARTING_BALANCE) / STARTING_BALANCE * 100

    print("\n=== AMD Backtest Summary ===")
    print(f"Total Completed Trades: {len(trades)} | Wins: {len(wins)} | Win Rate: {win_rate:.2f}%")
    print(f"Starting: {STARTING_BALANCE:,.2f} -> Final Balance: {final_balance:,.2f} ({total_return:+.2f}%)")


if __name__ == "__main__":
    run_backtest()
