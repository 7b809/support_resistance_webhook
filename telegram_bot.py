# telegram_bot.py

import requests
import threading
from authentication import generate_access_token
from config import is_token_valid,BOT_TOKEN,ALLOWED_CHAT_ID
from feed_manager import start_feed_thread


BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

FEED_STARTED = False


def send_message(text):
    requests.post(
        f"{BASE_URL}/sendMessage",
        json={"chat_id": ALLOWED_CHAT_ID, "text": text}
    )


def get_updates(offset=None):
    url = f"{BASE_URL}/getUpdates"
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    return requests.get(url, params=params).json()


def safe_start_feed():
    global FEED_STARTED
    if not FEED_STARTED:
        start_feed_thread()
        FEED_STARTED = True
        send_message("📡 Feed started")


def telegram_listener():
    print("🤖 Telegram bot started...")
    offset = None

    while True:
        data = get_updates(offset)

        for update in data.get("result", []):
            offset = update["update_id"] + 1

            try:
                chat_id = str(update["message"]["chat"]["id"])
                message = update["message"]["text"].strip()
            except:
                continue

            # 🔒 Security check
            if chat_id != ALLOWED_CHAT_ID:
                continue

            # Commands
            if message == "/start":
                send_message("Send 6-digit TOTP to login")
                continue

            if message == "/status":
                if is_token_valid():
                    send_message("✅ Token is valid")
                else:
                    send_message("❌ Token not valid")
                continue

            # TOTP input
            if message.isdigit() and len(message) == 6:
                send_message("⏳ Generating token...")

                result = generate_access_token(message)

                if result["status"] == "success":
                    send_message("✅ Token generated")

                    if is_token_valid():
                        safe_start_feed()
                    else:
                        send_message("⚠️ Token invalid after generation")

                else:
                    send_message(f"❌ {result['message']}")

            else:
                send_message("⚠️ Send valid 6-digit TOTP")


def start_telegram_bot():
    thread = threading.Thread(target=telegram_listener, daemon=True)
    thread.start()