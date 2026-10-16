"""ICT-style AMD strategy logic.

This module contains the price-structure and fairness-gap detection logic used
by the trading bot. It evaluates higher-timeframe bias, liquidity sweeps, and
FVG confluence before producing a trade signal.
"""

import time
try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - allows import-only environments without MT5
    mt5 = None
from datetime import datetime

from .config import (
    SYMBOL, BIAS_TIMEFRAME, POI_TIMEFRAME, CONFIRM_TIMEFRAME,
    DISPLACEMENT_MULTIPLIER, LOCAL_SWEEP_LOOKBACK, MIN_RISK_REWARD,
    POI_TIMEOUT_BARS, CONFIRM_TIMEOUT_BARS, RISK_PERCENT, MAX_SPREAD_PIPS,
    MAGIC_NUMBER, DEVIATION
)
from .phase3_mt5_connection import (
    initialize_mt5, get_market_data, get_pip_size, get_filling_mode
)


def spread_is_acceptable(symbol_info, pip_size):
    spread_points = symbol_info.spread * symbol_info.point
    return spread_points <= MAX_SPREAD_PIPS


def pip_value_per_lot(symbol_info, pip_size):
    return symbol_info.trade_tick_value * (pip_size / symbol_info.trade_tick_size)


def calculate_lot_size(symbol_info, sl_pips, risk_percent, balance):
    risk_amount = balance * risk_percent
    pip_size = get_pip_size(symbol_info)
    pv_per_lot = pip_value_per_lot(symbol_info, pip_size)

    if pv_per_lot <= 0 or sl_pips <= 0:
        return symbol_info.volume_min

    raw_lots = risk_amount / (sl_pips * pv_per_lot)
    step = symbol_info.volume_step
    lots = round(raw_lots / step) * step
    return max(symbol_info.volume_min, min(lots, symbol_info.volume_max))


def send_trade_order(symbol, order_type, price, volume, sl, tp, symbol_info):
    sl = round(sl, symbol_info.digits)
    tp = round(tp, symbol_info.digits)
    price = round(price, symbol_info.digits)

    request = {
        "action": mt5.TRADE_ACTION_PENDING,  # Changed to pending for limit structure placement
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": DEVIATION,
        "magic": MAGIC_NUMBER,
        "comment": "ICT AMD Limit Trade",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_mode(symbol_info),
    }

    result = mt5.order_send(request)
    if result is None:
        print(f"Order send returned None. Last error: {mt5.last_error()}")
    elif result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Order failed! Retcode: {result.retcode}, comment: {result.comment}")
    else:
        print(f"Limit order executed. Ticket: {result.order}, volume: {volume}, Entry: {price:.2f}, SL: {sl:.2f}, TP: {tp:.2f}")


def check_open_positions():
    positions = mt5.positions_get(magic=MAGIC_NUMBER)
    orders = mt5.orders_get(magic=MAGIC_NUMBER)
    
    total_active = 0
    if positions is not None:
        total_active += len(positions)
    if orders is not None:
        total_active += len(orders)
        
    return total_active

from datetime import datetime

from .config import (
    LOCAL_SWEEP_LOOKBACK,
    SWING_LOOKBACK,
    FIB_TARGET_EXTENSION,
    DISPLACEMENT_MULTIPLIER,
    MIN_RISK_REWARD,
    MIN_SETUP_SCORE,
)


def _bullish_fvg(df, index):
    return (
        index >= 2
        and float(df.iloc[index]["low"]) > float(df.iloc[index - 2]["high"])
    )


def _bearish_fvg(df, index):
    return (
        index >= 2
        and float(df.iloc[index]["high"]) < float(df.iloc[index - 2]["low"])
    )


def _candle_range(candle):
    return float(candle["high"]) - float(candle["low"])


