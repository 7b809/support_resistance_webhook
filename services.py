import os
from dhanhq import dhanhq
from config import load_keys,option_cache_collection
from datetime import datetime

# ✅ SINGLE SOURCE OF TRUTH
BASIC_LOGS = os.getenv("BASIC_LOGS", "false").lower() == "true"
LOCAL_CACHE = {}


def log(msg):
    if BASIC_LOGS:
        print(msg)


def log_line():
    if BASIC_LOGS:
        print("-" * 40)

def get_nearest_strike_data(option_chain_json, target_price, option_type):
    try:
        oc_data = option_chain_json.get("data", {}).get("data", {}).get("oc", {})

        if not oc_data:
            return {"error": "Option chain data missing"}

        strikes = sorted([float(k) for k in oc_data.keys()])

        # 🎯 ALWAYS FLOOR (for both CE & PE)
        valid_strikes = [s for s in strikes if s <= target_price]
        nearest_strike = max(valid_strikes) if valid_strikes else strikes[0]

        strike_key = f"{nearest_strike:.6f}"
        strike_data = oc_data.get(strike_key, {})

        ce = strike_data.get("ce", {})
        pe = strike_data.get("pe", {})

        return {
            "nearest_strike": nearest_strike,
            "ce_security_id": ce.get("security_id"),
            "ce_price": ce.get("last_price"),
            "pe_security_id": pe.get("security_id"),
            "pe_price": pe.get("last_price"),
        }

    except Exception as e:
        return {"error": str(e)}

def get_option_contract(security_id, option_type):
    """
    security_id → index (13 / 51)
    option_type → buyCE / buyPE
    """

    try:
        log_line()
        log(f"🔍 Fetching option contract | SecID={security_id} | Type={option_type}")

        # -----------------------------
        # 🔐 STEP 0: Credentials
        # -----------------------------
        log_line()


        creds = load_keys()

        print(creds.keys())
        if not creds:
            return {"error": "No valid credentials"}


        dhan_instance = dhanhq(creds['dhanClientId'], creds['accessToken'])

        # -----------------------------
        # 📅 STEP 1: Expiry
        # -----------------------------
        log_line()

        expiry_data = dhan_instance.expiry_list(
            under_security_id=int(security_id),
            under_exchange_segment="IDX_I"
        )

        log(f"📅 Expiry API Response: {expiry_data}")

        expiry_list = expiry_data.get("data", {}).get("data", [])

        if not expiry_list:
            return {"error": "No expiry data"}

        expiry = expiry_list[0]
        log(f"✅ Selected Expiry: {expiry}")

        # -----------------------------
        # 📊 STEP 2: Option Chain
        # -----------------------------
        log_line()

        oc = dhan_instance.option_chain(
            under_security_id=int(security_id),
            under_exchange_segment="IDX_I",
            expiry=expiry
        )

        log(f"📊 Option Chain Response received")

        oc_data = oc.get("data", {}).get("data", {})

        if not oc_data:
            return {"error": "Invalid option chain response"}

        # -----------------------------
        # 📈 STEP 3: Spot Price
        # -----------------------------
        log_line()

        spot_price = oc_data.get("last_price")

        if spot_price is None:
            return {"error": "Missing spot price"}

        log(f"📈 Spot Price: {spot_price}")

        # -----------------------------
        # 🎯 STEP 4: Nearest Strike
        # -----------------------------
        log_line()

        result = get_nearest_strike_data(oc, spot_price, option_type)

        log(f"🎯 Nearest Strike Data: {result}")

        if not isinstance(result, dict) or "error" in result:
            return {"error": result.get("error", "Invalid strike data")}

        # -----------------------------
        # 🧾 STEP 5: Select Contract
        # -----------------------------
        log_line()

        if option_type == "buyCE":
            sec_id = result.get("ce_security_id")
            price = result.get("ce_price")

        elif option_type == "buyPE":
            sec_id = result.get("pe_security_id")
            price = result.get("pe_price")

        else:
            return {"error": "Invalid option type"}

        # -----------------------------
        # ❌ FINAL VALIDATION
        # -----------------------------
        log_line()

        if not sec_id or price is None:
            return {"error": "Invalid contract data"}

        log(f"✅ Selected Contract → SecID: {sec_id}, Price: {price}")

        # -----------------------------
        # ✅ FINAL RESPONSE
        # -----------------------------
        log_line()

        return {
            "security_id": sec_id,
            "price": price,
            "strike": result.get("nearest_strike"),
            "spot_price": spot_price
        }

    except Exception as e:
        # 🔥 ALWAYS log errors
        print(f"❌ Exception in get_option_contract: {str(e)}")
        return {"error": str(e)}
    
