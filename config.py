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

REQUIRED_KEYS = [
    "dhanClientId",
    "dhanClientName",
    "accessToken",
    "expiryTime",
]

# ✅ Create Mongo client once (avoid reconnect each call)
mongo_client = None
mongo_collection = None

if MONGO_URI and MongoClient:
    try:
        mongo_client = MongoClient(MONGO_URI)
        db = mongo_client["trading"]
        mongo_collection = db["auth"]
        print("✅ MongoDB connected")
    except Exception as e:
        print(f"❌ MongoDB init error: {e}")


# -------------------------------------------------
# LOAD KEYS (FILE → MONGO FALLBACK)
# -------------------------------------------------
def load_keys():

    # ✅ 1. Try local file first
    if os.path.exists(KEYS_FILE):
        try:
            with open(KEYS_FILE, "r") as f:
                data = json.load(f)
                return data
        except Exception:
            print("❌ Error reading keys_data.json")

    # ✅ 2. Try MongoDB (if configured)
    if mongo_collection is not None:
        try:
            data = mongo_collection.find_one({"_id": "dhan_token"})

            if data:
                data.pop("_id", None)  # remove Mongo internal id
                return data

        except Exception as e:
            print(f"❌ MongoDB load error: {e}")

    return None


# -------------------------------------------------
# SAVE KEYS (FILE + MONGO)
# -------------------------------------------------
def save_keys(data):

    # ✅ Save locally
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

    if not data:
        print("❌ keys_data.json / MongoDB missing or corrupted")
        return False

    # ✅ Check required keys
    for key in REQUIRED_KEYS:
        if key not in data or not data[key]:
            print(f"❌ Missing or empty key: {key}")
            return False

    # ✅ Fix timezone issue (Dhan gives ISO without Z sometimes)
    try:
        expiry_raw = data["expiryTime"]

        # Add Z if missing (force UTC)
        if not expiry_raw.endswith("Z"):
            expiry_raw = expiry_raw + "Z"
 
        expiry_time = datetime.fromisoformat(expiry_raw.replace("Z", "+00:00"))

    except Exception:
        print("❌ Invalid expiry format")
        return False

    # ✅ Compare with UTC
    if datetime.utcnow() >= expiry_time.replace(tzinfo=None):
        print("❌ Token expired")
        return False

    return True