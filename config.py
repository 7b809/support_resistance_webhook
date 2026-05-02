import json
import os
from datetime import datetime
from dotenv import load_dotenv

# ✅ Mongo import (safe)
try:
    from pymongo import MongoClient
except:
    MongoClient = None

load_dotenv()

# -------------------------------------------------
# ENV CONFIG
# -------------------------------------------------
KEYS_FILE = "keys_data.json"
MONGO_URI = os.getenv("MONGO_URI")

BOT_TOKEN = os.getenv("BOT_TOKEN", None)
ALLOWED_CHAT_ID = os.getenv("CHAT_ID", None)

PRINT_LOGS = os.getenv("PRINT_LOGS", "false").strip().lower() in ("true", "1", "yes")
TELE_BOT_LOGS = os.getenv("TELE_BOT_LOGS", "true").strip().lower() in ("true", "1", "yes")

MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "trading")
MONGO_COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME", "auth")

INSTRUMENT_COLLECTION_NAME = os.getenv(
    "MONGO_INSTRUMENT_COLLECTION",
    "instrument_subscriptions"
)

REQUIRED_KEYS = [
    "dhanClientId",
    "dhanClientName",
    "accessToken",
    "expiryTime",
]


# -------------------------------------------------
# LOG HELPER
# -------------------------------------------------
def log(msg, level="INFO"):
    if PRINT_LOGS:
        print(f"[CONFIG {level}] {msg}")


# -------------------------------------------------
# MONGO INIT
# -------------------------------------------------
mongo_client = None
mongo_collection = None
mongo_instrument_collection = None

if MONGO_URI and MongoClient:
    try:
        mongo_client = MongoClient(MONGO_URI)

        db = mongo_client[MONGO_DB_NAME]

        # ✅ Token collection
        mongo_collection = db[MONGO_COLLECTION_NAME]

        # ✅ Instrument collection
        mongo_instrument_collection = db[INSTRUMENT_COLLECTION_NAME]

        log(f"MongoDB connected → DB:{MONGO_DB_NAME}", "INFO")
        log(f"Token Collection → {MONGO_COLLECTION_NAME}", "INFO")
        log(f"Instrument Collection → {INSTRUMENT_COLLECTION_NAME}", "INFO")

        # ✅ Ensure unique index (VERY IMPORTANT)
        try:
            mongo_instrument_collection.create_index(
                [("security_id", 1), ("exchange", 1), ("type", 1)],
                unique=True
            )
            log("Instrument index ensured", "INFO")
        except Exception as idx_err:
            log(f"Index creation warning: {idx_err}", "WARN")

    except Exception as e:
        log(f"MongoDB init error: {e}", "ERROR")

else:
    log("MongoDB not configured (MONGO_URI missing)", "WARN")

# -------------------------------------------------
# 🔁 TOKEN ALERT COLLECTION
# -------------------------------------------------
token_alert_collection = None

if mongo_client:
    try:
        token_alert_collection = mongo_client[MONGO_DB_NAME]["token_alerts"]
        log("Token alert collection ready", "INFO")
    except Exception as e:
        log(f"Token alert collection error: {e}", "ERROR")

# -------------------------------------------------
# LOAD KEYS (Mongo → File fallback)
# -------------------------------------------------
def load_keys():
    if mongo_collection is not None:
        try:
            data = mongo_collection.find_one({"_id": "dhan_token"})
            if data:
                data.pop("_id", None)
                return data
        except Exception as e:
            log(f"Mongo load error: {e}", "ERROR")

    if os.path.exists(KEYS_FILE):
        try:
            with open(KEYS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            log("Error reading keys_data.json", "ERROR")

    return None


# -------------------------------------------------
# SAVE KEYS (FILE + MONGO)
# -------------------------------------------------
def save_keys(data):
    try:
        with open(KEYS_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        log(f"File save error: {e}", "ERROR")

    if mongo_collection is not None:
        try:
            mongo_collection.update_one(
                {"_id": "dhan_token"},
                {"$set": data},
                upsert=True
            )
            log("Token saved to MongoDB", "INFO")
        except Exception as e:
            log(f"Mongo save error: {e}", "ERROR")


# -------------------------------------------------
# TOKEN VALIDATION
# -------------------------------------------------
def is_token_valid():
    data = load_keys()

    if not data:
        log("Token missing or corrupted", "WARN")
        return False

    for key in REQUIRED_KEYS:
        if key not in data or not data[key]:
            log(f"Missing key: {key}", "ERROR")
            return False

    try:
        expiry_raw = data["expiryTime"]

        if not expiry_raw.endswith("Z"):
            expiry_raw += "Z"

        expiry_time = datetime.fromisoformat(
            expiry_raw.replace("Z", "+00:00")
        )

    except Exception:
        log("Invalid expiry format", "ERROR")
        return False

    if datetime.utcnow() >= expiry_time.replace(tzinfo=None):
        log("Token expired", "WARN")
        return False

    return True


# -------------------------------------------------
# SAVE INSTRUMENTS
# -------------------------------------------------
def save_instruments(symbols):
    if mongo_instrument_collection is None:
        log("Instrument collection not available", "WARN")
        return

    try:
        for ex, sid, typ in symbols:
            mongo_instrument_collection.update_one(
                {
                    "security_id": str(sid),
                    "exchange": ex,
                    "type": typ,
                },
                {
                    "$set": {
                        "security_id": str(sid),
                        "exchange": ex,
                        "type": typ,
                        "updated_at": datetime.utcnow(),
                    }
                },
                upsert=True
            )

        log(f"Saved instruments → {len(symbols)}", "INFO")

    except Exception as e:
        log(f"Save instruments error: {e}", "ERROR")


# -------------------------------------------------
# REMOVE INSTRUMENTS
# -------------------------------------------------
def remove_instruments_db(symbols):
    if mongo_instrument_collection is None:
        log("Instrument collection not available", "WARN")
        return

    try:
        for ex, sid, typ in symbols:
            mongo_instrument_collection.delete_one(
                {
                    "security_id": str(sid),
                    "exchange": ex,
                    "type": typ,
                }
            )

        log(f"Removed instruments → {len(symbols)}", "INFO")

    except Exception as e:
        log(f"Remove instruments DB error: {e}", "ERROR")


# -------------------------------------------------
# LOAD INSTRUMENTS
# -------------------------------------------------
def load_instruments():
    if mongo_instrument_collection is None:
        log("Instrument collection not available", "WARN")
        return []

    try:
        data = mongo_instrument_collection.find()

        result = [
            (doc["exchange"], doc["security_id"], doc["type"])
            for doc in data
        ]

        log(f"Loaded instruments → {len(result)}", "INFO")
        return result

    except Exception as e:
        log(f"Load instruments error: {e}", "ERROR")
        return []
    

# -------------------------------------------------
# SAVE TOKEN ALERT STATE
# -------------------------------------------------
def save_token_alert(data):
    if not token_alert_collection:
        return

    try:
        token_alert_collection.update_one(
            {"_id": "token_alert"},
            {"$set": data},
            upsert=True
        )
    except Exception as e:
        log(f"Save token alert error: {e}", "ERROR")


# -------------------------------------------------
# LOAD TOKEN ALERT STATE
# -------------------------------------------------
def load_token_alert():
    if not token_alert_collection:
        return {}

    try:
        data = token_alert_collection.find_one({"_id": "token_alert"})
        return data if data else {}
    except Exception as e:
        log(f"Load token alert error: {e}", "ERROR")
        return {}    