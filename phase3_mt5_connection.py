"""
Phase 3 — talk to MT5 programmatically.

Everything here is about the terminal connection and correctly interpreting
what MT5's API gives you back. No strategy or trading decisions live in this
file.

This layer handles initialization, market data retrieval, and small helper
calculations required by the strategy modules.
"""

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - used by non-MT5 web/API environments
    mt5 = None

import pandas as pd

from .config import PIP_SIZE_OVERRIDE, SYMBOL

# -----------------------------------------------------------------------------
# MT5 connection and data access helpers
# -----------------------------------------------------------------------------


def initialize_mt5():
    """Opens the connection between this script and the running MT5 terminal."""
    if mt5 is None:
        raise RuntimeError("MetaTrader5 is required to initialize the trading terminal.")
    # Path to the terminal executable. This is required for a live MT5 connection.
    terminal_path = r"C:\Program Files\MetaTrader 5\terminal64.exe"

    # Initialize the terminal connection before querying account or market data.
    if not mt5.initialize(path=terminal_path):
        print(f"MT5 initialization failed: {mt5.last_error()}")
        return False

    # Confirm that the terminal and account are usable; otherwise shut down cleanly.
    if mt5.terminal_info() is None or mt5.account_info() is None:
        print(f"MT5 connection unavailable: {mt5.last_error()}")
        mt5.shutdown()
        return False

    # Make sure the configured symbol exists and is selectable in the terminal.
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        print(f"Symbol '{SYMBOL}' was not found.")
        mt5.shutdown()
        return False

    if not info.visible and not mt5.symbol_select(SYMBOL, True):
        print(f"Could not select '{SYMBOL}': {mt5.last_error()}")
        mt5.shutdown()
        return False

    print(f"Connected to MT5: {info.name}")
    return True



def get_market_data(symbol, timeframe, bars):
    """Fetch the most recent candles for live trading."""
    # Pull the latest candlesticks from the current MT5 position.
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)

    if rates is None or len(rates) == 0:
        print(f"Failed to fetch market data for {symbol}.")
        print(f"MT5 error: {mt5.last_error()}")
        return None

    # Convert the MT5 time stamps into pandas datetime objects for easier analysis.
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def get_historical_range_data(symbol, timeframe, start_date, end_date):
    """Fetches all candles between two datetime objects."""
    # Pull the historical data range needed for backtesting and strategy analysis.
    rates = mt5.copy_rates_range(symbol, timeframe, start_date, end_date)

    if rates is None or len(rates) == 0:
        print(
            f"Failed to fetch historical data for {symbol}. "
            f"MT5 error: {mt5.last_error()}"
        )
        return None

    # Convert timestamps for consistent handling in pandas-based calculations.
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def get_pip_size(symbol_info):
    """Returns pip/point size in price terms."""
    # A broker-specific override can be used when the symbol's pip scale differs.
    if PIP_SIZE_OVERRIDE is not None:
        return PIP_SIZE_OVERRIDE
    if symbol_info.digits in (3, 5):
        return symbol_info.point * 10
    return symbol_info.point


def get_filling_mode(symbol_info):
    """Picks a filling mode the broker actually supports for this symbol."""
    # Some brokers only support immediate-or-cancel or fill-or-kill execution.
    modes = symbol_info.filling_mode
    
    if modes & mt5.ORDER_FILLING_IOC:
        return mt5.ORDER_FILLING_IOC
    if modes & mt5.ORDER_FILLING_FOK:
        return mt5.ORDER_FILLING_FOK
        
    return mt5.ORDER_FILLING_RETURN