def get_option_by_strike(security_id, strike_price, strike_type):
    """
    security_id → 13 (NIFTY)
    strike_price → 23400
    strike_type → "CE" / "PE"
    """

    try:
        log_line()
        log(f"🔍 Fetching by Strike | SecID={security_id} | Strike={strike_price} | Type={strike_type}")

        # -----------------------------
        # 🛑 INPUT VALIDATION
        # -----------------------------
        if not isinstance(security_id, (int, str)):
            return {"error": "Invalid security_id type"}

        if not isinstance(strike_price, (int, float)) or strike_price <= 0:
            return {"error": "Invalid strike_price"}

        if strike_type.upper() not in ("CE", "PE"):
            return {"error": "Invalid strike_type (must be CE or PE)"}

        # -----------------------------
        # ⚡ STEP 0: CACHE CHECK
        # -----------------------------
        cached = get_cached_option(security_id, strike_price, strike_type)

        if cached:
            log(f"⚡ CACHE HIT → {strike_price} {strike_type}")

            return {
                "security_id": cached["option_security_id"],
                "price": cached.get("price"),
                "strike": cached["strike"],
                "input_strike": strike_price,
                "expiry": cached["expiry"],
                "type": strike_type.upper(),
                "source": "cache"
            }

        log("🚀 CACHE MISS → Calling API")

        # -----------------------------
        # 🔐 Credentials
        # -----------------------------
        creds = load_keys()

        if not creds:
            return {"error": "No valid credentials"}

        client_id = creds.get("dhanClientId")
        access_token = creds.get("accessToken")

        if not client_id or not access_token:
            return {"error": "Invalid credential format"}

        dhan_instance = dhanhq(client_id, access_token)

        # -----------------------------
        # 📅 Expiry
        # -----------------------------
        expiry_data = dhan_instance.expiry_list(
            under_security_id=int(security_id),
            under_exchange_segment="IDX_I"
        )

        expiry_list = expiry_data.get("data", {}).get("data", [])

        if not expiry_list:
            return {"error": f"No expiry data for security_id={security_id}"}

        expiry = expiry_list[0]

        # -----------------------------
        # 📊 Option Chain
        # -----------------------------
        oc = dhan_instance.option_chain(
            under_security_id=int(security_id),
            under_exchange_segment="IDX_I",
            expiry=expiry
        )

        oc_data = oc.get("data", {}).get("data", {}).get("oc", {})

        if not oc_data:
            return {"error": "Option chain missing or empty"}

        # -----------------------------
        # 🎯 Find Nearest Strike
        # -----------------------------
        try:
            strikes = sorted([float(k) for k in oc_data.keys()])
        except Exception:
            return {"error": "Invalid strike format in option chain"}

        if not strikes:
            return {"error": "No strikes available"}

        nearest_strike = min(strikes, key=lambda x: abs(x - strike_price))

        if abs(nearest_strike - strike_price) > 500:
            return {
                "error": f"Strike {strike_price} too far",
                "nearest_available": nearest_strike
            }

        strike_key = f"{nearest_strike:.6f}"
        strike_data = oc_data.get(strike_key)

        if not strike_data:
            return {"error": "Strike not found"}

        # -----------------------------
        # 🧾 Select CE / PE
        # -----------------------------
        if strike_type.upper() == "CE":
            opt = strike_data.get("ce")
        else:
            opt = strike_data.get("pe")

        if not opt:
            return {"error": f"{strike_type} not available"}

        sec_id = opt.get("security_id")
        price = opt.get("last_price")

        if not sec_id or price is None:
            return {"error": "Invalid contract data"}

        # -----------------------------
        # 💾 SAVE CACHE
        # -----------------------------
        cache_data = {
            "security_id": str(security_id),
            "option_security_id": sec_id,
            "price": price,
            "strike": nearest_strike,
            "input_strike": strike_price,
            "expiry": expiry,
            "type": strike_type.upper(),
            "date": get_today()
        }

        save_option_cache(cache_data)

        # -----------------------------
        # ✅ RETURN
        # -----------------------------
        return {
            "security_id": sec_id,
            "price": price,
            "strike": nearest_strike,
            "input_strike": strike_price,
            "expiry": expiry,
            "type": strike_type.upper(),
            "source": "api"
        }

    except Exception as e:
        print(f"❌ Exception in get_option_by_strike: {str(e)}")
        return {"error": f"Internal error: {str(e)}"}
    

# 🔥 L1 CACHE (RAM)

if len(LOCAL_CACHE) > 2000:
    LOCAL_CACHE.clear()

def get_today():
    return datetime.utcnow().strftime("%Y-%m-%d")


def get_cached_option(security_id, strike, opt_type):
    key = (str(security_id), float(strike), opt_type.upper())

    # -----------------------------
    # ⚡ L1 CACHE (FASTEST)
    # -----------------------------
    if key in LOCAL_CACHE:
        return LOCAL_CACHE[key]

    # -----------------------------
    # 💾 L2 CACHE (MONGO)
    # -----------------------------
    if not option_cache_collection:
        return None

    # remove strike from query
    data = option_cache_collection.find_one({
        "security_id": str(security_id),
        "type": opt_type.upper(),
        "date": get_today()
    })

    if data and abs(data.get("strike", 0) - float(strike)) <= 50:
        LOCAL_CACHE[key] = data
        return data


    return None


def save_option_cache(data):
    key = (str(data["security_id"]), float(data["input_strike"]), data["type"])

    # -----------------------------
    # 💾 SAVE TO MONGO
    # -----------------------------
    if option_cache_collection:
        option_cache_collection.update_one(
            {
                "security_id": str(data["security_id"]),
                "strike": float(data["input_strike"]),
                "type": data["type"],
                "date": get_today()
            },
            {"$set": data},
            upsert=True
        )

    # -----------------------------
    # ⚡ SAVE TO RAM
    # -----------------------------
    LOCAL_CACHE[key] = data

# if __name__ == "__main__":
#     result = get_option_by_strike(13, 23400, "CE")
#     print(result) 