from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import asyncio, os
from datetime import datetime

from config import load_keys, is_token_valid
from authentication import generate_access_token
from telegram_bot import start_telegram_bot

from feed_manager import (
    ALLOWED_SECURITIES,
    SUBSCRIBERS,
    start_feed_thread,
    get_current_instruments
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory="templates")


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
    try:
        log("Starting Telegram bot...")
        start_telegram_bot()
    except Exception as e:
        log(f"Telegram bot start error: {e}", "ERROR")

    try:
        if is_token_valid():
            log("Token valid → starting feed")
            start_feed_thread()
        else:
            log("Waiting for TOTP from Telegram...", "WARN")
    except Exception as e:
        log(f"Feed start error: {e}", "ERROR")

    yield


app = FastAPI(
    title="Dhan Market Dashboard",
    lifespan=lifespan,
)


# -------------------------------------------------
# MIDDLEWARE
# -------------------------------------------------
@app.middleware("http")
async def check_token_middleware(request: Request, call_next):
    try:
        public_paths = ["/", "/token", "/generate-token", "/favicon.ico"]

        if request.url.path not in public_paths:
            if not is_token_valid():
                log("Blocked request → token invalid", "WARN")
                return HTMLResponse(
                    content="❌ Token not available. Send TOTP via Telegram.",
                    status_code=401
                )

        response = await call_next(request)
        return response

    except Exception as e:
        log(f"Middleware error: {e}", "ERROR")
        return HTMLResponse(content="❌ Internal Server Error", status_code=500)


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

        return {
            "status": "running",
            "message": "Dhan Market API is live",
            "token_valid": is_token_valid(),
            "expiry_time": str(expiry) if expiry else "None",
            "available_securities": list(ALLOWED_SECURITIES.keys()),
            "websocket_example": "/ws/{security_id}/quote"
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

        if security_id not in ALLOWED_SECURITIES or mode not in ("ticker", "quote"):
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