class AMDWeeklyStrategy:
    def __init__(
        self,
        displacement_multiplier=DISPLACEMENT_MULTIPLIER,
        local_sweep_lookback=LOCAL_SWEEP_LOOKBACK,
        swing_lookback=SWING_LOOKBACK,
        fib_target_extension=FIB_TARGET_EXTENSION,
        min_rr=MIN_RISK_REWARD,
        min_setup_score=MIN_SETUP_SCORE,
        poi_timeout_bars=POI_TIMEOUT_BARS,
        confirm_timeout_bars=CONFIRM_TIMEOUT_BARS,
    ):
        self.displacement_multiplier = displacement_multiplier
        self.local_sweep_lookback = local_sweep_lookback
        self.swing_lookback = swing_lookback
        self.fib_target_extension = fib_target_extension
        self.min_rr = min_rr
        self.min_setup_score = min_setup_score
        self.poi_timeout_bars = poi_timeout_bars
        self.confirm_timeout_bars = confirm_timeout_bars
        self.last_signal_time = None

    def _average_range(self, df, bars=10):
        sample = df.iloc[-bars - 1:-1]
        if sample.empty:
            return 0.0
        return float(
            (sample["high"] - sample["low"]).mean()
        )

    def _higher_timeframe_bias(self, df):
        completed = df.iloc[:-1]
        if len(completed) < 3:
            return None

        latest = completed.iloc[-1]
        previous = completed.iloc[-2]
        latest_close = float(latest["close"])
        if latest_close > float(previous["high"]):
            return "BUY"
        if latest_close < float(previous["low"]):
            return "SELL"
        if latest_close > float(latest["open"]):
            return "BUY"
        if latest_close < float(latest["open"]):
            return "SELL"
        return None

    def _swing_dealing_range(self, df):
        completed = df.iloc[:-1].reset_index(drop=True)
        lookback = self.swing_lookback
        if len(completed) < (lookback * 2) + 3:
            return None

        swing_high = None
        swing_low = None
        for index in range(len(completed) - lookback - 1, lookback - 1, -1):
            high = float(completed.iloc[index]["high"])
            low = float(completed.iloc[index]["low"])
            left = completed.iloc[index - lookback:index]
            right = completed.iloc[index + 1:index + lookback + 1]
            if swing_high is None and high > float(left["high"].max()) and high > float(right["high"].max()):
                swing_high = high
            if swing_low is None and low < float(left["low"].min()) and low < float(right["low"].min()):
                swing_low = low
            if swing_high is not None and swing_low is not None:
                break

        if swing_high is None or swing_low is None or swing_high <= swing_low:
            return None

        range_size = swing_high - swing_low
        return {
            "low": swing_low,
            "high": swing_high,
            "equilibrium": swing_low + range_size / 2,
            "bullish_target": swing_high + range_size * self.fib_target_extension,
            "bearish_target": swing_low - range_size * self.fib_target_extension,
        }

    def _make_signal(self, direction, model, entry, stop, target, current_time):
        entry = float(entry)
        stop = float(stop)
        target = float(target)

        if direction == "BUY" and not (stop < entry < target):
            return None
        if direction == "SELL" and not (target < entry < stop):
            return None

        risk = abs(entry - stop)
        reward = abs(target - entry)

        if risk <= 0 or reward <= 0 or reward / risk < self.min_rr:
            return None

        if self.last_signal_time == current_time:
            return None

        self.last_signal_time = current_time

        return {
            "signal": direction,
            "model": model,
            "time": current_time,
            "entry": entry,
            "sl": stop,
            "tp": target,
            "risk_price": risk,
            "rr": reward / risk,
        }

    def update(self, df_bias, df_4h, df_1h, current_time):
        if min(len(df_bias), len(df_4h), len(df_1h)) < 30:
            return None

        bias = self._higher_timeframe_bias(df_bias)
        dealing_range = self._swing_dealing_range(df_4h)
        if bias is None or dealing_range is None:
            return None
        equilibrium = dealing_range["equilibrium"]

        # Use completed execution candles only. The setup is sweep -> displacement
        # -> FVG, with the limit entry placed inside the newly created gap.
        execution = df_1h.iloc[:-1].reset_index(drop=True)
        if len(execution) < max(12, self.local_sweep_lookback + 3):
            return None

        current_index = len(execution) - 1
        current = execution.iloc[current_index]
        average_range = self._average_range(execution)
        if average_range <= 0:
            return None

        current_range = _candle_range(current)
        current_high = float(current["high"])
        current_low = float(current["low"])

        sweep = execution.iloc[current_index - 1]
        prior = execution.iloc[
            max(0, current_index - self.local_sweep_lookback - 1):current_index - 1
        ]
        if prior.empty or current_range < average_range * self.displacement_multiplier:
            return None

        prior_high = float(prior["high"].max())
        prior_low = float(prior["low"].min())

        # Score confluence instead of requiring every factor. FVG remains
        # mandatory because it supplies the limit-entry zone and stop anchor.
        bullish_fvg = next(
            (index for index in range(current_index, max(1, current_index - 3), -1)
             if _bullish_fvg(execution, index)),
            None,
        )
        bearish_fvg = next(
            (index for index in range(current_index, max(1, current_index - 3), -1)
             if _bearish_fvg(execution, index)),
            None,
        )
        bullish_sweep = float(sweep["low"]) < prior_low
        bearish_sweep = float(sweep["high"]) > prior_high
        bullish_bos = float(current["close"]) > max(prior_high, float(sweep["high"]))
        bearish_bos = float(current["close"]) < min(prior_low, float(sweep["low"]))

        bullish_score = sum((
            bias == "BUY",
            bullish_sweep,
            bullish_bos,
            bullish_fvg is not None,
            float(current["close"]) < equilibrium,
        )) / 5
        if bullish_score >= self.min_setup_score and bullish_fvg is not None:
            fvg_low = float(execution.iloc[bullish_fvg - 2]["high"])
            fvg_high = float(execution.iloc[bullish_fvg]["low"])
            entry = (fvg_low + fvg_high) / 2
            stop = float(sweep["low"])
            target = max(
                float(df_1h["high"].iloc[:-1].tail(50).max()),
                float(df_4h["high"].iloc[:-1].tail(50).max()),
                dealing_range["bullish_target"],
            )
            signal = self._make_signal("BUY", "CONFLUENCE_FVG", entry, stop, target, current_time)
            if signal is not None:
                signal["setup_score"] = bullish_score
                return signal

        bearish_score = sum((
            bias == "SELL",
            bearish_sweep,
            bearish_bos,
            bearish_fvg is not None,
            float(current["close"]) > equilibrium,
        )) / 5
        if bearish_score >= self.min_setup_score and bearish_fvg is not None:
            fvg_low = float(execution.iloc[bearish_fvg]["high"])
            fvg_high = float(execution.iloc[bearish_fvg - 2]["low"])
            entry = (fvg_low + fvg_high) / 2
            stop = float(sweep["high"])
            target = min(
                float(df_1h["low"].iloc[:-1].tail(50).min()),
                float(df_4h["low"].iloc[:-1].tail(50).min()),
                dealing_range["bearish_target"],
            )
            signal = self._make_signal("SELL", "CONFLUENCE_FVG", entry, stop, target, current_time)
            if signal is not None:
                signal["setup_score"] = bearish_score
                return signal

        return None

    def reset(self):
        self.last_signal_time = None
        self.fresh_1h_poi = None


