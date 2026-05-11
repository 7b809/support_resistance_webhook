import json
import yfinance as yf


# =====================================================
# CONFIG
# =====================================================
INPUT_FILE = "data.json"

# ✅ RANGE (+/-)
POINT_RANGE = 1000

# ✅ INDEX CONFIG
INDEX_CONFIG = {
    13: {
        "name": "NIFTY",
        "yfinance_symbol": "^NSEI"
    },
    51: {
        "name": "SENSEX",
        "yfinance_symbol": "^BSESN"
    }
}


# =====================================================
# GET LIVE SPOT PRICE
# =====================================================
def get_live_spot_price(symbol):

    try:

        ticker = yf.Ticker(symbol)

        data = ticker.history(period="1d")

        if data.empty:
            return None

        # ✅ LAST CLOSE PRICE
        price = float(data["Close"].iloc[-1])

        return price

    except Exception as e:

        print(f"YFINANCE ERROR ({symbol}):", str(e))
        return None


# =====================================================
# GET SECURITY IDS
# =====================================================
def get_nearby_option_security_ids():

    try:

        # ✅ LOAD JSON
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        final_result = {}

        # =================================================
        # LOOP MAIN INDEX IDS
        # =================================================
        for main_index_id, config in INDEX_CONFIG.items():

            index_name = config["name"]
            yf_symbol = config["yfinance_symbol"]

            # =============================================
            # GET LIVE SPOT PRICE
            # =============================================
            live_spot = get_live_spot_price(yf_symbol)

            if not live_spot:
                print(f"Unable to fetch live price for {index_name}")
                continue

            print(f"{index_name} LIVE PRICE:", live_spot)

            lower_range = live_spot - POINT_RANGE
            upper_range = live_spot + POINT_RANGE

            ce_security_ids = []
            pe_security_ids = []

            # =============================================
            # FIND MATCHING DOCUMENT
            # =============================================
            matching_doc = None

            for item in data:

                if item.get("index_security_id") == main_index_id:
                    matching_doc = item
                    break

            if not matching_doc:
                print(f"No option chain found for {main_index_id}")
                continue

            option_chain = matching_doc.get("option_chain", {})

            oc_data = option_chain.get("oc", {})

            # =============================================
            # LOOP STRIKES
            # =============================================
            for strike_str, strike_data in oc_data.items():

                try:
                    strike = float(strike_str)
                except:
                    continue

                # ✅ WITHIN RANGE
                if lower_range <= strike <= upper_range:

                    # -----------------------------------------
                    # CE
                    # -----------------------------------------
                    ce_data = strike_data.get("ce", {})

                    ce_sid = ce_data.get("security_id")

                    if ce_sid:

                        ce_security_ids.append({
                            "strike": strike,
                            "security_id": ce_sid
                        })

                    # -----------------------------------------
                    # PE
                    # -----------------------------------------
                    pe_data = strike_data.get("pe", {})

                    pe_sid = pe_data.get("security_id")

                    if pe_sid:

                        pe_security_ids.append({
                            "strike": strike,
                            "security_id": pe_sid
                        })

            # =============================================
            # SORT STRIKES
            # =============================================
            ce_security_ids.sort(key=lambda x: x["strike"])
            pe_security_ids.sort(key=lambda x: x["strike"])

            # =============================================
            # FINAL RESULT
            # =============================================
            final_result[main_index_id] = {
                "index_name": index_name,
                "spot_price": live_spot,
                "lower_range": lower_range,
                "upper_range": upper_range,
                "total_ce": len(ce_security_ids),
                "total_pe": len(pe_security_ids),
                "ce_security_ids": ce_security_ids,
                "pe_security_ids": pe_security_ids
            }

        return final_result

    except Exception as e:

        print("ERROR:", str(e))
        return {}


# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":

    result = get_nearby_option_security_ids()

    print(
        json.dumps(
            result,
            indent=4
        )
    )