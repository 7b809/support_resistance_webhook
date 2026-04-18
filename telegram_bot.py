# telegram_bot.py

import requests
import threading
import time
import re
from datetime import datetime

from authentication import generate_access_token
from config import is_token_valid, BOT_TOKEN, ALLOWED_CHAT_ID, load_keys
from feed_manager import start_feed_thread


BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

FEED_STARTED = False
LAST_ATTEMPT = {}  # rate limiting


# -------------------------------------------------
# SEND MESSAGE (SAFE)
# -------------------------------------------------
def send_message(text):
    try:
        requests.post(
            f"{BASE_URL}/sendMessage",
            json={"chat_id": ALLOWED_CHAT_ID, "text": text},
            timeout=10
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
# VALIDATE TOTP (STRICT)
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
            return False

    LAST_ATTEMPT[chat_id] = now
    return True


# -------------------------------------------------
# GET EXPIRY INFO
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

        expiry_time = datetime.fromisoformat(
            expiry_raw.replace("Z", "+00:00")
        )

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
                except Exception:
                    continue

                # 🔒 Security check
                if chat_id != ALLOWED_CHAT_ID:
                    continue

                # ⛔ Rate limit
                if not can_attempt(chat_id):
                    send_message("⏳ Please wait a few seconds before retrying")
                    continue

                # -------------------------
                # COMMANDS
                # -------------------------
                if message == "/start":
                    send_message(
                        "👋 Welcome!\n\n"
                        "👉 Send 6-digit TOTP to login\n"
                        "👉 /status → Check token\n"
                        "👉 /expiry → Check expiry"
                    )
                    continue

                if message == "/status":
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
                    try:
                        expiry_time, remaining = get_expiry_info()

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
                            f"🕒 Expiry (UTC): {expiry_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                            f"⏳ Remaining: {hrs}h {mins}m"
                        )

                    except Exception as e:
                        print(f"❌ Expiry error: {e}")
                        send_message("❌ Failed to fetch expiry info")

                    continue

                # -------------------------
                # TOTP INPUT
                # -------------------------
                if is_valid_totp(message):

                    send_message("⏳ Generating token...")

                    try:
                        result = generate_access_token(message)
                    except Exception as e:
                        print(f"❌ Token generation crash: {e}")
                        send_message("❌ Internal error during token generation")
                        continue

                    if result.get("status") == "success":
                        send_message("✅ Token generated successfully")

                        try:
                            if is_token_valid():
                                safe_start_feed()
                            else:
                                send_message("⚠️ Token invalid after generation")
                        except Exception as e:
                            print(f"❌ Validation error: {e}")
                            send_message("❌ Error validating token")

                    else:
                        send_message(
                            f"❌ Token generation failed\n👉 {result.get('message', 'Unknown error')}"
                        )

                else:
                    send_message(
                        "❌ Invalid TOTP\n\n"
                        "👉 Must be exactly 6 digits (0-9)\n"
                        "👉 No spaces, letters, or symbols"
                    )

        except Exception as e:
            print(f"❌ Listener loop error: {e}")
            time.sleep(5)


# -------------------------------------------------
# START BOT THREAD
# -------------------------------------------------
def start_telegram_bot():
    try:
        thread = threading.Thread(target=telegram_listener, daemon=True)
        thread.start()
    except Exception as e:
        print(f"❌ Failed to start Telegram bot: {e}")