import json
import os
from datetime import datetime

KEYS_FILE = "keys_data.json"

REQUIRED_KEYS = [
    "dhanClientId",
    "dhanClientName",
    "accessToken",
    "expiryTime",
]


def load_keys():
    if not os.path.exists(KEYS_FILE):
        return None

    try:
        with open(KEYS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return None


def is_token_valid():
    data = load_keys()

    if not data:
        print("❌ keys_data.json missing or corrupted")
        return False

    # Check required keys
    for key in REQUIRED_KEYS:
        if key not in data or not data[key]:
            print(f"❌ Missing or empty key: {key}")
            return False

    # Check expiry
    try:
        expiry_time = datetime.fromisoformat(data["expiryTime"])
    except Exception:
        print("❌ Invalid expiry format")
        return False

    if datetime.utcnow() >= expiry_time:
        print("❌ Token expired")
        return False

    return True