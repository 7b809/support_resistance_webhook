from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import asyncio, os

from config import load_keys, is_token_valid
from authentication import generate_access_token
from telegram_bot import start_telegram_bot


from feed_manager import (
    ALLOWED_SECURITIES,
    SUBSCRIBERS,
    start_feed_thread,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

templates = Jinja2Templates(directory="templates")

# -------------------------------------------------
# LIFESPAN
# -------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):

    # ✅ Start Telegram bot ALWAYS
    start_telegram_bot()

    if is_token_valid():
        print("✅ Token valid. Starting feed...")
        start_feed_thread()
    else:
        print("⚠️ Waiting for TOTP from Telegram...")

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
    public_paths = ["/", "/token", "/generate-token", "/favicon.ico"]
    if request.url.path not in public_paths:
        if not is_token_valid():
            return HTMLResponse(
                content="❌ Token not available. Send TOTP via Telegram.",
                status_code=401
            )
    response = await call_next(request)
    return response


# -------------------------------------------------
# TOKEN PAGE
# -------------------------------------------------
@app.get("/token", response_class=HTMLResponse)
def token_page(request: Request):
    return templates.TemplateResponse("token.html", {"request": request})


# -------------------------------------------------
# GENERATE TOKEN
# -------------------------------------------------
@app.post("/generate-token")
def generate_token(totp: str = Form(...)):
    result = generate_access_token(totp)

    if result["status"] == "error":
        return HTMLResponse(
            content=f"<h3 style='color:red'>Error: {result['message']}</h3>",
            status_code=400
        )

    print("🔁 Token refreshed.")

    return RedirectResponse(url="/", status_code=303)


# -------------------------------------------------
# HOME (REPLACED DASHBOARD)
# -------------------------------------------------
@app.get("/")
def home():
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


# -------------------------------------------------
# INFO
# -------------------------------------------------
@app.get("/info")
def info():
    return {
        "available_securities": list(ALLOWED_SECURITIES.keys()),
        "available_websockets": [
            f"/ws/{sid}/{mode}"
            for sid in ALLOWED_SECURITIES
            for mode in ("ticker", "quote")
        ],
    }


# -------------------------------------------------
# WEBSOCKET
# -------------------------------------------------
@app.websocket("/ws/{security_id}/{mode}")
async def websocket_handler(ws: WebSocket, security_id: str, mode: str):

    if not is_token_valid():
        await ws.close(code=1008)
        return

    if security_id not in ALLOWED_SECURITIES or mode not in ("ticker", "quote"):
        await ws.close(code=1008)
        return

    await ws.accept()

    loop = asyncio.get_running_loop()

    def sender(message):
        asyncio.run_coroutine_threadsafe(
            ws.send_json(message),
            loop,
        )

    key = (security_id, mode)
    SUBSCRIBERS[key].add(sender)

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        SUBSCRIBERS[key].remove(sender) 