from flask import Flask, render_template, request
from routes import routes
from db import db
from datetime import datetime
import pytz

app = Flask(__name__)

app.register_blueprint(routes)

# IST timezone
IST = pytz.timezone("Asia/Kolkata")


@app.route("/")
def dashboard():
    # Get params
    collection_name = request.args.get("collection", "nifty")
    limit_param = request.args.get("limit", "100")

    # Safe limit handling
    try:
        limit = int(limit_param)
    except:
        limit = 100

    # Get collections
    collections = db.list_collection_names()

    if collection_name not in collections:
        collection_name = collections[0] if collections else "nifty"

    # Fetch data
    data = list(
        db[collection_name]
        .find()
        .sort("created_at", -1)
        .limit(limit)
    )

    # Process data
    for i, item in enumerate(data, start=1):
        item["serial"] = i

        # ✅ Format time to readable IST
        if "created_at" in item and isinstance(item["created_at"], datetime):
            try:
                item["formatted_time"] = item["created_at"].astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")
            except:
                item["formatted_time"] = str(item["created_at"])
        else:
            item["formatted_time"] = "N/A"

        # ✅ Fallbacks (in case missing fields)
        item["symbol"] = item.get("symbol", "N/A")
        item["webhook"] = item.get("webhook", "N/A")

    return render_template(
        "index.html",
        data=data,
        collections=collections,
        selected_collection=collection_name,
        limit=limit
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)