import os
import json
import requests
from dotenv import load_dotenv

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
# SAVE TOKEN (CLEAN + SAFE + MONGO)
# -------------------------------------------------
def save_keys(data: dict):
    # ✅ EXISTING LOGIC (UNCHANGED)
    try:
        with open(KEYS_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"❌ Failed to save keys: {e}")

    # ✅ NEW: Save to MongoDB (no logic change)
    if MONGO_URI and MongoClient:
        try:
            client = MongoClient(MONGO_URI)
            db = client["trading"]
            collection = db["auth"]

            collection.update_one(
                {"_id": "dhan_token"},
                {"$set": data},
                upsert=True
            )

            print("✅ Token saved to MongoDB")

        except Exception as e:
            print(f"❌ MongoDB save error: {e}")


# -------------------------------------------------
# DELETE TOKEN (FOR INVALID CASES)
# -------------------------------------------------
def delete_keys():
    # ✅ EXISTING LOGIC (UNCHANGED)
    try:
        if os.path.exists(KEYS_FILE):
            os.remove(KEYS_FILE)
            print("🗑️ Invalid keys_data.json removed")
    except Exception as e:
        print(f"❌ Failed to delete keys file: {e}")

    # ✅ NEW: Delete from MongoDB also
    if MONGO_URI and MongoClient:
        try:
            client = MongoClient(MONGO_URI)
            db = client["trading"]
            collection = db["auth"]

            collection.delete_one({"_id": "dhan_token"})
            print("🗑️ Token removed from MongoDB")

        except Exception as e:
            print(f"❌ MongoDB delete error: {e}")


# -------------------------------------------------
# VALIDATE RESPONSE DATA
# -------------------------------------------------
def validate_token_data(data: dict):
    for key in REQUIRED_KEYS:
        if key not in data or not data[key]:
            print(f"❌ Missing or empty key: {key}")
            return False
    return True


# -------------------------------------------------
# GENERATE ACCESS TOKEN
# -------------------------------------------------
def generate_access_token(totp: str):
    try:
        dhan_client_id = os.getenv("DHAN_CLIENT_ID")
        dhan_pin = os.getenv("DHAN_PIN")

        if not dhan_client_id or not dhan_pin:
            return {
                "status": "error",
                "message": "Missing DHAN_CLIENT_ID or DHAN_PIN in .env"
            }

        if not totp or len(totp) != 6:
            return {
                "status": "error",
                "message": "Invalid TOTP (must be 6 digits)"
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
            delete_keys()
            return {
                "status": "error",
                "message": f"API Error {response.status_code}",
                "details": response.text
            }

        try:
            data = response.json()
        except Exception:
            delete_keys()
            return {
                "status": "error",
                "message": "Invalid JSON response from API"
            }

        # Validate required fields
        if not validate_token_data(data):
            delete_keys()
            return {
                "status": "error",
                "message": "Invalid token data received",
                "details": data
            }

        # Clean data before saving
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

        return {
            "status": "success",
            "data": clean_data
        }

    except Exception as e:
        delete_keys()
        return {
            "status": "error",
            "message": str(e)
        }
    

# # ---------------------------------------
# # OPTIONAL: CLI MODE (for manual testing)
# # ---------------------------------------
# if __name__ == "__main__":
#     totp = input("Enter TOTP (6-digit code): ").strip()

#     result = generate_access_token(totp)

#     if result["status"] == "success":
#         data = result["data"]

#         print("\n📌 Details:")
#         print(f"Client ID: {data.get('dhanClientId')}")
#         print(f"Name: {data.get('dhanClientName')}")
#         print(f"Expiry: {data.get('expiryTime')}")
#     else:
#         print(f"❌ {result['message']}")
#         if "details" in result:
#             print(result["details"])