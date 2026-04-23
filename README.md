# 📡 Dhan Market Feed API (FastAPI)

A real-time market data system built using **FastAPI + Dhan WebSocket Feed**, supporting:

- 🔄 Dynamic subscription/unsubscription
- 📊 Real-time streaming via WebSocket
- 🤖 Telegram-based authentication (TOTP)
- ⚡ Live market data (Ticker / Quote / Depth / Full)

---

# 🚀 Getting Started

## Install dependencies
pip install -r requirements.txt

## Run the server
uvicorn app:app --host 0.0.0.0 --port 8000

---

# 📌 API Endpoints

## ➕ Subscribe
POST /subscribe

{
  "symbols": [
    [2, "72216", 17]
  ]
}

## ➖ Unsubscribe
POST /unsubscribe

{
  "symbols": [
    [2, "72216", 17]
  ]
}

## 📄 Get Subscriptions
GET /subscriptions

---

# 📊 WebSocket

ws://localhost:8000/ws/{security_id}/{mode}

Example:
ws://localhost:8000/ws/72216/quote

---

# 🧠 Instrument Format

(exchange_segment, security_id, request_type)

---

# 🏦 Exchange Segment Constants

IDX = 0
NSE = 1
NSE_FNO = 2
NSE_CURR = 3
BSE = 4
MCX = 5
BSE_CURR = 7
BSE_FNO = 8

---

# 📡 Feed Type Constants

Ticker = 15
Quote = 17
Depth = 19
Full = 21

---

# 🧪 Sample Test Cases

## NIFTY Index
[0, "13", 17]

## NIFTY Option
[2, "72216", 17]

---

# ⚠️ Notes

- Market hours: 9:15 AM – 3:30 PM IST
- No data outside market hours
- WebSocket required for live data

---

# 🔥 Features

- Real-time streaming
- Dynamic subscriptions
- WebSocket delivery
