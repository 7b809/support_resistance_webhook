import requests
import threading
import time
import re
import os
from datetime import datetime

from authentication import generate_access_token
from config import is_token_valid, BOT_TOKEN, ALLOWED_CHAT_ID, load_keys
from feed_manager import start_feed_thread
from config import save_token_alert, load_token_alert
from datetime import timedelta


# -------------------------------------------------
# 🔁 TOKEN ALERT STATE
# -------------------------------------------------
TOKEN_ALERT_SENT = False
LAST_ALERT_TIME = 0
ALERT_INTERVAL = 3600  # 1 hour


# -------------------------------------------------
# ✅ LOG CONTROL (NEW)
# -------------------------------------------------
TELE_BOT_LOGS = os.getenv("TELE_BOT_LOGS", "false").strip().lower() in (
    "true",
    "1",
    "yes",
)


def log(msg):
    if TELE_BOT_LOGS:
        print(f"[TELEGRAM {datetime.now().strftime('%H:%M:%S')}] {msg}")


BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

FEED_STARTED = False
LAST_ATTEMPT = {}  # rate limiting


# -------------------------------------------------
# 💰 GET FUND LIMIT (BALANCE)  ✅ ADDED
# -------------------------------------------------
def get_fund_limit():
    try:
        data = load_keys()
        if not data:
            return None

        access_token = data.get("accessToken")
        if not access_token:
            return None

        headers = {
            "Content-Type": "application/json",
            "access-token": access_token,
        }

        response = requests.get(
            "https://api.dhan.co/v2/fundlimit",
            headers=headers,
            timeout=10,
        )

        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Fund API error: {response.text}")
            return None

    except Exception as e:
        print(f"❌ Fund fetch error: {e}")
        return None


# -------------------------------------------------
# SEND MESSAGE (SAFE)
# -------------------------------------------------
def send_message(text):
    try:
        log(f"📤 Sending: {text}")
        requests.post(
            f"{BASE_URL}/sendMessage",
            json={"chat_id": ALLOWED_CHAT_ID, "text": text},
            timeout=10,
        )
    except Exception as e:
        print(f"❌ Telegram send error: {e}")


# -------------------------------------------------
# GET UPDATES (SAFE)
# -------------------------------------------------
def get_updates(offset=None):
    try:
        url = f"{BASE_URL}/getUpdates"
        params = {"timeout": 30}

        if offset:
            params["offset"] = offset

        response = requests.get(url, params=params, timeout=35)
        return response.json()

    except Exception as e:
        print(f"❌ Telegram fetch error: {e}")
        return {"result": []}


# -------------------------------------------------
# VALIDATE TOTP
# -------------------------------------------------
def is_valid_totp(text: str) -> bool:
    if not text:
        return False

    text = text.strip()
    return bool(re.fullmatch(r"[0-9]{6}", text))


# -------------------------------------------------
# RATE LIMITING
# -------------------------------------------------
def can_attempt(chat_id):
    now = time.time()

    if chat_id in LAST_ATTEMPT:
        if now - LAST_ATTEMPT[chat_id] < 5:
            log(f"⛔ Rate limited: {chat_id}")
            return False

    LAST_ATTEMPT[chat_id] = now
    return True


# -------------------------------------------------
# EXPIRY INFO
# -------------------------------------------------
def get_expiry_info():
    try:
        data = load_keys()
        if not data:
            return None, None

        expiry_raw = data.get("expiryTime")
        if not expiry_raw:
            return None, None

        if not expiry_raw.endswith("Z"):
            expiry_raw += "Z"

        expiry_time = datetime.fromisoformat(expiry_raw.replace("Z", "+00:00"))

        now = datetime.utcnow()
        remaining = expiry_time.replace(tzinfo=None) - now

        return expiry_time, remaining

    except Exception as e:
        print(f"❌ Expiry parse error: {e}")
        return None, None


# -------------------------------------------------
# SAFE FEED START
# -------------------------------------------------
def safe_start_feed():
    global FEED_STARTED

    try:
        if not FEED_STARTED:
            log("🚀 Starting feed thread...")
            start_feed_thread()
            FEED_STARTED = True
            send_message("📡 Feed started successfully")
    except Exception as e:
        print(f"❌ Feed start error: {e}")
        send_message("❌ Failed to start feed")


