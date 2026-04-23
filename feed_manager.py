import os
import threading
import asyncio
import time
from dotenv import load_dotenv
from dhanhq import marketfeed
from datetime import datetime
from websockets.exceptions import ConnectionClosedError
from config import load_instruments, save_instruments, remove_instruments_db,load_keys
RECONNECT_DELAY = 3
# -------------------------------------------------
# ENV CONFIG
# -------------------------------------------------
TEST_LOG = os.getenv("PRINT_LOGS", "false").strip().lower() in ("true", "1", "yes")
TEST_MODE = os.getenv("TEST_MODE", "false").strip().lower() in ("true", "1", "yes")

# -------------------------------------------------
# LOGGING
# -------------------------------------------------
def log(msg, level="INFO"):
    if TEST_LOG:
        print(f"[FEED {level} {datetime.now().strftime('%H:%M:%S')}] {msg}")


load_dotenv()


# -------------------------------------------------
# GET TOKEN (DYNAMIC)
# -------------------------------------------------
def get_credentials():
    try:
        data = load_keys()

        if not data:
            log("No token data found", "ERROR")
            return None, None

        return data.get("dhanClientId"), data.get("accessToken")

    except Exception as e:
        log(f"Credential fetch error: {e}", "ERROR")
        return None, None


# -------------------------------------------------
# STATIC INITIAL SECURITIES (UNCHANGED)
# -------------------------------------------------
ALLOWED_SECURITIES = {
    "13": [
        (marketfeed.IDX, "13", marketfeed.Ticker),
        (marketfeed.IDX, "13", marketfeed.Quote),
    ],
    "21": [
        (marketfeed.IDX, "21", marketfeed.Ticker),
        (marketfeed.IDX, "21", marketfeed.Quote),
    ],
    "51": [
        (marketfeed.IDX, "51", marketfeed.Ticker),
        (marketfeed.IDX, "51", marketfeed.Quote),
    ],
   
}


# -------------------------------------------------
# SUBSCRIBERS (UNCHANGED + DYNAMIC SAFE)
# -------------------------------------------------
SUBSCRIBERS = {
    (sid, mode): set() for sid in ALLOWED_SECURITIES for mode in ("ticker", "quote")
}


# -------------------------------------------------
# BUILD INITIAL INSTRUMENTS
# -------------------------------------------------
def build_instruments():
    ins = []
    for subs in ALLOWED_SECURITIES.values():
        ins.extend(subs)
    return ins


# -------------------------------------------------
# FEED MANAGER
# -------------------------------------------------
class FeedManager:
    def start(self):
        log("FeedManager started")

        while True:
            try:
                CLIENT_ID, ACCESS_TOKEN = get_credentials()

                if not CLIENT_ID or not ACCESS_TOKEN:
                    log("Missing token. Waiting...", "WARN")
                    time.sleep(5)
                    continue

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                global LIVE_FEED

                # -------------------------------------------------
                # LOAD FROM DB + STATIC
                # -------------------------------------------------
                initial_instruments = build_instruments()
                db_instruments = load_instruments()

                # merge + remove duplicates
                combined = list(set(initial_instruments + db_instruments))

                log(f"Loaded from DB → {len(db_instruments)} instruments")

                # -------------------------------------------------
                # 🔥 INIT SUBSCRIBERS FOR DB INSTRUMENTS
                # -------------------------------------------------
                for ex, sid, typ in db_instruments:
                    sid = str(sid)

                    if (sid, "ticker") not in SUBSCRIBERS:
                        SUBSCRIBERS[(sid, "ticker")] = set()

                    if (sid, "quote") not in SUBSCRIBERS:
                        SUBSCRIBERS[(sid, "quote")] = set()

                feed = marketfeed.DhanFeed(
                    CLIENT_ID,
                    ACCESS_TOKEN,
                    combined,
                    version="v2",
                )

                LIVE_FEED = feed  # ⭐ store globally

                log("Connecting to Dhan feed...")
                feed.run_forever()
                log("Feed connected")

                while True:
                    try:
                        msg = feed.get_data()

                        if not msg:
                            continue

                        sid = str(msg.get("security_id"))
                        mtype = msg.get("type")

                        if mtype == "Ticker Data":
                            key = (sid, "ticker")
                        elif mtype == "Quote Data":
                            key = (sid, "quote")
                        else:
                            continue

                        # Safe callback execution
                        for cb in list(SUBSCRIBERS.get(key, [])):
                            try:
                                cb(msg)
                            except Exception as cb_err:
                                log(f"Callback error: {cb_err}", "ERROR")

                    except Exception as inner_err:
                        log(f"Data processing error: {inner_err}", "ERROR")
                        time.sleep(1)

            except ConnectionClosedError:
                log("Feed disconnected, restarting feed...", "WARN")
                time.sleep(RECONNECT_DELAY)
                continue  # 🔥 THIS IS IMPORTANT
            
            except Exception as e:
                log(f"Feed error: {e}", "ERROR")

                # 🔥 Treat as reconnect case
                time.sleep(RECONNECT_DELAY)
                continue


