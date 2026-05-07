import websockets

# 🔥 PATCH for dhanhq compatibility
try:
    from websockets.legacy.client import WebSocketClientProtocol

    if not hasattr(WebSocketClientProtocol, "closed"):
        WebSocketClientProtocol.closed = property(
            lambda self: self.close_code is not None
        )
except Exception as e:
    print("Patch skipped:", e)

# -------------------------------------------------
# IMPORTS
# -------------------------------------------------
import os
import threading
import asyncio
import time
from dotenv import load_dotenv
from dhanhq import marketfeed
from datetime import datetime
from websockets.exceptions import ConnectionClosedError
from config import load_instruments, save_instruments, remove_instruments_db, load_keys

# -------------------------------------------------
# CONFIG
# -------------------------------------------------
RECONNECT_DELAY = 3

TEST_LOG = os.getenv("PRINT_LOGS", "false").strip().lower() in ("true", "1", "yes")

LIVE_FEED = None
FEED_READY = False

load_dotenv()

# -------------------------------------------------
# LOG
# -------------------------------------------------
def log(msg, level="INFO"):
    if TEST_LOG:
        print(f"[FEED {level} {datetime.now().strftime('%H:%M:%S')}] {msg}")

# -------------------------------------------------
# GET TOKEN
# -------------------------------------------------
def get_credentials():
    try:
        data = load_keys()

        if data is None:
            log("No token data found", "ERROR")
            return None, None

        return data.get("dhanClientId"), data.get("accessToken")

    except Exception as e:
        log(f"Credential fetch error: {e}", "ERROR")
        return None, None

# -------------------------------------------------
# STATIC SECURITIES
# -------------------------------------------------
ALLOWED_SECURITIES = {
    "13": [(marketfeed.IDX, "13", marketfeed.Ticker), (marketfeed.IDX, "13", marketfeed.Quote)],
    "21": [(marketfeed.IDX, "21", marketfeed.Ticker), (marketfeed.IDX, "21", marketfeed.Quote)],
    "51": [(marketfeed.IDX, "51", marketfeed.Ticker), (marketfeed.IDX, "51", marketfeed.Quote)],
}

# -------------------------------------------------
# SUBSCRIBERS
# -------------------------------------------------
SUBSCRIBERS = {
    (sid, mode): set() for sid in ALLOWED_SECURITIES for mode in ("ticker", "quote")
}

# -------------------------------------------------
# BUILD INSTRUMENTS
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
        global LIVE_FEED, FEED_READY

        log("FeedManager started")

        while True:
            try:
                CLIENT_ID, ACCESS_TOKEN = get_credentials()

                if not CLIENT_ID or not ACCESS_TOKEN:
                    log("Missing token. Waiting...", "WARN")
                    time.sleep(5)
                    continue

                # -----------------------------
                # LOAD INSTRUMENTS
                # -----------------------------
                initial = build_instruments()
                db_instruments = load_instruments()

                combined = list(set(initial + db_instruments))

                log(f"Loaded from DB → {len(db_instruments)} instruments")

                # ensure subscriber buckets exist
                for ex, sid, typ in combined:
                    sid = str(sid)
                    if (sid, "ticker") not in SUBSCRIBERS:
                        SUBSCRIBERS[(sid, "ticker")] = set()
                    if (sid, "quote") not in SUBSCRIBERS:
                        SUBSCRIBERS[(sid, "quote")] = set()

                # -----------------------------
                # INIT FEED
                # -----------------------------
                feed = marketfeed.DhanFeed(
                    CLIENT_ID,
                    ACCESS_TOKEN,
                    combined,
                    version="v2"
                )

                LIVE_FEED = feed
                FEED_READY = False

                log("Connecting to Dhan feed...")

                feed.run_forever()

                log("✅ Feed connected")

                # -----------------------------
                # PROCESS DATA
                # -----------------------------
                first_data_received = False

                while True:
                    try:
                        msg = feed.get_data()

                        if not msg:
                            continue

                        # ✅ mark ready when first tick received
                        if not first_data_received:
                            FEED_READY = True
                            first_data_received = True
                            log("✅ Feed READY (data flow started)")

                        sid = str(msg.get("security_id"))
                        mtype = msg.get("type")

                        if mtype == "Ticker Data":
                            key = (sid, "ticker")
                        elif mtype == "Quote Data":
                            key = (sid, "quote")
                        else:
                            continue

                        for cb in list(SUBSCRIBERS.get(key, [])):
                            try:
                                cb(msg)
                            except Exception as cb_err:
                                log(f"Callback error: {cb_err}", "ERROR")

                    except Exception as e:
                        log(f"Data processing error: {e}", "ERROR")
                        time.sleep(1)

            except ConnectionClosedError:
                log("Feed disconnected → reconnecting...", "WARN")
                time.sleep(RECONNECT_DELAY)
                continue

            except Exception as e:
                log(f"Feed error: {e}", "ERROR")
                time.sleep(RECONNECT_DELAY)
                continue

