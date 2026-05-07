from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import asyncio, os
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from feed_manager import add_instruments, SUBSCRIBERS
from feed_manager import LIVE_FEED
from config import load_keys, is_token_valid
from authentication import generate_access_token
from telegram_bot import start_telegram_bot
from services import get_option_by_strike,LOCAL_CACHE
import feed_manager

from feed_manager import (
    ALLOWED_SECURITIES,
    SUBSCRIBERS,
    start_feed_thread,
    get_current_instruments,
    
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from jinja2 import Environment, FileSystemLoader
from starlette.templating import Jinja2Templates
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

jinja_env = Environment(
    loader=FileSystemLoader(os.path.join(BASE_DIR, "templates")),
    autoescape=True,
)

templates = Jinja2Templates(env=jinja_env)



# -------------------------------------------------
# ENV CONFIG
# -------------------------------------------------
APP_LOGS = os.getenv("PRINT_LOGS", "false").strip().lower() in ("true", "1", "yes")
TEST_MODE = os.getenv("TEST_MODE", "false").strip().lower() in ("true", "1", "yes")
def log(msg, level="INFO"):
    if APP_LOGS:
        print(f"[APP {level} {datetime.now().strftime('%H:%M:%S')}] {msg}")
 

# -------------------------------------------------
# LIFESPAN
# -------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):

    # do not remove this we commenting this for temperory if not commented
    try:
        log("Starting Telegram bot...")
        start_telegram_bot()
    except Exception as e:
        log(f"Telegram bot start error: {e}", "ERROR")

    try:
        if is_token_valid():
            log("Token valid → starting feed")
            start_feed_thread()

            # ✅ NEW: wait & log instruments
            if APP_LOGS:

                async def log_instruments():
                    await asyncio.sleep(3)  # 🔥 increase wait (important)

                    try:
                        data = get_current_instruments()

                        if data.get("status") != "success":
                            log("Feed not ready yet (skip logging)", "WARN")
                            return

                        instruments = data.get("instruments", [])
                        count = len(instruments)

                        log(f"Active Instruments Loaded → {count}")

                        if count <= 10:
                            for ex, sid, typ in instruments:
                                log(f"Instrument → EX:{ex} | SID:{sid} | TYPE:{typ}")
                        else:
                            security_ids = sorted({sid for _, sid, _ in instruments})
                            log(f"Security IDs → {security_ids}")

                    except Exception as e:
                        log(f"Startup instrument log error: {e}", "ERROR")


                asyncio.create_task(log_instruments())

        else:
            log("Waiting for TOTP from Telegram...", "WARN")

    except Exception as e:
        log(f"Feed start error: {e}", "ERROR")

    yield

app = FastAPI(
    title="Dhan Market Dashboard",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or restrict later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# # -------------------------------------------------
# # MIDDLEWARE
# # -------------------------------------------------
# @app.middleware("http")
# async def check_token_middleware(request: Request, call_next):
#     try:
#         public_paths = {"/", "/token", "/generate-token", "/favicon.ico", "/ui"}

#         path = str(request.url.path)  # 🔥 FORCE STRING (fix)

#         if path not in public_paths:
#             if not is_token_valid():
#                 log("Blocked request → token invalid", "WARN")
#                 return HTMLResponse(
#                     content="❌ Token not available. Send TOTP via Telegram.",
#                     status_code=401
#                 )

#         response = await call_next(request)
#         return response

#     except Exception as e:
#         log(f"Middleware error: {e}", "ERROR")
#         return HTMLResponse(content="❌ Internal Server Error", status_code=500)
    

# -------------------------------------------------
# TOKEN PAGE
# -------------------------------------------------
@app.get("/token", response_class=HTMLResponse)
def token_page(request: Request):
    try:
        return templates.TemplateResponse("token.html", {"request": request})
    except Exception as e:
        log(f"Token page error: {e}", "ERROR")
        return HTMLResponse("❌ Failed to load token page", status_code=500)


# -------------------------------------------------
# GENERATE TOKEN
# -------------------------------------------------
@app.post("/generate-token")
def generate_token(totp: str = Form(...)):
    try:
        result = generate_access_token(totp)

        if result["status"] == "error":
            log(f"Token generation failed: {result['message']}", "ERROR")
            return HTMLResponse(
                content=f"<h3 style='color:red'>Error: {result['message']}</h3>",
                status_code=400
            )

        log("Token refreshed successfully")
        return RedirectResponse(url="/", status_code=303)

    except Exception as e:
        log(f"Generate token error: {e}", "ERROR")
        return HTMLResponse("❌ Token generation failed", status_code=500)


# -------------------------------------------------
# HOME
# -------------------------------------------------
@app.get("/")
def home():
    try:
        data = load_keys()
        expiry = data.get("expiryTime") if isinstance(data, dict) else None

        # -----------------------------
        # 🔥 FEED STATUS
        # -----------------------------
        feed_status = "running" if feed_manager.LIVE_FEED else "not_started"

        # -----------------------------
        # 📊 ACTIVE INSTRUMENTS
        # -----------------------------
        try:
            instruments_data = get_current_instruments()
            instruments = instruments_data.get("instruments", []) if instruments_data.get("status") == "success" else []
            instrument_count = len(instruments)
        except:
            instrument_count = 0

        # -----------------------------
        # ⚡ CACHE STATUS
        # -----------------------------
        try:
            cache_size = len(LOCAL_CACHE)
        except:
            cache_size = 0

        # -----------------------------
        # ✅ RESPONSE
        # -----------------------------
        return {
            "status": "running",
            "message": "Dhan Market API is live",

            # 🔐 Token
            "token_valid": is_token_valid(),
            "expiry_time": str(expiry) if expiry else "None",

            # 📡 Feed
            "feed_status": feed_status,

            # 📊 Instruments
            "active_instruments": instrument_count,

            # ⚡ Cache
            "cache_size": cache_size,

            # 📌 Available
            "available_securities": list(ALLOWED_SECURITIES.keys()),

            # 🔗 Examples
            "websocket_examples": {
                "basic": "/ws/13/quote",
                "dynamic_option": "/ws/option/13/23400/ce/quote"
            }
        }

    except Exception as e:
        log(f"Home endpoint error: {e}", "ERROR")
        return {"status": "error", "message": "Internal error"}

# -------------------------------------------------
# INFO
# -------------------------------------------------
@app.get("/info")
def info():
    try:
        return {
            "available_securities": list(ALLOWED_SECURITIES.keys()),
            "available_websockets": [
                f"/ws/{sid}/{mode}"
                for sid in ALLOWED_SECURITIES
                for mode in ("ticker", "quote")
            ],
        }

    except Exception as e:
        log(f"Info endpoint error: {e}", "ERROR")
        return {"status": "error", "message": "Internal error"}


# -------------------------------------------------
# WEBSOCKET
# -------------------------------------------------
@app.websocket("/ws/{security_id}/{mode}")
async def websocket_handler(ws: WebSocket, security_id: str, mode: str):

    try:
        if not is_token_valid():
            log("WebSocket rejected → invalid token", "WARN")
            await ws.close(code=1008)
            return

        valid_modes = ("ticker", "quote")

        if mode not in valid_modes:
            log(f"Invalid WS mode → {mode}", "WARN")
            await ws.close(code=1008)
            return

        # allow dynamic instruments also
        if (security_id, mode) not in SUBSCRIBERS:
            log(f"WS requested for non-subscribed instrument → {security_id}", "WARN")
            

            log(f"Invalid WS request → {security_id} {mode}", "WARN")
            await ws.close(code=1008)
            return

        await ws.accept()
        log(f"WebSocket connected → {security_id} {mode}")

        loop = asyncio.get_running_loop()

        def sender(message):
            try:
                asyncio.run_coroutine_threadsafe(
                    ws.send_json(message),
                    loop,
                )
            except Exception as send_err:
                log(f"WS send error: {send_err}", "ERROR")

        key = (security_id, mode)
        SUBSCRIBERS[key].add(sender)

        try:
            while True:
                await ws.receive_text()

        except WebSocketDisconnect:
            log(f"WebSocket disconnected → {security_id} {mode}")
            SUBSCRIBERS[key].remove(sender)

    except Exception as e:
        log(f"WebSocket error: {e}", "ERROR")
        try:
            await ws.close()
        except:
            pass

@app.websocket("/ws/option/{security_id}/{strike}/{opt_type}/{mode}")
async def websocket_option_handler(ws: WebSocket, security_id: int, strike: float, opt_type: str, mode: str):

    async def send_error(message, code=1008):
        if not ws.client_state.name == "CONNECTED":
            await ws.accept()
        await ws.send_json({
            "status": "error",
            "message": message
        })
        await ws.close(code=code)

    try:
        # -----------------------------
        # 🔐 TOKEN CHECK
        # -----------------------------
        if not is_token_valid():
            await send_error("Token invalid or expired")
            return

        # -----------------------------
        # 🛑 MODE VALIDATION
        # -----------------------------
        if mode not in ("ticker", "quote"):
            await send_error(f"Invalid mode: {mode}. Use 'ticker' or 'quote'")
            return

        # -----------------------------
        # 🎯 STEP 1: Get option contract
        # -----------------------------
        try:
            result = get_option_by_strike(security_id, strike, opt_type.upper())
        except Exception as e:
            await send_error(f"Error fetching option data: {str(e)}")
            return

        if not result or "error" in result:
            await send_error(result.get("error", "Failed to fetch option contract"))
            return

        option_sid = str(result["security_id"])

        log(f"Dynamic WS → Strike {strike} {opt_type} → SID {option_sid}")

        # -----------------------------
        # 📡 STEP 2: Subscribe dynamically
        # -----------------------------

        instrument = ("NSE_FNO", option_sid, mode)


        if not LIVE_FEED:
            await send_error("Feed not ready. Try again.")
            return

        try:
            add_instruments([instrument])
        except Exception as e:
            await send_error(f"Subscription failed: {str(e)}", code=1011)
            return

        key = (option_sid, mode)

        # wait until feed_manager initializes subscriber bucket
        for _ in range(10):
            if key in SUBSCRIBERS:
                break
            await asyncio.sleep(0.2)

        if key not in SUBSCRIBERS:
            await send_error("Subscription not initialized in feed manager", code=1011)
            return

        # -----------------------------
        # 🔗 STEP 3: Attach WebSocket
        # -----------------------------
        await ws.accept()

        # ✅ Send initial success payload
        await ws.send_json({
            "status": "connected",
            "security_id": option_sid,
            "strike": strike,
            "type": opt_type.upper(),
            "mode": mode
        })

        loop = asyncio.get_running_loop()

        def sender(message):
            try:
                asyncio.run_coroutine_threadsafe(
                    ws.send_json({
                        "status": "data",
                        "payload": message
                    }),
                    loop,
                )
            except Exception as e:
                log(f"WS send error: {e}", "ERROR")

        SUBSCRIBERS[key].add(sender)

        try:
            while True:
                await ws.receive_text()

        except WebSocketDisconnect:
            SUBSCRIBERS[key].discard(sender)
            log(f"WS disconnected → {option_sid} {mode}")

    except Exception as e:
        log(f"Dynamic WS error: {e}", "ERROR")
        try:
            await send_error(f"Internal server error: {str(e)}", code=1011)
        except:
            pass


# -------------------------------------------------
# ➕ SUBSCRIBE API
# -------------------------------------------------
@app.post("/subscribe")
async def subscribe(data: dict):
    try:
        from feed_manager import add_instruments

        symbols = [tuple(x) for x in data.get("symbols", [])]
        log(f"Subscribe API called → {symbols}")

        return add_instruments(symbols)

    except Exception as e:
        log(f"Subscribe API error: {e}", "ERROR")
        return {"status": "error", "message": str(e)}


# -------------------------------------------------
# ➖ UNSUBSCRIBE API
# -------------------------------------------------
@app.post("/unsubscribe")
async def unsubscribe(data: dict):
    try:
        from feed_manager import remove_instruments

        raw_symbols = data.get("symbols", [])

        # ✅ FIX: convert list → tuple
        symbols = [tuple(x) for x in raw_symbols]

        log(f"Unsubscribe API called → {symbols}")

        return remove_instruments(symbols)

    except Exception as e:
        log(f"Unsubscribe API error: {e}", "ERROR")
        return {"status": "error", "message": str(e)}

# -------------------------------------------------
# 📄 SUBSCRIPTIONS
# -------------------------------------------------
@app.get("/subscriptions")
def subscriptions():
    try:

        log("Fetch subscriptions called")
        return get_current_instruments()

    except Exception as e:
        log(f"Subscriptions API error: {e}", "ERROR")
        return {"status": "error", "message": str(e)}
    


@app.get("/ui", response_class=HTMLResponse)
def ui(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request
        }
    )