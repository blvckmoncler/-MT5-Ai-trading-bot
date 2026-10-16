"""Live execution loop for the rule-based MetaTrader 5 bot.

This module ties together the strategy, MT5 connection, and news filter to
decide whether a new limit order should be sent to the market.
"""

import time
try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - allows API/UI import without MT5 installed
    mt5 = None

from datetime import datetime, time as dtime, timezone

from .config import (
    SYMBOL, BIAS_TIMEFRAME, POI_TIMEFRAME, CONFIRM_TIMEFRAME,
    DISPLACEMENT_MULTIPLIER, LOCAL_SWEEP_LOOKBACK, SWING_LOOKBACK,
    FIB_TARGET_EXTENSION, MIN_RISK_REWARD, MIN_SETUP_SCORE,
    POI_TIMEOUT_BARS, CONFIRM_TIMEOUT_BARS, RISK_PERCENT, LOT_SIZE, MAX_SPREAD_PIPS,
    MAGIC_NUMBER, DEVIATION, DAILY_PROFIT_TARGET,
    NEWS_FILTER_ENABLED, NEWS_CURRENCIES, NEWS_MIN_IMPACT,
    NEWS_BLOCK_BEFORE_MINUTES, NEWS_BLOCK_AFTER_MINUTES, NEWS_CACHE_MINUTES,
)
from .phase3_mt5_connection import (
    initialize_mt5, get_market_data, get_pip_size, get_filling_mode
)
from .ict import AMDWeeklyStrategy
from .news_filter import news_blackout_active


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


def get_today_net_profit():
    """Return today's closed net profit for this bot and symbol."""
    now_utc = datetime.now(timezone.utc)
    start_of_day = datetime.combine(now_utc.date(), dtime.min, tzinfo=timezone.utc)
    deals = mt5.history_deals_get(start_of_day, now_utc)

    if deals is None:
        print(f"Could not read today's deal history: {mt5.last_error()}")
        return 0.0

    return sum(
        deal.profit + deal.commission + deal.swap + getattr(deal, "fee", 0.0)
        for deal in deals
        if deal.symbol == SYMBOL and deal.magic == MAGIC_NUMBER
    )


def daily_profit_target_reached():
    """Return True once today's closed net profit reaches the configured target."""
    today_net_profit = get_today_net_profit()
    if today_net_profit >= DAILY_PROFIT_TARGET:
        print(
            f"Daily profit target reached: ${today_net_profit:.2f}. "
            "No new trades will be opened today."
        )
        return True
    return False


def run_bot():
    if mt5 is None:
        raise RuntimeError("MetaTrader5 is required to run the live bot.")
    initialize_mt5()
    print(f"Bot starting. Tracking Weekly AMD setups for {SYMBOL}...")

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

    last_processed_candle_time = None

    try:
        while True:
            # Fetch extended historical data depth to avoid window calculation gaps.
            df_bias = get_market_data(SYMBOL, BIAS_TIMEFRAME, 150)
            df_4h = get_market_data(SYMBOL, POI_TIMEFRAME, 350)
            df_1h = get_market_data(SYMBOL, CONFIRM_TIMEFRAME, 1000)

            if df_bias is None or df_4h is None or df_1h is None or df_1h.empty:
                time.sleep(10)
                continue

            # Identify the newest 1H candle timestamp.
            latest_candle_time = df_1h['time'].iloc[-1].to_pydatetime()

            # Evaluate the strategy once per new 1H candle.
            if last_processed_candle_time is None or latest_candle_time > last_processed_candle_time:
                last_processed_candle_time = latest_candle_time
                
                # FIXED: Keep background state machine running so tracking stays synchronized
                result = strategy.update(df_bias, df_4h, df_1h, latest_candle_time)

                # Skip placing new orders if an active position or pending order is running
                if check_open_positions() > 0:
                    print("Active position or pending limit order running. Updating tracking matrix...")
                    continue

                if daily_profit_target_reached():
                    time.sleep(30)
                    continue

                if result is not None:
                    if NEWS_FILTER_ENABLED:
                        news_event = news_blackout_active(
                            datetime.now(timezone.utc),
                            currencies=NEWS_CURRENCIES,
                            minimum_impact=NEWS_MIN_IMPACT,
                            minutes_before=NEWS_BLOCK_BEFORE_MINUTES,
                            minutes_after=NEWS_BLOCK_AFTER_MINUTES,
                            cache_minutes=NEWS_CACHE_MINUTES,
                        )
                        if news_event is not None:
                            print(
                                f"News filter: skipping {result['signal']} setup "
                                f"near {news_event['currency']} release "
                                f"{news_event['title']} at {news_event['time'].isoformat()}"
                            )
                            continue

                    signal = result["signal"]
                    limit_entry_price = result["entry"]
                    stop_level = result["sl"]
                    target_level = result["tp"]

                    symbol_info = mt5.symbol_info(SYMBOL)
                    if symbol_info is None:
                        continue

                    pip_size = get_pip_size(symbol_info)
                    if not spread_is_acceptable(symbol_info, pip_size):
                        spread_points = symbol_info.spread * symbol_info.point
                        print(
                            f"Execution rejected: Market spread is {spread_points:.2f} "
                            f"points; maximum is {MAX_SPREAD_PIPS:.2f}."
                        )
                        continue

                    order_type = mt5.ORDER_TYPE_BUY_LIMIT if signal == "BUY" else mt5.ORDER_TYPE_SELL_LIMIT

                    sl_distance = abs(limit_entry_price - stop_level)
                    if sl_distance <= 0:
                        continue

                    account_info = mt5.account_info()
                    if account_info is None:
                        continue

                    sl_pips = sl_distance / pip_size
                    volume = calculate_lot_size(
                        symbol_info, sl_pips, RISK_PERCENT, account_info.balance
                    )

                    print(f"Placing {signal} LIMIT order at {limit_entry_price:.2f} | SL: {stop_level:.2f} | TP: {target_level:.2f}")
                    send_trade_order(SYMBOL, order_type, limit_entry_price, volume, stop_level, target_level, symbol_info)
                    
                    strategy.reset()  # Reset tracking state machine only after verified order routing

            time.sleep(15)  # Quick polling cycle checking for hourly bar transitions

    except KeyboardInterrupt:
        print("Bot tracking halted manually.")
    finally:
        mt5.shutdown()
        print("MetaTrader Interface Connection Terminated.")


if __name__ == "__main__":
    run_bot()
