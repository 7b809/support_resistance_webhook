import os
import threading
import asyncio
import time
from dotenv import load_dotenv
from dhanhq import marketfeed
from datetime import datetime
from websockets.exceptions import ConnectionClosedError

TEST_LOG = False
RECONNECT_DELAY = 3

def log(msg):
    if TEST_LOG:
        print(f"[FEED {datetime.now().strftime('%H:%M:%S')}] {msg}")

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

ALLOWED_SECURITIES = {
    "13": [(marketfeed.IDX, "13", marketfeed.Ticker), (marketfeed.IDX, "13", marketfeed.Quote)],
    "21": [(marketfeed.IDX, "21", marketfeed.Ticker), (marketfeed.IDX, "21", marketfeed.Quote)],
    "51": [(marketfeed.IDX, "51", marketfeed.Ticker), (marketfeed.IDX, "51", marketfeed.Quote)],
    "5024": [(marketfeed.IDX, "5024", marketfeed.Ticker), (marketfeed.IDX, "5024", marketfeed.Quote)],
}

SUBSCRIBERS = { (sid, mode): set() for sid in ALLOWED_SECURITIES for mode in ("ticker", "quote") }

def build_instruments():
    ins = []
    for subs in ALLOWED_SECURITIES.values(): ins.extend(subs)
    return ins

class FeedManager:
    def start(self):
        log("FeedManager started")
        while True:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                feed = marketfeed.DhanFeed(CLIENT_ID, ACCESS_TOKEN, build_instruments(), version="v2")
                feed.run_forever()
                log("Feed connected")
                while True:
                    msg = feed.get_data()
                    print(msg)
                    if not msg: continue
                    sid = str(msg.get("security_id"))
                    mtype = msg.get("type")
                    if mtype == "Ticker Data": key = (sid, "ticker")
                    elif mtype == "Quote Data": key = (sid, "quote")
                    else: continue
                    for cb in list(SUBSCRIBERS.get(key, [])): cb(msg)
            except ConnectionClosedError:
                log("Feed disconnected, reconnecting")
                time.sleep(RECONNECT_DELAY)
            except Exception as e:
                log(f"Error: {e}")
                time.sleep(RECONNECT_DELAY)

feed_manager = FeedManager()

def start_feed_thread():
    if os.environ.get("RUN_MAIN") not in (None, "true"):
        return
    t = threading.Thread(target=feed_manager.start, daemon=True)
    t.start()