# -------------------------------------------------
# ADD INSTRUMENTS
# -------------------------------------------------
def add_instruments(symbols):
    global LIVE_FEED

    if LIVE_FEED is None:
        return {"status": "error", "message": "Feed not initialized"}

    # ✅ WAIT FOR READY
    for _ in range(10):
        if FEED_READY:
            break
        time.sleep(0.3)

    if not FEED_READY:
        return {"status": "error", "message": "Feed not ready yet"}

    try:
        symbols = list(set(symbols))
        existing = set(LIVE_FEED.instruments)

        symbols = list(set(symbols) - existing)

        if not symbols:
            return {"status": "success", "message": "No new instruments"}

        LIVE_FEED.subscribe_symbols(symbols)
        save_instruments(symbols)

        # ensure subscriber keys
        for ex, sid, typ in symbols:
            sid = str(sid)
            SUBSCRIBERS.setdefault((sid, "ticker"), set())
            SUBSCRIBERS.setdefault((sid, "quote"), set())

        log(f"Subscribed: {symbols}")

        return {"status": "success", "data": symbols}

    except Exception as e:
        log(f"Subscribe error: {e}", "ERROR")
        return {"status": "error", "message": str(e)}

# -------------------------------------------------
# REMOVE INSTRUMENTS
# -------------------------------------------------
def remove_instruments(symbols):
    global LIVE_FEED

    if LIVE_FEED is None:
        return {"status": "error", "message": "Feed not initialized"}

    try:
        LIVE_FEED.unsubscribe_symbols(symbols)
        remove_instruments_db(symbols)

        for ex, sid, typ in symbols:
            sid = str(sid)
            SUBSCRIBERS.pop((sid, "ticker"), None)
            SUBSCRIBERS.pop((sid, "quote"), None)

        log(f"Unsubscribed: {symbols}")

        return {"status": "success", "data": symbols}

    except Exception as e:
        log(f"Unsubscribe error: {e}", "ERROR")
        return {"status": "error", "message": str(e)}

# -------------------------------------------------
# GET CURRENT
# -------------------------------------------------
def get_current_instruments():
    if LIVE_FEED is None:
        return {"status": "error", "message": "Feed not initialized"}

    if not FEED_READY:
        return {"status": "error", "message": "Feed not ready"}

    return {"status": "success", "instruments": LIVE_FEED.instruments}

# -------------------------------------------------
# THREAD START
# -------------------------------------------------
feed_manager = FeedManager()

def start_feed_thread():
    if os.environ.get("RUN_MAIN") not in (None, "true"):
        return

    global LIVE_FEED

    if LIVE_FEED is not None:
        log("Feed already running")
        return

    t = threading.Thread(target=feed_manager.start, daemon=True)
    t.start()

    log("Feed thread started")
