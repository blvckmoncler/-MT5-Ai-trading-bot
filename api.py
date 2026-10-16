import logging
import threading
import time
from typing import Dict, Any, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field

# ==========================================
# 1. INTEGRATING YOUR 6 MODULAR COMPONENTS
# ==========================================
# These imports bridge your existing scripts directly into the web app api layers.
from . import backtester as sim_engine
from . import config as bot_config
from . import ict as fvg_strat
from . import news_filter as time_filter
from . import phase3_mt5_connection as mt5_conn
from . import phase4_rule_based_bot as live_bot

MODULES_LOADED = True

# Initialize the core FastAPI Application object
app = FastAPI(
    title="Modular AI Trading Bot Subscription Service",
    description="Python 3.12 API backend orchestrating MT5 logic execution, data rules validation, and subscription status verification.",
    version="1.0.0"
)

# Active background bot monitor tracking dict (In-memory map for the MVP)
active_subscriber_bots: Dict[str, bool] = {}


# ==========================================
# 2. PYDANTIC VALIDATION MODELS (SCHEMAS)
# ==========================================
class BotStartPayload(BaseModel):
    """Enforces strict structural data types on payloads sent from the frontend user portal."""
    subscriber_id: str = Field(..., description="Unique alphanumeric identifier for the system account user.")
    account_number: int = Field(..., description="The MT5 broker trading account number.")
    password: str = Field(..., description="The secure master or investor password required by MT5 terminal interfaces.")
    server: str = Field(..., description="The precise live or demo broker network server address.")
    symbol: str = Field(default="XAUUSD", description="The standard trade asset ticker symbol (e.g., XAUUSD, NAS100).")
    risk_percentage: float = Field(default=1.0, ge=0.1, le=5.0, description="Risk budget parameter per single open trade position.")

class BotStatusResponse(BaseModel):
    subscriber_id: str
    is_running: bool
    active_symbol: Optional[str] = None


# ==========================================
# 3. BACKGROUND EXECUTION ENGINE (THE LOOP)
# ==========================================
def run_continuous_trading_loop(payload: BotStartPayload):
    """
    Runs the bot logic in a background thread and keeps the subscriber state
    synchronized with the actual loop lifecycle.
    """
    sub_id = payload.subscriber_id
    active_subscriber_bots[sub_id] = True

    print(f"🚀 [WORKER] Spawning dedicated trading pipeline instance for user: {sub_id}")

    try:
        if MODULES_LOADED and hasattr(live_bot, "run_bot"):
            # Start the real MT5 bot in a daemon thread so the API remains responsive.
            worker = threading.Thread(
                target=live_bot.run_bot,
                name=f"bot-{sub_id}",
                daemon=True,
            )
            worker.start()
            while active_subscriber_bots.get(sub_id, False):
                time.sleep(0.5)
            return

        count = 0
        while active_subscriber_bots.get(sub_id, False) and count < 10:
            print(f"📊 [MOCK LOOP] Bot running for user {sub_id} tracking {payload.symbol}... Tick {count}")
            time.sleep(2)
            count += 1
    except Exception as exc:
        logging.exception("Background bot loop failed for %s", sub_id)
        active_subscriber_bots[sub_id] = False
        raise RuntimeError(f"Bot loop crashed for {sub_id}: {exc}") from exc
    finally:
        active_subscriber_bots[sub_id] = False


# ==========================================
# 4. ENDPOINT ROUTING MANAGEMENT (API CONTROL)
# ==========================================
@app.get("/", tags=["Health System Check"])
async def root_health_ping():
    """Confirms operational up-time parameters for verification tests."""
    return {
        "status": "online",
        "python_version": "3.12.3",
        "modules_integrated": MODULES_LOADED
    }

@app.post("/api/v1/bot/start", status_code=status.HTTP_202_ACCEPTED, tags=["Bot Control Engines"])
async def start_subscriber_bot(payload: BotStartPayload, background_tasks: BackgroundTasks):
    """
    Validates the input parameters using Pydantic, accepts the trade request packet instantly, 
    and offloads the infinite polling cycle to background runtime handlers.
    """
    sub_id = payload.subscriber_id
    
    # Restrict spinning up multiple concurrent loops for the same exact system subscription ID
    if active_subscriber_bots.get(sub_id, False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"An active trading loop instance is already running for user profile: {sub_id}"
        )
    
    # Hand off execution loop sequence cleanly over to the async runner pool
    background_tasks.add_task(run_continuous_trading_loop, payload)
    
    return {
        "status": "accepted",
        "message": f"Trading bot deployment initialized for profile: {sub_id}.",
        "target_asset": payload.symbol
    }

@app.post("/api/v1/bot/stop", tags=["Bot Control Engines"])
async def stop_subscriber_bot(subscriber_id: str):
    """Flips the run flag so the background loop can terminate cleanly."""
    if not active_subscriber_bots.get(subscriber_id, False):
        return {"status": "ignored", "message": f"No active loop running for subscriber context {subscriber_id}."}

    active_subscriber_bots[subscriber_id] = False
    return {"status": "success", "message": f"Termination flag dispatched safely for subscription context: {subscriber_id}."}

@app.get("/api/v1/bot/status/{subscriber_id}", response_model=BotStatusResponse, tags=["Bot Diagnostics Services"])
async def query_bot_telemetry(subscriber_id: str):
    """Fetches diagnostic state metrics for live monitoring widgets."""
    is_running = active_subscriber_bots.get(subscriber_id, False)
    return BotStatusResponse(subscriber_id=subscriber_id, is_running=is_running)
