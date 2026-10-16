# Trading Bot Portal Overview

This project is a Reflex-based frontend and state controller for a trading bot subscription portal. It connects a user interface to a backend state machine and prepares the app to run trading logic in a background loop while keeping the UI responsive.

The main logic lives in `bot_portal.py`.

## File purpose

`bot_portal.py` does three main jobs:

1. Loads the trading bot modules that contain the actual broker, strategy, and simulation logic.
2. Defines reactive app state and background execution behavior.
3. Renders the web interface where a user configures the bot and starts/stops it.

---

## 1) Import and module integration

```python
import reflex as rx
import asyncio
```

- `reflex as rx` imports the Reflex framework used to build the web app and reactive state.
- `asyncio` provides the asynchronous sleep and background task handling used by the bot loop.

```python
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
```

This block tries to import the actual bot modules:

- `config`: bot configuration
- `phase3_mt5_connection`: MT5 connection logic
- `ict`: strategy logic
- `phase4_rule_based_bot`: live trading logic
- `news_filter`: market/news filtering logic
- `backtester`: simulation/testing engine

If those modules are unavailable (for example, during local UI-only testing), the app still runs in a reduced fallback mode. The `MODULES_LOADED` flag tells the UI whether the full trading stack is connected.

---

## 2) State management: `State`

```python
class State(rx.State):
```

This is the main reactive backend state for the Reflex app. It stores values used by the interface and the bot execution loop.

### Stored variables

These fields represent the broker credentials and trading configuration:

- `subscriber_id`: unique subscriber or account identifier
- `account_number`: broker account number
- `password`: secure password used to authenticate trading access
- `broker_server`: broker server name
- `target_symbol`: asset symbol to track (for example `NAS100`)
- `risk_percentage`: risk amount percentage for the bot

These are live operational variables:

- `is_running`: whether the bot loop is currently active
- `status_message`: text shown in the UI to explain the current bot state
- `status_color`: color state used by the badge in the interface (`gray`, `green`, `red`)

### Input setters

Each method updates a state field when the UI changes an input:

- `set_subscriber_id(self, value: str)`
- `set_account_number(self, value: str)`
- `set_password(self, value: str)`
- `set_broker_server(self, value: str)`
- `set_target_symbol(self, value: str)`

These are decorated with `@rx.event`, which makes them callable from the frontend form controls.

### Start/stop bot trigger

```python
@rx.event(background=True)
async def toggle_bot_execution(self):
```

This is the main control method that starts or stops the background trading loop.

What it does:

1. Checks whether the bot is already running.
2. If it is running, it sets `is_running = False` and changes the status to a dormant state.
3. If it is not running, it validates the password before launching.
4. If the password is missing, it blocks execution and shows an error.
5. If validation passes, it changes the bot to a running state and updates the status message.

After the state changes, the function enters a background infinite loop:

```python
while True:
    async with self:
        if not self.is_running:
            break
```

This loop keeps checking whether the user has stopped the bot. If not, it can trigger trading logic. In the current code, the actual trading action is intentionally left as a placeholder:

```python
if MODULES_LOADED:
    # e.g., live_bot.check_market_and_execute(self.target_symbol, float(self.risk_percentage))
    pass
else:
    print(f"[REFLEX BACKGROUND PROCESS] Checking ticker pricing array feeds for {self.target_symbol}...")
```

- If the bot modules were successfully imported, this is where real trading checks would be triggered.
- If not, the app simulates a fallback behavior in the console.

The loop pauses between checks using:

```python
await asyncio.sleep(5)
```

This prevents the loop from running continuously and overwhelming the app.

---

## 3) UI page: `index()`

```python
def index() -> rx.Component:
```

This function builds the main dashboard page of the app. It returns a Reflex component tree used to render the portal in the browser.

### Page layout

The page is centered and uses a stack layout:

```python
return rx.center(
    rx.vstack(
        ...
    )
)
```

This creates a clean card-like dashboard in the middle of the page.

### Header

```python
rx.heading("🤖 AI Trading Bot Subscription Portal", size="7")
```

Displays the page title.

```python
rx.text(
    f"Core Modules Integration: {'🟢 Connected' if MODULES_LOADED else '🟡 Bypassed for UI testing'}",
    color="gray"
)
```

Shows whether the full app modules were successfully loaded.

### Status card

```python
rx.card(
    rx.vstack(
        rx.text("Live Operational Telemetry Status:", font_weight="bold"),
        rx.badge(State.status_message, color_scheme=State.status_color, variant="surface", size="3"),
        align="center",
        width="100%"
    ),
    width="100%",
    padding="4"
)
```

This banner displays the current bot status, such as:

- dormant
- access denied
- live monitoring
- termination in progress

It uses the state fields `status_message` and `status_color` for live updates.

### Configuration panel

```python
rx.vstack(
    rx.text("👤 Subscriber Context Registration", font_weight="bold", size="4"),
    rx.input(placeholder="Subscriber Account ID String", value=State.subscriber_id, on_change=State.set_subscriber_id, width="100%"),
```

This section captures the user’s configuration fields through Reflex input widgets.

The following controls are defined:

- `Subscriber Account ID`
- `MT5 Broker Account Number`
- `Secure Password`
- `Broker Server`
- `Target Asset` (`XAUUSD`, `NAS100`, `EURUSD`)

The `value` parameter binds the UI control directly to the state variable, while `on_change` calls the corresponding setter method.

### Start/Stop button

```python
rx.button(
    rx.cond(State.is_running, "💥 Emergency STOP Bot Loop", "🚀 Deploy & Run Trading Loop"),
    color_scheme=rx.cond(State.is_running, "red", "blue"),
    width="100%",
    on_click=State.toggle_bot_execution
)
```

This button toggles the bot between running and stopped states.

- If `is_running` is `True`, it shows a stop button and colors it red.
- If `is_running` is `False`, it shows a start button and colors it blue.
- Clicking the button calls `State.toggle_bot_execution`.

---

## 4) App registration

```python
app = rx.App()
app.add_page(index)
```

This creates the Reflex app and registers the `index` page as the main page for the website.

In practical terms, this is the step that makes the portal available to the browser when the project is launched.

---

## Overall behavior

When the app starts:

1. It imports the trading modules if available.
2. It initializes the backend state.
3. It renders the portal form and status section.
4. The user enters broker and trading details.
5. Clicking the action button either starts or stops the background bot loop.
6. The status badge updates in real time to reflect what the bot is doing.

This file serves as the central UI + control layer, while the actual MT5, strategy, signal, and backtesting logic is expected to live in the imported modules.
