from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

def parse_alert(raw_text: str):
    return {
        "message": raw_text.strip(),
        "created_at": datetime.now(IST)
    }
