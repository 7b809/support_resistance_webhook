import requests
from config import BOT_TOKEN, ALLOWED_CHAT_ID

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


def send_telegram_alert(message: str):
    try:
        requests.post(
            f"{BASE_URL}/sendMessage",
            json={
                "chat_id": ALLOWED_CHAT_ID,
                "text": f"🚨 *ERROR ALERT*\n\n{message}",
                "parse_mode": "Markdown"
            },
            timeout=5
        )
    except Exception as e:
        print(f"❌ Failed to send Telegram alert: {e}")