def run_bot():
    if mt5 is None:
        raise RuntimeError("MetaTrader5 is required to run the ICT strategy bot.")
    if not initialize_mt5():
        return

    strategy = AMDWeeklyStrategy(
        displacement_multiplier=DISPLACEMENT_MULTIPLIER,
        local_sweep_lookback=LOCAL_SWEEP_LOOKBACK,
        min_rr=MIN_RISK_REWARD,
        poi_timeout_bars=POI_TIMEOUT_BARS,
        confirm_timeout_bars=CONFIRM_TIMEOUT_BARS,
    )

    last_processed_candle_time = None

    try:
        while True:
            df_bias = get_market_data(SYMBOL, BIAS_TIMEFRAME, 150)
            df_4h = get_market_data(SYMBOL, POI_TIMEFRAME, 300)
            df_1h = get_market_data(SYMBOL, CONFIRM_TIMEFRAME, 200)

            if df_bias is None or df_4h is None or df_1h is None:
                time.sleep(10)
                continue

            latest_candle_time = df_1h["time"].iloc[-1].to_pydatetime()

            if latest_candle_time > (last_processed_candle_time or datetime.min):
                last_processed_candle_time = latest_candle_time
                result = strategy.update(
                    df_bias, df_4h, df_1h, latest_candle_time
                )

                # Keep the existing order-placement logic here.
                if result is not None:
                    print(f"Signal received: {result}")

            time.sleep(15)

    except KeyboardInterrupt:
        print("Bot tracking halted manually.")
    finally:
        mt5.shutdown()
        print("MetaTrader Interface Connection Terminated.")


if __name__ == "__main__":
    run_bot()
