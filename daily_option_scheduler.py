import time
import threading
from datetime import datetime
import pytz
from dhanhq import marketfeed

from get_current_spot import get_nearby_option_security_ids

from feed_manager import (
    add_instruments,
    remove_instruments,
    load_instruments
)


# =====================================================
# CONFIG
# =====================================================
IST = pytz.timezone("Asia/Kolkata")

UNSUBSCRIBE_HOUR = 7
UNSUBSCRIBE_MINUTE = 55

SUBSCRIBE_HOUR = 8
SUBSCRIBE_MINUTE = 0


# =====================================================
# LOG
# =====================================================
def log(msg):

    print(
        f"[OPTION-SCHEDULER {datetime.now().strftime('%H:%M:%S')}] {msg}"
    )


# =====================================================
# BUILD INSTRUMENTS
# =====================================================
def build_option_instruments(result):

    instruments = []

    try:

        for index_id, data in result.items():

            # -----------------------------------------
            # CE
            # -----------------------------------------
            for item in data["ce_security_ids"]:

                sid = str(item["security_id"])

                instruments.append(
                    ("NSE_FNO", sid, marketfeed.Ticker)
                )

                instruments.append(
                    ("NSE_FNO", sid, marketfeed.Quote)
                )

            # -----------------------------------------
            # PE
            # -----------------------------------------
            for item in data["pe_security_ids"]:

                sid = str(item["security_id"])

                instruments.append(
                    ("NSE_FNO", sid, marketfeed.Ticker)
                )

                instruments.append(
                    ("NSE_FNO", sid, marketfeed.Quote)
                )

        # ✅ REMOVE DUPLICATES
        instruments = list(set(instruments))

        return instruments

    except Exception as e:

        log(f"Build instruments error: {e}")
        return []


# =====================================================
# REMOVE OLD OPTION INSTRUMENTS
# =====================================================
def remove_old_option_instruments():

    try:

        log("Removing old option instruments...")

        instruments = load_instruments()

        if not instruments:
            log("No old instruments found")
            return

        # -----------------------------------------
        # REMOVE ONLY NSE_FNO
        # KEEP INDEX INSTRUMENTS SAFE
        # -----------------------------------------
        option_instruments = [
            x for x in instruments
            if x[0] == "NSE_FNO"
        ]

        if not option_instruments:
            log("No option instruments to remove")
            return

        response = remove_instruments(option_instruments)

        log(f"Unsubscribe response → {response}")

    except Exception as e:

        log(f"Remove old instruments error: {e}")


# =====================================================
# ADD NEW OPTION INSTRUMENTS
# =====================================================
def add_new_option_instruments():

    try:

        log("Fetching latest option chain instruments...")

        result = get_nearby_option_security_ids()

        if not result:
            log("No option chain result")
            return

        instruments = build_option_instruments(result)

        if not instruments:
            log("No instruments generated")
            return

        log(f"Total instruments to subscribe → {len(instruments)}")

        response = add_instruments(instruments)

        log(f"Subscribe response → {response}")

    except Exception as e:

        log(f"Add new instruments error: {e}")


# =====================================================
# MAIN LOOP
# =====================================================
def scheduler_loop():

    unsubscribe_done = False
    subscribe_done = False

    while True:

        try:

            now = datetime.now(IST)

            hour = now.hour
            minute = now.minute

            # =========================================
            # 7:55 AM IST
            # REMOVE OLD
            # =========================================
            if (
                hour == UNSUBSCRIBE_HOUR
                and minute == UNSUBSCRIBE_MINUTE
                and not unsubscribe_done
            ):

                log("Running unsubscribe scheduler")

                remove_old_option_instruments()

                unsubscribe_done = True
                subscribe_done = False

            # =========================================
            # 8:00 AM IST
            # ADD NEW
            # =========================================
            elif (
                hour == SUBSCRIBE_HOUR
                and minute == SUBSCRIBE_MINUTE
                and not subscribe_done
            ):

                log("Running subscribe scheduler")

                add_new_option_instruments()

                subscribe_done = True
                unsubscribe_done = False

            # =========================================
            # RESET FLAGS AFTER 9 AM
            # =========================================
            elif hour >= 9:

                unsubscribe_done = False
                subscribe_done = False

            time.sleep(20)

        except Exception as e:

            log(f"Scheduler loop error: {e}")

            time.sleep(10)


# =====================================================
# START THREAD
# =====================================================
def start_option_scheduler():

    thread = threading.Thread(
        target=scheduler_loop,
        daemon=True
    )

    thread.start()

    log("Option scheduler started")