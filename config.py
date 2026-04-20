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

KEYS_FILE = "keys_data.json"
MONGO_URI = os.getenv("MONGO_URI")

BOT_TOKEN = os.getenv("BOT_TOKEN", None)
ALLOWED_CHAT_ID = os.getenv("CHAT_ID", None)

# ✅ ENV आधारित DB + COLLECTION
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "trading")
MONGO_COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME", "auth")

REQUIRED_KEYS = [
    "dhanClientId",
    "dhanClientName",
    "accessToken",
    "expiryTime",
]

# -------------------------------------------------
# ✅ SINGLE Mongo INIT (FIXED)
# -------------------------------------------------
mongo_client = None
mongo_collection = None

if MONGO_URI and MongoClient:
    try:
        mongo_client = MongoClient(MONGO_URI)

        db = mongo_client[MONGO_DB_NAME]
        mongo_collection = db[MONGO_COLLECTION_NAME]

        print(f"✅ MongoDB connected → DB: {MONGO_DB_NAME}, Collection: {MONGO_COLLECTION_NAME}")

    except Exception as e:
        print(f"❌ MongoDB init error: {e}")


# -------------------------------------------------
# LOAD KEYS (Mongo → File fallback)  ✅ FIXED ORDER
# -------------------------------------------------
def load_keys():

    # ✅ 1. Try MongoDB FIRST (important for Railway)
    if mongo_collection is not None:
        try:
            data = mongo_collection.find_one({"_id": "dhan_token"})

            if data:
                data.pop("_id", None)
                return data

        except Exception as e:
            print(f"❌ MongoDB load error: {e}")

    # ✅ 2. Fallback to local file
    if os.path.exists(KEYS_FILE):
        try:
            with open(KEYS_FILE, "r") as f:
                data = json.load(f)
                return data
        except Exception:
            print("❌ Error reading keys_data.json")

    return None


# -------------------------------------------------
# SAVE KEYS (FILE + MONGO)
# -------------------------------------------------
def save_keys(data):

    # ✅ Save locally (optional for local dev)
    try:
        with open(KEYS_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"❌ Failed to save file: {e}")

    # ✅ Save to MongoDB
    if mongo_collection is not None:
        try:
            mongo_collection.update_one(
                {"_id": "dhan_token"},
                {"$set": data},
                upsert=True
            )
            print("✅ Token saved to MongoDB")
        except Exception as e:
            print(f"❌ MongoDB save error: {e}")


# -------------------------------------------------
# TOKEN VALIDATION
# -------------------------------------------------
def is_token_valid():
    data = load_keys()

    # 🔍 DEBUG (keep this for now)
    print("🔍 Loaded token data:", data)

    if not data:
        print("❌ keys_data.json / MongoDB missing or corrupted")
        return False

    # ✅ Check required keys
    for key in REQUIRED_KEYS:
        if key not in data or not data[key]:
            print(f"❌ Missing or empty key: {key}")
            return False

    # ✅ Fix timezone issue
    try:
        expiry_raw = data["expiryTime"]

        if not expiry_raw.endswith("Z"):
            expiry_raw = expiry_raw + "Z"

        expiry_time = datetime.fromisoformat(
            expiry_raw.replace("Z", "+00:00")
        )

    except Exception:
        print("❌ Invalid expiry format")
        return False

    # ✅ Compare with UTC
    if datetime.utcnow() >= expiry_time.replace(tzinfo=None):
        print("❌ Token expired")
        return False

    return True