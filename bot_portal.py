import reflex as rx
import asyncio

# ==========================================
# 1. INTEGRATING YOUR 6 MODULAR COMPONENTS
# ==========================================
# Reflex runs everything inside a single project framework context.
try:
    from . import config as bot_config
    from . import phase3_mt5_connection as mt5_conn
    from . import ict as strategy
    from . import phase4_rule_based_bot as live_bot
    from . import news_filter as time_filter
    from . import backtester as sim_engine
    MODULES_LOADED = True
except ImportError as e:
    MODULES_LOADED = False
    print(f"⚠️ Core modules fallback activated for local UI testing: {e}")


# ==========================================
# 2. STATE MANAGEMENT (BACKEND ENGINE)
# ==========================================
class State(rx.State):
    """Handles the reactive backend variables and background loops for your subscribers."""
    # Form input tracking variables
    subscriber_id: str = "SUB-2026-X"
    account_number: str = "123456"
    password: str = ""
    broker_server: str = "FBS-Demo"
    target_symbol: str = "NAS100"
    risk_percentage: float = 1.0
    
    # Live operational status tracking variables
    is_running: bool = False
    status_message: str = "Bot is dormant / inactive."
    status_color: str = "gray"

    @rx.event
    def set_subscriber_id(self, value: str):
        self.subscriber_id = value

    @rx.event
    def set_account_number(self, value: str):
        self.account_number = value

    @rx.event
    def set_password(self, value: str):
        self.password = value

    @rx.event
    def set_broker_server(self, value: str):
        self.broker_server = value

    @rx.event
    def set_target_symbol(self, value: str):
        self.target_symbol = value

    @rx.event(background=True)
    async def toggle_bot_execution(self):
        """Spawns an asynchronous background worker execution thread safely without crashing the UI."""
        async with self:
            # If the bot is already running, turn it off cleanly
            if self.is_running:
                self.is_running = False
                self.status_message = "Termination signal sent. Bot is dormant."
                self.status_color = "gray"
                return

            # Input validation checks before execution kicks off
            if not self.password:
                self.status_message = "🔒 Access Denied: Secure trading password is required."
                self.status_color = "red"
                return

            # Turn the bot state indicator on
            self.is_running = True
            self.status_color = "green"
            self.status_message = f"🚀 Live loop actively monitoring {self.target_symbol}..."

        # Infinite loop representation running in the background thread framework
        while True:
            async with self:
                # Check if the user clicked the stop button
                if not self.is_running:
                    break
                
            # --- YOUR TRADING LOGIC TRIGGERS HERE ---
            if MODULES_LOADED:
                # e.g., live_bot.check_market_and_execute(self.target_symbol, float(self.risk_percentage))
                pass
            else:
                # Mock environment behavior simulation
                print(f"[REFLEX BACKGROUND PROCESS] Checking ticker pricing array feeds for {self.target_symbol}...")
            
            # Non-blocking pause interval (e.g., checks every 5 seconds)
            await asyncio.sleep(5)


# ==========================================
# 3. USER INTERFACE (FRONTEND VIEW)
# ==========================================
def index() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.heading("🤖 AI Trading Bot Subscription Portal", size="7"),
            rx.text(
                f"Core Modules Integration: {'🟢 Connected' if MODULES_LOADED else '🟡 Bypassed for UI testing'}",
                color="gray"
            ),
            rx.divider(),

            # Operational Metrics Status Card Widget Component
            rx.card(
                rx.vstack(
                    rx.text("Live Operational Telemetry Status:", font_weight="bold"),
                    rx.badge(State.status_message, color_scheme=State.status_color, variant="surface", size="3"),
                    align="center",
                    width="100%"
                ),
                width="100%",
                padding="4"
            ),

            # Configuration input panel form parameters
            rx.vstack(
                rx.text("👤 Subscriber Context Registration", font_weight="bold", size="4"),
                rx.input(placeholder="Subscriber Account ID String", value=State.subscriber_id, on_change=State.set_subscriber_id, width="100%"),
                
                rx.text("📊 MT5 Broker Node Configuration", font_weight="bold", size="4"),
                rx.input(placeholder="MT5 Broker Account ID Number", value=State.account_number, on_change=State.set_account_number, width="100%"),
                rx.input(placeholder="Secure Password String", type="password", value=State.password, on_change=State.set_password, width="100%"),
                rx.input(placeholder="Broker Network Access Server Name", value=State.broker_server, on_change=State.set_broker_server, width="100%"),
                
                rx.text("🎯 Target Asset Settings", font_weight="bold", size="3"),
                rx.select(["XAUUSD", "NAS100", "EURUSD"], value=State.target_symbol, on_change=State.set_target_symbol, width="100%"),
                
                rx.button(
                    rx.cond(State.is_running, "💥 Emergency STOP Bot Loop", "🚀 Deploy & Run Trading Loop"),
                    color_scheme=rx.cond(State.is_running, "red", "blue"),
                    width="100%",
                    on_click=State.toggle_bot_execution
                ),
                spacing="3",
                width="100%"
            ),
            spacing="5",
            padding="6",
            border_radius="lg",
            box_shadow="md",
            bg="var(--gray-2)",
            width="450px"
        ),
        padding_top="10%"
    )


# Register our layout cleanly within the app pipeline
app = rx.App()
app.add_page(index)
