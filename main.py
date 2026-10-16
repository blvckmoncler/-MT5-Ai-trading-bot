"""Entry point for the MetaTrader 5 trading bot.

This script simply launches the main live trading loop defined in the bot module.
It is intentionally thin so the actual strategy and execution logic remain in
separate files for easier testing and maintenance.
"""

# Import the bot entry function from the live trading module.
from .phase4_rule_based_bot import run_bot


# Run the bot when this script is executed directly.
if __name__ == "__main__":
    run_bot()