# -------------------------------------------------
# TELEGRAM LISTENER
# -------------------------------------------------
def telegram_listener():
    print("🤖 Telegram bot started...")
    offset = None

    while True:
        try:
            data = get_updates(offset)

            for update in data.get("result", []):
                offset = update["update_id"] + 1

                try:
                    message_data = update.get("message", {})
                    chat_id = str(message_data.get("chat", {}).get("id"))
                    message = message_data.get("text", "").strip()

                    log(f"📩 Received → chat_id={chat_id}, msg='{message}'")

                except Exception:
                    continue

                # 🔒 Security check
                if chat_id != ALLOWED_CHAT_ID:
                    log(f"🚫 Unauthorized chat: {chat_id}")
                    continue

                # ⛔ Rate limit
                SAFE_COMMANDS = ["/start", "/status", "/expiry", "/balance"]

                if message not in SAFE_COMMANDS:
                    if not can_attempt(chat_id):
                        send_message("⏳ Please wait a few seconds before retrying")
                        continue

                # -------------------------
                # COMMANDS
                # -------------------------
                if message == "/start":
                    log("⚙️ Command: /start")
                    send_message(
                        "👋 Welcome!\n\n"
                        "👉 Send 6-digit TOTP to login\n"
                        "👉 /status → Check token\n"
                        "👉 /expiry → Check expiry\n"
                        "👉 /balance → Check funds"
                    )
                    continue

                if message == "/status":
                    log("⚙️ Command: /status")
                    try:
                        if is_token_valid():
                            expiry_time, remaining = get_expiry_info()

                            msg = "✅ Token is valid"

                            if remaining:
                                mins = int(remaining.total_seconds() // 60)
                                msg += f"\n⏳ Expires in {mins} mins"

                            send_message(msg)
                        else:
                            send_message("❌ Token not valid or expired")

                    except Exception as e:
                        print(f"❌ Status error: {e}")
                        send_message("❌ Error checking token status")

                    continue

                if message == "/expiry":
                    log("⚙️ Command: /expiry")
                    try:
                        expiry_time, remaining = get_expiry_info()
                        expiry_ist = expiry_time + timedelta(hours=5, minutes=30)

                        if not expiry_time:
                            send_message("❌ No token data available")
                            continue

                        if remaining.total_seconds() <= 0:
                            send_message("❌ Token already expired")
                            continue

                        total_sec = int(remaining.total_seconds())
                        hrs = total_sec // 3600
                        mins = (total_sec % 3600) // 60

                        send_message(
                            f"🕒 Expiry (IST): {expiry_ist.strftime('%Y-%m-%d %H:%M:%S')}\n"
                            f"⏳ Remaining: {hrs}h {mins}m"
                        )

                    except Exception as e:
                        print(f"❌ Expiry error: {e}")
                        send_message("❌ Failed to fetch expiry info")

                    continue

                # -------------------------
                # 💰 BALANCE COMMAND (NEW)
                # -------------------------
                if message == "/balance":
                    log("⚙️ Command: /balance")

                    try:
                        if not is_token_valid():
                            send_message("❌ Token not valid. Please login again.")
                            continue

                        fund = get_fund_limit()

                        if not fund:
                            send_message("❌ Failed to fetch balance")
                            continue

                        msg = (
                            "💰 Account Balance Info\n\n"
                            f"Available Balance: ₹{fund.get('availabelBalance')}\n"
                            f"Withdrawable: ₹{fund.get('withdrawableBalance')}\n"
                            f"Used: ₹{fund.get('utilizedAmount')}\n"
                            f"Collateral: ₹{fund.get('collateralAmount')}\n"
                        )

                        send_message(msg)

                    except Exception as e:
                        print(f"❌ Balance error: {e}")
                        send_message("❌ Error fetching balance")

                    continue

                # -------------------------
                # TOTP INPUT
                # -------------------------
                if is_valid_totp(message):

                    log(f"🔐 TOTP received: {message}")
                    send_message("⏳ Generating token...")

                    try:
                        result = generate_access_token(message)
                    except Exception as e:
                        print(f"❌ Token generation crash: {e}")
                        send_message("❌ Internal error during token generation")
                        continue

                    if result.get("status") == "success":

                        # ✅ RESET ALERT STATE AFTER LOGIN
                        save_token_alert({
                            "last_alert_time": None,
                            "alert_active": False,
                            "alert_count": 0,
                            "last_token_generated_time": datetime.utcnow().isoformat()
                        })


                        log("✅ Token generated successfully")
                        send_message("✅ Token generated successfully")

                        # 💰 AUTO BALANCE AFTER LOGIN (NEW)
                        try:
                            fund = get_fund_limit()
                            if fund:
                                send_message(
                                    "💰 Token Valid ✅\n\n"
                                    f"Available Balance: ₹{fund.get('availabelBalance')}\n"
                                    f"Withdrawable: ₹{fund.get('withdrawableBalance')}"
                                )
                            else:
                                send_message("⚠️ Balance fetch failed")
                        except Exception as e:
                            print(f"❌ Post-login balance error: {e}")

                        try:
                            if is_token_valid():
                                log("✅ Token validated → starting feed")
                                safe_start_feed()
                            else:
                                log("⚠️ Token invalid after generation")
                                send_message("⚠️ Token invalid after generation")
                        except Exception as e:
                            print(f"❌ Validation error: {e}")
                            send_message("❌ Error validating token")

                    else:
                        log("❌ Token generation failed")
                        send_message(
                            f"❌ Token generation failed\n👉 {result.get('message', 'Unknown error')}"
                        )

                else:
                    log("❌ Invalid TOTP format")
                    send_message(
                        "❌ Invalid TOTP\n\n"
                        "👉 Must be exactly 6 digits (0-9)\n"
                        "👉 No spaces, letters, or symbols"
                    )

        except Exception as e:
            print(f"❌ Listener loop error: {e}")
            time.sleep(5)

# -------------------------------------------------
# 🕒 AUTO BALANCE CHECK (EVERY 1 HOUR)
# -------------------------------------------------
def balance_monitor():
    print("⏱️ Balance monitor started (DB mode)")

    while True:
        try:
            now = datetime.utcnow()

            state = load_token_alert()

            last_alert_time = state.get("last_alert_time")
            alert_active = state.get("alert_active", False)

            # convert string → datetime
            if last_alert_time:
                last_alert_time = datetime.fromisoformat(last_alert_time)

            # -------------------------------------------------
            # ❌ TOKEN INVALID
            # -------------------------------------------------
            if not is_token_valid():

                should_alert = False

                if not alert_active:
                    should_alert = True
                elif last_alert_time:
                    diff = (now - last_alert_time).total_seconds()
                    if diff >= 3600:
                        should_alert = True

                if should_alert:
                    send_message(
                        "⚠️ Token expired.\n"
                        "👉 Please login using TOTP."
                    )

                    save_token_alert({
                        "last_alert_time": now.isoformat(),
                        "alert_active": True,
                        "alert_count": state.get("alert_count", 0) + 1
                    })

                time.sleep(60)
                continue

            # -------------------------------------------------
            # ✅ TOKEN FIXED
            # -------------------------------------------------
            if alert_active:
                send_message("✅ Token restored. System resumed.")

                save_token_alert({
                    "last_alert_time": None,
                    "alert_active": False,
                    "alert_count": 0,
                    "last_token_generated_time": now.isoformat()
                })

            # -------------------------------------------------
            # 💰 BALANCE CHECK
            # -------------------------------------------------
            fund = get_fund_limit()

            if not fund:
                time.sleep(10)
                fund = get_fund_limit()

            if not fund:
                send_message("🚨 API issue. Please check login.")

        except Exception as e:
            print(f"❌ Monitor error: {e}")

        time.sleep(3600)

# -------------------------------------------------
# START BOT THREAD
# -------------------------------------------------
def start_telegram_bot():
    try:
        # ✅ Telegram listener
        thread = threading.Thread(target=telegram_listener, daemon=True)
        thread.start()

        # ✅ NEW: balance monitor thread
        monitor_thread = threading.Thread(target=balance_monitor, daemon=True)
        monitor_thread.start()

        print("✅ Telegram bot + Balance monitor started")

    except Exception as e:
        print(f"❌ Failed to start Telegram bot: {e}")