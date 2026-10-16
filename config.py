"""Central configuration for the MT5 trading bot.

This file defines symbol settings, timeframe structure, trade sizing, risk rules,
and live/backtest filtering settings. All strategy parameters are kept here so
changing a value does not require touching multiple modules.
"""

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - used when running UI/API without MT5 installed
    mt5 = None

import calendar
from datetime import datetime, time as dtime

# =====================================================================
# SYMBOL CONFIGURATION
# =====================================================================
SYMBOL = "US100"
PIP_SIZE_OVERRIDE = None  # Use broker pip size for Forex

# =====================================================================
# MULTI-TIMEFRAME ARCHITECTURE
# =====================================================================
# These default values are used when MetaTrader5 is unavailable (for example in
# the web/API-only environment). Real MT5 values are still used when the terminal
# is installed and connected.
if mt5 is None:
    TIMEFRAME_M5 = 5
    TIMEFRAME_H1 = 16385
    TIMEFRAME_H4 = 16388
else:
    TIMEFRAME_M5 = mt5.TIMEFRAME_M5
    TIMEFRAME_H1 = mt5.TIMEFRAME_H1
    TIMEFRAME_H4 = mt5.TIMEFRAME_H4

BIAS_TIMEFRAME = TIMEFRAME_H4    # 4H trend tracking
POI_TIMEFRAME = TIMEFRAME_H1     # 1H Point of Interest zone hunting
CONFIRM_TIMEFRAME = TIMEFRAME_M5  # 5M confirmation & execution timeframe

# =====================================================================
# STRATEGY TUNING PARAMETERS
# =====================================================================
LOCAL_SWEEP_LOOKBACK = 5       # Candles back to search for liquidity sweeps
SWING_LOOKBACK = 3             # H4 candles on each side to confirm swing points
FIB_TARGET_EXTENSION = 1.0     # First expansion target beyond the dealing range
DISPLACEMENT_MULTIPLIER = 1.5  # Scale ratio vs ATR window for displacement 
POI_TIMEOUT_BARS = 200         # Maximum bars a 1H POI can sit un-tapped
CONFIRM_TIMEOUT_BARS = 60      # Max execution timeout bars for 5M structure

# =====================================================================
# ORDER & RISK MANAGEMENT
# =====================================================================
RISK_PERCENT = 0.01            # 1% equity risk per trade
LOT_SIZE = 0.1                 # Fixed lot size per trade
MIN_RISK_REWARD = 3.0          # Minimum mathematical RR threshold to take trade
MIN_SETUP_SCORE = 0.80         # Minimum confluence score: 4 of 5 setup factors
MAX_SPREAD_PIPS = 3.0          # Max acceptable spread in index points
MAGIC_NUMBER = 123456          # Unique identification ID for positions
DEVIATION = 20                 # Execution price slippage cap in points
DAILY_PROFIT_TARGET = 20.0     # Stop opening trades after this day's net profit

# =====================================================================
# ECONOMIC NEWS FILTERING
# =====================================================================
NEWS_FILTER_ENABLED = True
NEWS_CURRENCIES = ("USD",)    # US100 is most sensitive to USD releases
NEWS_MIN_IMPACT = "high"      # "high" or "medium"
NEWS_BLOCK_BEFORE_MINUTES = 30
NEWS_BLOCK_AFTER_MINUTES = 30
NEWS_CACHE_MINUTES = 15

# =====================================================================
# BACKTESTING
# =====================================================================
STARTING_BALANCE = 135.62
BACKTEST_END = datetime.utcnow()
_backtest_start_month = (BACKTEST_END.month - 8) % 12 or 12
_backtest_start_year = BACKTEST_END.year - (1 if BACKTEST_END.month <= 8 else 0)
_backtest_start_day = min(
	BACKTEST_END.day,
	calendar.monthrange(_backtest_start_year, _backtest_start_month)[1],
)
BACKTEST_START = BACKTEST_END.replace(
	year=_backtest_start_year,
	month=_backtest_start_month,
	day=_backtest_start_day,
)


