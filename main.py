# === Required Libraries ===
from flask import Flask, request
from SmartApi.smartConnect import SmartConnect
import threading
import time
import os
import requests
import pyotp
from datetime import datetime

app = Flask(__name__)


def log_print(message):
    """Print with timestamp for better debugging"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


@app.route("/")
def home():
    log_print("🏠 Home route accessed - Bot is running!")
    return "Nifty Breakout Bot is running!"


# === ENV Variables ===
log_print("🔧 Loading environment variables...")
CLIENT_ID = os.getenv("CLIENT_ID")
API_KEY = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")
MPIN = os.getenv("MPIN")
TOTP_SECRET = os.getenv("TOTP_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

log_print("✅ Environment variables loaded:")
log_print(f"   CLIENT_ID: {'✅ Set' if CLIENT_ID else '❌ Missing'}")
log_print(f"   API_KEY: {'✅ Set' if API_KEY else '❌ Missing'}")
log_print(f"   SECRET_KEY: {'✅ Set' if SECRET_KEY else '❌ Missing'}")
log_print(f"   MPIN: {'✅ Set' if MPIN else '❌ Missing'}")
log_print(f"   TOTP_SECRET: {'✅ Set' if TOTP_SECRET else '❌ Missing'}")
log_print(f"   TELEGRAM_TOKEN: {'✅ Set' if TELEGRAM_TOKEN else '❌ Missing'}")
log_print(f"   TELEGRAM_CHAT_ID: {'✅ Set' if TELEGRAM_CHAT_ID else '❌ Missing'}")

# === Angel One Login ===
log_print("🔐 Attempting Angel One login...")
try:
    smart_api = SmartConnect(api_key=API_KEY)
    log_print("📱 Generating TOTP...")
    TOTP = pyotp.TOTP(TOTP_SECRET).now()
    log_print(f"🔑 TOTP Generated: {TOTP}")

    log_print("🚀 Generating session...")
    data = smart_api.generateSession(CLIENT_ID, MPIN, TOTP)
    log_print(f"📊 Session Response: {data}")

    refresh_token = data["data"]["refreshToken"]
    smart_api.setRefreshToken(refresh_token)
    log_print("✅ Angel One login successful!")
    log_print(f"🔄 Refresh Token Set: {refresh_token[:20]}...")

except Exception as e:
    log_print(f"❌ Angel One login failed: {e}")
    log_print("🛑 Bot cannot continue without Angel One connection")

# === Globals ===
current_trade = {
    "symbol": None,
    "token": None,
    "entry_price": None,
    "sl": None,
    "target": None,
    "side": None,
    "active": False,
}

log_print("🎯 Trade tracking initialized")
log_print(f"📊 Current trade status: {current_trade}")


# === Get Symbol Token ===
def get_symbol_token(symbol):
    """Get token for a given symbol from Angel One"""
    try:
        log_print(f"🔍 Searching for symbol token: {symbol}")

        # Example for NIFTY futures/options - adjust based on your symbol format
        search_result = smart_api.searchScrip("NFO", symbol)
        log_print(f"📋 Search result for {symbol}: {search_result}")

        if search_result and search_result.get("data"):
            token = search_result["data"][0]["symboltoken"]
            log_print(f"✅ Token found for {symbol}: {token}")
            return token
        else:
            log_print(f"❌ Could not find token for symbol: {symbol}")
            return None
    except Exception as e:
        log_print(f"❌ Error getting token for {symbol}: {e}")
        return None


# === Order Placement ===
def place_order(symbol, side, sl, target):
    try:
        quantity = 75  # 1 lot for NIFTY

        log_print("=" * 50)
        log_print("📝 NEW ORDER REQUEST RECEIVED")
        log_print(f"🎯 Symbol: {symbol}")
        log_print(f"📈 Side: {side}")
        log_print(f"🛑 Stop Loss: {sl}")
        log_print(f"🎯 Target: {target}")
        log_print(f"📊 Quantity: {quantity}")
        log_print("=" * 50)

        # Get symbol token first
        log_print("🔍 Step 1: Getting symbol token...")
        token = get_symbol_token(symbol)
        if not token:
            log_print("❌ FAILED: Could not get symbol token")
            return {"status": "error", "msg": "Could not get symbol token"}

        # Get current LTP for entry price
        log_print("💰 Step 2: Getting current LTP...")
        try:
            ltp_data = smart_api.ltpData("NFO", symbol, token)
            log_print(f"📊 LTP Data Response: {ltp_data}")
            entry_price = ltp_data["data"]["ltp"]
            log_print(f"✅ Current LTP (Entry Price): {entry_price}")
        except Exception as e:
            log_print(f"❌ Error getting LTP: {e}")
            return {"status": "error", "msg": f"Could not get LTP: {e}"}

        # Prepare order parameters
        log_print("📋 Step 3: Preparing order parameters...")
        order_params = {
            "variety": "NORMAL",
            "tradingsymbol": symbol,
            "symboltoken": token,
            "transactiontype": side.upper(),
            "exchange": "NFO",
            "ordertype": "MARKET",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "price": 0,
            "squareoff": 0,
            "stoploss": 0,
            "quantity": quantity,
        }
        log_print(f"📋 Order Parameters: {order_params}")

        # Place the order
        log_print("🚀 Step 4: Placing order with Angel One...")
        order_response = smart_api.placeOrder(order_params)
        log_print(f"✅ Order Response: {order_response}")

        # Set current trade details
        log_print("💾 Step 5: Updating trade tracking...")
        current_trade.update(
            {
                "symbol": symbol,
                "token": token,
                "entry_price": entry_price,
                "sl": sl,
                "target": target,
                "side": side.upper(),
                "active": True,
            }
        )
        log_print(f"📊 Trade Status Updated: {current_trade}")

        # Start monitoring in background
        log_print("👁️ Step 6: Starting trade monitoring thread...")
        monitoring_thread = threading.Thread(target=monitor_trade, daemon=True)
        monitoring_thread.start()
        log_print("✅ Monitoring thread started successfully")

        # Send Telegram notification
        log_print("📱 Step 7: Sending Telegram notification...")
        msg = (
            f"📊 Trade Opened: {symbol}\n"
            f"💰 Entry: {entry_price}\n"
            f"🎯 Target: {target}\n"
            f"🛑 SL: {sl}\n"
            f"📈 Side: {side.upper()}"
        )
        send_telegram_message(msg)

        log_print("✅ ORDER PLACEMENT COMPLETED SUCCESSFULLY!")
        log_print("=" * 50)
        return order_response

    except Exception as e:
        log_print(f"❌ ORDER PLACEMENT FAILED: {e}")
        log_print("=" * 50)
        return {"status": "error", "msg": str(e)}


# === Monitor SL/Target ===
def monitor_trade():
    log_print("👁️ TRADE MONITORING STARTED")
    log_print("📊 Monitoring Details:")
    log_print(f"   Symbol: {current_trade['symbol']}")
    log_print(f"   Entry: {current_trade['entry_price']}")
    log_print(f"   SL: {current_trade['sl']}")
    log_print(f"   Target: {current_trade['target']}")
    log_print(f"   Side: {current_trade['side']}")

    monitor_count = 0
    while current_trade["active"]:
        try:
            monitor_count += 1
            log_print(f"🔍 Monitor Check #{monitor_count}")

            # Get current LTP
            ltp_data = smart_api.ltpData(
                "NFO", current_trade["symbol"], current_trade["token"]
            )
            ltp = ltp_data["data"]["ltp"]

            entry = current_trade["entry_price"]
            sl = current_trade["sl"]
            target = current_trade["target"]

            # Calculate current P&L
            if current_trade["side"] == "BUY":
                current_pnl = (ltp - entry) * 75
                sl_price = entry - sl
                target_price = entry + target
            else:
                current_pnl = (entry - ltp) * 75
                sl_price = entry + sl
                target_price = entry - target

            log_print(f"💰 Current LTP: {ltp}")
            log_print(f"📊 Current P&L: ₹{current_pnl:.2f}")
            log_print(f"🛑 SL Price: {sl_price}")
            log_print(f"🎯 Target Price: {target_price}")

            # Check exit conditions
            if current_trade["side"] == "BUY":
                if ltp >= target_price:
                    log_print("🎯 TARGET HIT! Exiting trade...")
                    exit_trade("TARGET HIT", ltp)
                    break
                elif ltp <= sl_price:
                    log_print("🛑 STOP LOSS HIT! Exiting trade...")
                    exit_trade("STOP LOSS HIT", ltp)
                    break

            elif current_trade["side"] == "SELL":
                if ltp <= target_price:
                    log_print("🎯 TARGET HIT! Exiting trade...")
                    exit_trade("TARGET HIT", ltp)
                    break
                elif ltp >= sl_price:
                    log_print("🛑 STOP LOSS HIT! Exiting trade...")
                    exit_trade("STOP LOSS HIT", ltp)
                    break

            log_print("✅ Monitor check complete. Sleeping for 5 seconds...")
            time.sleep(5)

        except Exception as e:
            log_print(f"❌ LTP Monitoring Error: {e}")
            log_print("⏰ Waiting 10 seconds before retry...")
            time.sleep(10)  # Wait longer on error

    log_print("👁️ TRADE MONITORING ENDED")


# === Send Telegram Message ===
def send_telegram_message(message):
    try:
        log_print(f"📱 Sending Telegram message: {message}")
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        }
        response = requests.post(url, json=payload)
        log_print(
            f"📱 Telegram response: {response.status_code} - {response.text}"
        )
    except Exception as e:
        log_print(f"❌ Telegram Error: {e}")


# === Exit Trade ===
def exit_trade(reason, exit_price=None):
    log_print("=" * 50)
    log_print("🚪 EXITING TRADE")
    log_print(f"📍 Reason: {reason}")
    log_print(f"💰 Exit Price: {exit_price}")

    current_trade["active"] = False

    # Calculate P&L
    entry = current_trade["entry_price"]
    exit_p = exit_price or entry

    if current_trade["side"] == "BUY":
        pnl = (exit_p - entry) * 75
    else:
        pnl = (entry - exit_p) * 75

    log_print(f"💵 Final P&L: ₹{pnl:.2f}")

    # Send Telegram notification
    msg = (
        f"🚪 Trade Closed: {current_trade['symbol']}\n"
        f"📍 Reason: {reason}\n"
        f"💰 Entry: {entry}\n"
        f"🎯 Exit: {exit_p}\n"
        f"💵 P&L: ₹{pnl:.2f}"
    )
    send_telegram_message(msg)

    # Place reverse order to exit
    exit_side = "SELL" if current_trade["side"] == "BUY" else "BUY"
    log_print(f"🔄 Placing exit order - Side: {exit_side}")

    try:
        exit_order_params = {
            "variety": "NORMAL",
            "tradingsymbol": current_trade["symbol"],
            "symboltoken": current_trade["token"],
            "transactiontype": exit_side,
            "exchange": "NFO",
            "ordertype": "MARKET",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "price": 0,
            "squareoff": 0,
            "stoploss": 0,
            "quantity": 75,
        }

        log_print(f"📋 Exit Order Parameters: {exit_order_params}")
        exit_response = smart_api.placeOrder(exit_order_params)
        log_print(f"✅ Exit order placed successfully: {exit_response}")

    except Exception as e:
        log_print(f"❌ Exit order failed: {e}")
        send_telegram_message(f"❌ Exit order failed: {e}")

    log_print("🚪 TRADE EXIT PROCESS COMPLETED")
    log_print("=" * 50)


# === Webhook Receiver ===
@app.route("/webhook", methods=["POST"])
def webhook():
    log_print("🌐 WEBHOOK REQUEST RECEIVED")
    log_print(f"📡 Request Headers: {dict(request.headers)}")
    log_print(f"📡 Request Method: {request.method}")
    log_print(f"📡 Request URL: {request.url}")

    try:
        # Get raw data first
        raw_data = request.get_data()
        log_print(f"📄 Raw Data: {raw_data}")

        # Parse JSON
        data = request.json
        log_print(f"✅ Parsed JSON Data: {data}")

        # Validate required fields
        required_fields = ["symbol", "side", "sl", "target"]
        log_print(f"🔍 Validating required fields: {required_fields}")

        missing_fields = []
        for field in required_fields:
            if field not in data:
                missing_fields.append(field)

        if missing_fields:
            error_msg = f"Missing fields: {missing_fields}"
            log_print(f"❌ Validation failed: {error_msg}")
            return {"status": "error", "msg": error_msg}

        # Extract data
        symbol = data["symbol"]
        side = data["side"]
        sl = float(data["sl"])
        target = float(data["target"])

        log_print("📊 Extracted Data:")
        log_print(f"   Symbol: {symbol}")
        log_print(f"   Side: {side}")
        log_print(f"   SL: {sl}")
        log_print(f"   Target: {target}")

        # Check if there's already an active trade
        if current_trade["active"]:
            error_msg = (
                f"Another trade is already active for {current_trade['symbol']}"
            )
            log_print(f"❌ Trade conflict: {error_msg}")
            return {"status": "error", "msg": error_msg}

        # Place the order
        log_print("🚀 Proceeding to place order...")
        response = place_order(symbol, side, sl, target)
        log_print(f"📤 Order placement result: {response}")

        log_print("✅ WEBHOOK PROCESSING COMPLETED SUCCESSFULLY")
        return {"status": "ok", "response": response}

    except Exception as e:
        log_print(f"❌ WEBHOOK ERROR: {e}")
        log_print(f"📄 Request data: {request.get_data()}")
        return {"status": "error", "msg": str(e)}


# === Health Check ===
@app.route("/health", methods=["GET"])
def health():
    log_print("🏥 Health check requested")
    health_data = {
        "status": "healthy",
        "active_trade": current_trade["active"],
        "current_symbol": current_trade.get("symbol", "None"),
        "timestamp": datetime.now().isoformat(),
    }
    log_print(f"🏥 Health status: {health_data}")
    return health_data


# === Test Webhook Route ===
@app.route("/test", methods=["GET", "POST"])
def test_webhook():
    log_print("🧪 Test webhook accessed")
    if request.method == "POST":
        test_data = {
            "symbol": "NIFTY24JUL24000CE",
            "side": "BUY",
            "sl": 20,
            "target": 50,
        }
        log_print(f"🧪 Test data being processed: {test_data}")
        response = place_order(
            test_data["symbol"],
            test_data["side"],
            test_data["sl"],
            test_data["target"],
        )
        return {"status": "ok", "response": response}
    else:
        return {"message": "Send POST request with webhook data to test"}


# === Run Server ===
if __name__ == "__main__":
    log_print("🚀 STARTING NIFTY BREAKOUT BOT SERVER")
    log_print("🌐 Server will run on host: 0.0.0.0, port: 5000")
    log_print("📡 Webhook endpoint: /webhook")
    log_print("🏥 Health check endpoint: /health")
    log_print("🧪 Test endpoint: /test")
    log_print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=True)
