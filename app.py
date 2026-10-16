import streamlit as st
import requests

# Set up clean browser window telemetry headers
st.set_page_config(
    page_title="AI Trading Bot Dashboard",
    page_icon="🤖",
    layout="centered"
)

# Backend FastAPI gateway URL definition
BACKEND_URL = "http://127.0.0.1:8000"

st.title("🤖 AI Trading Bot Subscription Portal")
st.write("First-year informatics project frontend console linking directly to the local FastAPI backend over web requests.")
st.divider()

# ==========================================
# 1. VISUAL STATUS CHECK WIDGET
# ==========================================
try:
    health_check = requests.get(f"{BACKEND_URL}/")
    if health_check.status_code == 200:
        st.success("🟢 Connected to mainapi.py Backend Gateway Server")
    else:
        st.error("⚠️ Backend returned an unexpected response status.")
except requests.exceptions.ConnectionError:
    st.error("🔴 Connection Failure: Please ensure the backend FastAPI service is running before starting.")
    st.stop()

# ==========================================
# 2. USER PROFILE CONTEXT REGISTRATION
# ==========================================
st.header("👤 Subscriber Profile Credentials")
subscriber_id = st.text_input("Subscriber ID Account String", value="SUB-2026-X", help="Your unique web client account tag.")

# ==========================================
# 3. METATRADER 5 TERMINAL INTEGRATION CONTROL FORM
# ==========================================
st.header("📊 MT5 Broker Node Configuration")

with st.form("trading_control_form"):
    account_number = st.number_input("MT5 Broker Account ID Number", value=123456, step=1)
    password = st.text_input("Master or Investor Secure Password String", value="", type="password")
    broker_server = st.text_input("Broker Network Access Server Name", value="FBS-Demo")
    
    # Structural Asset Configuration Parameters
    col1, col2 = st.columns(2)
    with col1:
        target_symbol = st.selectbox("Trading Ticker Asset Pair", ["XAUUSD", "NAS100", "EURUSD"])
    with col2:
        risk_management_budget = st.slider("Risk Exposure Percentage Per Order", min_value=0.1, max_value=5.0, value=1.0, step=0.1)
        
    submit_execution_trigger = st.form_submit_button("🚀 Deploy & Run Trading Loop")

# ==========================================
# 4. FORM TRANSACTION PAYLOAD PROCESSING
# ==========================================
if submit_execution_trigger:
    if not password:
        st.warning("🔒 Submission Blocked: An active security credential phrase is required.")
    else:
        # Wrap visual state parameters strictly into the exact schema expected by mainapi.py Pydantic Models
        payload = {
            "subscriber_id": subscriber_id,
            "account_number": int(account_number),
            "password": password,
            "server": broker_server,
            "symbol": target_symbol,
            "risk_percentage": risk_management_budget
        }
        
        with st.spinner("Dispatching credentials payload parameters to API workers..."):
            try:
                response = requests.post(f"{BACKEND_URL}/api/v1/bot/start", json=payload)
                
                if response.status_code == 202:
                    st.balloons()
                    st.success(f"✔️ {response.json()['message']}")
                else:
                    st.error(f"❌ Core Error Code {response.status_code}: {response.json().get('detail', 'Validation rejected.')}")
            except Exception as error_msg:
                st.error(f"Internal Pipeline Error: {error_msg}")

# ==========================================
# 5. DIAGNOSTICS & SYSTEM TERMINATION ENGINE
# ==========================================
st.divider()
st.header("🛑 Live Control Terminal Telemetry")

col_status, col_kill = st.columns([2, 1])

with col_status:
    if st.button("🔄 Pull Live Bot Operational Telemetry Status"):
        try:
            status_check = requests.get(f"{BACKEND_URL}/api/v1/bot/status/{subscriber_id}")
            if status_check.status_code == 200:
                bot_live = status_check.json()["is_running"]
                if bot_live:
                    st.warning("⚡ Bot Engine state parameter confirms active automated polling loops.")
                else:
                    st.info("💤 Bot Engine state parameter confirms dormant/inactive tracking status.")
        except Exception as e:
            st.error(f"Failed to pull live runtime telemetry: {e}")

with col_kill:
    if st.button("💥 Emergency STOP Bot Loop", type="secondary"):
        try:
            stop_request = requests.post(f"{BACKEND_URL}/api/v1/bot/stop", params={"subscriber_id": subscriber_id})
            if stop_request.status_code == 200:
                st.error(f"🛑 {stop_request.json()['message']}")
        except Exception as e:
            st.error(f"Failed to issue critical stop instruction: {e}")
