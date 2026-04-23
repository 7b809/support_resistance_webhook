import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from config import MONGO_DB_NAME, MONGO_COLLECTION_NAME

# ✅ Mongo (safe import)
try:
    from pymongo import MongoClient
except:
    MongoClient = None

# Load environment variables
load_dotenv()

KEYS_FILE = "keys_data.json"
MONGO_URI = os.getenv("MONGO_URI")

REQUIRED_KEYS = [
    "dhanClientId",
    "dhanClientName",
    "accessToken",
    "expiryTime",
]

# -------------------------------------------------
# INIT MONGO (REUSE CONNECTION)
# -------------------------------------------------
mongo_client = None
mongo_collection = None

if MONGO_URI and MongoClient:
    try:
        mongo_client = MongoClient(MONGO_URI)
        db = mongo_client[MONGO_DB_NAME]
        mongo_collection = db[MONGO_COLLECTION_NAME]
        print(f"✅ MongoDB connected → {MONGO_DB_NAME}.{MONGO_COLLECTION_NAME}")
    except Exception as e:
        print(f"❌ Mongo init error: {e}")


# -------------------------------------------------
# LOAD KEYS (Mongo → File fallback)
# -------------------------------------------------
def load_keys():
    # 1️⃣ Mongo FIRST
    if mongo_collection is not None:
        try:
            data = mongo_collection.find_one({"_id": "dhan_token"})
            if data:
                data.pop("_id", None)
                return data
        except Exception as e:
            print(f"❌ Mongo load error: {e}")

    # 2️⃣ File fallback
    if os.path.exists(KEYS_FILE):
        try:
            with open(KEYS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            print("❌ Error reading keys_data.json")

    return None


# -------------------------------------------------
# SAVE KEYS (FILE + MONGO)
# -------------------------------------------------
def save_keys(data: dict):
    try:
        with open(KEYS_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"❌ File save error: {e}")

    if mongo_collection is not None:
        try:
            mongo_collection.update_one(
                {"_id": "dhan_token"},
                {"$set": data},
                upsert=True
            )
            print("✅ Token saved to MongoDB")
        except Exception as e:
            print(f"❌ Mongo save error: {e}")


# -------------------------------------------------
# VALIDATE STRUCTURE ONLY (NO DELETE)
# -------------------------------------------------
def validate_token_data(data: dict):
    missing = [k for k in REQUIRED_KEYS if not data.get(k)]
    if missing:
        print(f"❌ Missing keys: {missing}")
        return False
    return True


# -------------------------------------------------
# CHECK EXPIRY
# -------------------------------------------------
def is_token_valid():
    data = load_keys()

    if not data:
        print("❌ No token data found")
        return False

    if not validate_token_data(data):
        return False

    try:
        expiry_raw = data["expiryTime"]

        if not expiry_raw.endswith("Z"):
            expiry_raw += "Z"

        expiry_time = datetime.fromisoformat(
            expiry_raw.replace("Z", "+00:00")
        )

    except Exception:
        print("❌ Invalid expiry format")
        return False

    if datetime.utcnow() >= expiry_time.replace(tzinfo=None):
        print("❌ Token expired")
        return False

    return True


# -------------------------------------------------
# GENERATE ACCESS TOKEN (SAFE VERSION)
# -------------------------------------------------
def generate_access_token(totp: str):
    try:
        dhan_client_id = os.getenv("DHAN_CLIENT_ID")
        dhan_pin = os.getenv("DHAN_PIN")

        if not dhan_client_id or not dhan_pin:
            return {
                "status": "error",
                "message": "Missing DHAN_CLIENT_ID or DHAN_PIN"
            }

        if not totp or len(totp) != 6:
            return {
                "status": "error",
                "message": "Invalid TOTP"
            }

        url = "https://auth.dhan.co/app/generateAccessToken"

        params = {
            "dhanClientId": dhan_client_id,
            "pin": dhan_pin,
            "totp": totp
        }

        print("⏳ Generating access token...")

        response = requests.post(url, params=params)

        if response.status_code != 200:
            print("⚠️ API error - keeping old token")
            return {
                "status": "error",
                "message": f"API Error {response.status_code}",
                "details": response.text
            }

        try:
            data = response.json()
        except Exception:
            print("⚠️ Invalid JSON response")
            return {"status": "error", "message": "Invalid JSON"}

        if not validate_token_data(data):
            print("⚠️ Invalid token data received")
            return {"status": "error", "message": "Invalid token data"}

        clean_data = {
            "dhanClientId": data.get("dhanClientId"),
            "dhanClientName": data.get("dhanClientName"),
            "dhanClientUcc": data.get("dhanClientUcc"),
            "givenPowerOfAtt": data.get("givenPowerOfAtt"),
            "accessToken": data.get("accessToken"),
            "expiryTime": data.get("expiryTime"),
        }

        save_keys(clean_data)

        print("✅ Access token generated and saved")

        return {"status": "success", "data": clean_data}

    except Exception as e:
        print(f"❌ Token generation error: {e}")
        return {"status": "error", "message": str(e)}


# -------------------------------------------------
# ✅ HELPER FUNCTION (YOUR REQUEST)
# -------------------------------------------------
def ensure_token(totp=None):

    data = load_keys()

    # 1️⃣ No data
    if not data:
        print("⚠️ No token → generating new")
        return generate_access_token(totp)

    # 2️⃣ Invalid structure
    if not validate_token_data(data):
        print("⚠️ Invalid token → regenerating")
        return generate_access_token(totp)

    # 3️⃣ Expired
    if not is_token_valid():
        print("⚠️ Expired token → regenerating")
        return generate_access_token(totp)

    # 4️⃣ Valid
    print("✅ Using existing token")
    return {"status": "success", "data": data}
