import requests
from config import Config

def send_telegram_message(message: str):
    url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": Config.TELEGRAM_CHAT_ID,
        "text": message
    }

    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print("Telegram Error:", e)
