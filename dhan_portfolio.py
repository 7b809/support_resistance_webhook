import requests
from config import load_keys
from telegram_logger import send_telegram_alert  # ✅ NEW

BASE_URL = "https://api.dhan.co/v2"


def get_headers():
    data = load_keys()
    if not data:
        return None

    return {
        "Content-Type": "application/json",
        "access-token": data.get("accessToken")
    }


# -------------------------------------------------
# 💰 GET FUND LIMIT (BALANCE)
# -------------------------------------------------
def get_fund_limit():
    headers = get_headers()
    if not headers:
        msg = "Token not available (fundlimit)"
        send_telegram_alert(msg)
        return {"status": "error", "message": msg}

    try:
        res = requests.get(f"{BASE_URL}/fundlimit", headers=headers)

        if res.status_code != 200:
            err = f"FundLimit API Error {res.status_code}\n{res.text}"
            send_telegram_alert(err)
            return {"status": "error", "message": res.text}

        data = res.json()

        formatted = (
            f"💰 *Account Balance*\n\n"
            f"👤 Client ID: {data.get('dhanClientId')}\n"
            f"💵 Available: ₹{data.get('availabelBalance')}\n"
            f"📊 SOD Limit: ₹{data.get('sodLimit')}\n"
            f"📦 Utilized: ₹{data.get('utilizedAmount')}\n"
            f"🔒 Collateral: ₹{data.get('collateralAmount')}\n"
            f"💸 Withdrawable: ₹{data.get('withdrawableBalance')}\n"
        )

        return {"status": "success", "data": formatted}

    except Exception as e:
        err = f"FundLimit Exception:\n{str(e)}"
        send_telegram_alert(err)
        return {"status": "error", "message": str(e)}


# -------------------------------------------------
# 📦 HOLDINGS
# -------------------------------------------------
def get_holdings():
    headers = get_headers()
    if not headers:
        msg = "Token not available (holdings)"
        send_telegram_alert(msg)
        return {"status": "error", "message": msg}

    try:
        res = requests.get(f"{BASE_URL}/holdings", headers=headers)

        if res.status_code != 200:
            err = f"Holdings API Error {res.status_code}\n{res.text}"
            send_telegram_alert(err)
            return {"status": "error", "message": res.text}

        data = res.json()

        if not data:
            return {"status": "success", "data": "📭 No holdings"}

        msg = "📦 *Holdings*\n\n"

        for h in data[:10]:
            msg += (
                f"📈 {h['tradingSymbol']}\n"
                f"Qty: {h['totalQty']} | Avg: ₹{h['avgCostPrice']}\n"
                f"Available: {h['availableQty']}\n\n"
            )

        return {"status": "success", "data": msg}

    except Exception as e:
        err = f"Holdings Exception:\n{str(e)}"
        send_telegram_alert(err)
        return {"status": "error", "message": str(e)}


# -------------------------------------------------
# 📊 POSITIONS
# -------------------------------------------------
def get_positions():
    headers = get_headers()
    if not headers:
        msg = "Token not available (positions)"
        send_telegram_alert(msg)
        return {"status": "error", "message": msg}

    try:
        res = requests.get(f"{BASE_URL}/positions", headers=headers)

        if res.status_code != 200:
            err = f"Positions API Error {res.status_code}\n{res.text}"
            send_telegram_alert(err)
            return {"status": "error", "message": res.text}

        data = res.json()

        if not data:
            return {"status": "success", "data": "📭 No positions"}

        msg = "📊 *Positions*\n\n"

        for p in data[:10]:
            msg += (
                f"📌 {p['tradingSymbol']} ({p['positionType']})\n"
                f"Qty: {p['netQty']}\n"
                f"P&L: ₹{p['unrealizedProfit']}\n\n"
            )

        return {"status": "success", "data": msg}

    except Exception as e:
        err = f"Positions Exception:\n{str(e)}"
        send_telegram_alert(err)
        return {"status": "error", "message": str(e)}


# -------------------------------------------------
# ❌ EXIT ALL POSITIONS
# -------------------------------------------------
def exit_all_positions():
    headers = get_headers()
    if not headers:
        msg = "Token not available (exit positions)"
        send_telegram_alert(msg)
        return {"status": "error", "message": msg}

    try:
        res = requests.delete(f"{BASE_URL}/positions", headers=headers)

        if res.status_code != 200:
            err = f"Exit Positions Error {res.status_code}\n{res.text}"
            send_telegram_alert(err)
            return {"status": "error", "message": res.text}

        return {"status": "success", "data": "✅ All positions exited"}

    except Exception as e:
        err = f"Exit Positions Exception:\n{str(e)}"
        send_telegram_alert(err)
        return {"status": "error", "message": str(e)}