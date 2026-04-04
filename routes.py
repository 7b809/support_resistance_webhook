from flask import Blueprint, request, jsonify
from db import get_collection
from parser import parse_alert
from telegram import send_telegram_message

routes = Blueprint("routes", __name__)

WEBHOOK_CONFIG = [
    {"num": 1, "symbol": "nifty"},
    {"num": 2, "symbol": "gift_nifty"},
    {"num": 3, "symbol": "bank_nifty"},
]

def get_config(num):
    return next((x for x in WEBHOOK_CONFIG if x["num"] == num), None)

@routes.route("/webhook/<int:num>", methods=["POST"])
def webhook(num):
    config = get_config(num)

    if not config:
        return jsonify({"error": "Invalid webhook"}), 404

    raw_data = request.get_data(as_text=True)

    parsed = parse_alert(raw_data)

    parsed["webhook"] = f"/webhook/{num}"
    parsed["symbol"] = config["symbol"]

    collection = get_collection(config["symbol"])
    inserted = collection.insert_one(parsed)

    msg = f"{config['symbol'].upper()} → {parsed['message']}"
    send_telegram_message(msg)

    return jsonify({
        "status": "ok",
        "id": str(inserted.inserted_id)
    })