# -------------------------------------------------
# ➕ ADD INSTRUMENTS (CRUD)
# -------------------------------------------------
def add_instruments(symbols):
    global LIVE_FEED, SUBSCRIBERS

    if not LIVE_FEED:
        return {"status": "error", "message": "Feed not started"}

    try:
        # -------------------------------------------------
        # REMOVE DUPLICATES + FILTER EXISTING
        # -------------------------------------------------
        symbols = list(set(symbols))

        existing = set(LIVE_FEED.instruments)
        symbols = list(set(symbols) - existing)

        if not symbols:
            return {
                "status": "success",
                "message": "No new instruments to subscribe"
            }

        LIVE_FEED.subscribe_symbols(symbols)
        save_instruments(symbols)


        # -------------------------------------------------
        # LOG UPDATED INSTRUMENTS
        # -------------------------------------------------
        try:
            instruments = LIVE_FEED.instruments
            count = len(instruments)

            log(f"Updated Instruments Count → {count}")

            if count <= 10:
                for ex, sid, typ in sorted(instruments):
                    log(f"Instrument → EX:{ex} | SID:{sid} | TYPE:{typ}")
            else:
                security_ids = sorted({sid for _, sid, _ in instruments})
                log(f"Security IDs → {security_ids}")

        except Exception as log_err:
            log(f"Post-subscribe log error: {log_err}", "ERROR")
 

        # ✅ Ensure subscribers exist
        for ex, sec_id, typ in symbols:
            sid = str(sec_id)

            if (sid, "ticker") not in SUBSCRIBERS:
                SUBSCRIBERS[(sid, "ticker")] = set()

            if (sid, "quote") not in SUBSCRIBERS:
                SUBSCRIBERS[(sid, "quote")] = set()

        log(f"Subscribed: {symbols}")

        return {
            "status": "success",
            "message": "Instruments subscribed",
            "data": symbols,
        }

    except Exception as e:
        log(f"Subscribe error: {e}", "ERROR")
        return {"status": "error", "message": str(e)}


# -------------------------------------------------
# ➖ REMOVE INSTRUMENTS (CRUD)
# -------------------------------------------------
def remove_instruments(symbols):
    global LIVE_FEED, SUBSCRIBERS

    if not LIVE_FEED:
        return {"status": "error", "message": "Feed not started"}

    try:

        LIVE_FEED.unsubscribe_symbols(symbols)
        
        remove_instruments_db(symbols)

        # -------------------------------------------------
        # LOG UPDATED INSTRUMENTS (NEW)
        # -------------------------------------------------
        try:
            instruments = LIVE_FEED.instruments
            count = len(instruments)

            log(f"Updated Instruments Count → {count}")

            if count <= 10:
                for ex, sid, typ in sorted(instruments):
                    log(f"Instrument → EX:{ex} | SID:{sid} | TYPE:{typ}")
            else:
                security_ids = sorted({sid for _, sid, _ in instruments})
                log(f"Security IDs → {security_ids}")

        except Exception as log_err:
            log(f"Post-unsubscribe log error: {log_err}", "ERROR")
            

        # ✅ Clean subscribers
        for ex, sec_id, typ in symbols:
            sid = str(sec_id)

            SUBSCRIBERS.pop((sid, "ticker"), None)
            SUBSCRIBERS.pop((sid, "quote"), None)

        log(f"Unsubscribed: {symbols}")

        return {
            "status": "success",
            "message": "Instruments unsubscribed",
            "data": symbols,
        }

    except Exception as e:
        log(f"Unsubscribe error: {e}", "ERROR")
        return {"status": "error", "message": str(e)}


# -------------------------------------------------
# 📄 GET CURRENT INSTRUMENTS
# -------------------------------------------------
def get_current_instruments():
    global LIVE_FEED

    if not LIVE_FEED:
        return {"status": "error", "message": "Feed not started"}

    try:
        return {
            "status": "success",
            "instruments": LIVE_FEED.instruments,
        }
    except Exception as e:
        log(f"Fetch instruments error: {e}", "ERROR")
        return {"status": "error", "message": str(e)}


# -------------------------------------------------
# START THREAD
# -------------------------------------------------
feed_manager = FeedManager()


def start_feed_thread():
    if os.environ.get("RUN_MAIN") not in (None, "true"):
        return

    try:
        t = threading.Thread(target=feed_manager.start, daemon=True)
        t.start()
        log("Feed thread started")
    except Exception as e:
        log(f"Thread start error: {e}", "ERROR")