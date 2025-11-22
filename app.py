from flask import Flask, render_template, request
from pymongo import MongoClient
import requests
from datetime import datetime, timedelta

FREQUENCIES = {
    "5m":  {"granularity": 300,   "window_minutes": 5},
    "15m": {"granularity": 900,   "window_minutes": 15},
    "1h":  {"granularity": 3600,  "window_minutes": 60},
    "6h":  {"granularity": 21600, "window_minutes": 360},
    "1d":  {"granularity": 86400, "window_minutes": 1440},
}

# ---------- Config ----------
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "CoinBase"
COLLECTION_NAME = "products"

COINBASE_STATS_URL = "https://api.exchange.coinbase.com/products/{product_id}/stats"
COINBASE_CANDLES_URL = "https://api.exchange.coinbase.com/products/{product_id}/candles"

app = Flask(__name__)

def fetch_stats(product_id, frequency="1d"):
    """
    Get open/last and % change for the given frequency using Coinbase candles.

    frequency: one of ["5m", "15m", "1h", "6h", "1d"]
    """
    config = FREQUENCIES.get(frequency)
    if not config:
        return None

    granularity = config["granularity"]
    window_minutes = config["window_minutes"]

    end = datetime.utcnow()
    start = end - timedelta(minutes=window_minutes)

    params = {
        "granularity": granularity,
        "start": start.isoformat() + "Z",
        "end": end.isoformat() + "Z",
    }

    url = COINBASE_CANDLES_URL.format(product_id=product_id)

    try:
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code != 200:
            return None

        candles = resp.json()
        if not candles:
            return None

        # La API devuelve las velas más recientes primero.
        latest = candles[0]
        oldest = candles[-1]

        # Formato: [time, low, high, open, close, volume]
        open_price = float(oldest[3])
        last_price = float(latest[4])

        if open_price <= 0:
            return None

        change_pct = (last_price - open_price) / open_price * 100.0

        return {
            "open": open_price,
            "last": last_price,
            "change_pct": change_pct,
        }
    except Exception:
        return None

def get_collection():
    """Return MongoDB collection for products."""
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    return db[COLLECTION_NAME]


def get_distinct_quote_currencies():
    """Get distinct quote_currency values from products collection."""
    col = get_collection()
    quotes = col.distinct("quote_currency")
    # Orden alfabético, por comodidad
    quotes = sorted([q for q in quotes if q is not None])
    return quotes


def fetch_24h_stats(product_id):
    """
    Call Coinbase /stats endpoint for a given product.

    Returns:
        dict with 'open', 'last', 'change_pct' or None if error.
    """
    url = COINBASE_STATS_URL.format(product_id=product_id)
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            return None

        data = resp.json()

        open_price = float(data.get("open", 0) or 0)
        last_price = float(data.get("last", 0) or 0)

        if open_price <= 0:
            return None

        change_pct = (last_price - open_price) / open_price * 100.0

        return {
            "open": open_price,
            "last": last_price,
            "change_pct": change_pct,
        }
    except Exception:
        return None

def get_top_movers(quote_currency, limit=10, max_products=80,
                   movement_filter="all", frequency="1d"):
    """
    Get top 'limit' products with biggest movement for a given quote_currency.

    movement_filter:
        - "all"       -> sort by absolute change
        - "positive"  -> only positive movers
        - "negative"  -> only negative movers

    frequency:
        - "5m", "15m", "1h", "6h", "1d"
    """
    col = get_collection()

    query = {"quote_currency": quote_currency}
    products_cursor = col.find(query).limit(max_products)

    movers = []

    for p in products_cursor:
        product_id = p.get("product_id") or p.get("id")
        if not product_id:
            continue

        stats = fetch_stats(product_id, frequency=frequency)
        if not stats:
            continue

        movers.append({
            "product_id": product_id,
            "display_name": p.get("display_name", product_id),
            "base_currency": p.get("base_currency"),
            "quote_currency": p.get("quote_currency"),
            "open": stats["open"],
            "last": stats["last"],
            "change_pct": stats["change_pct"],
        })

    # Filtro según tipo de movimiento
    if movement_filter == "positive":
        movers = [m for m in movers if m["change_pct"] > 0]
        movers.sort(key=lambda x: x["change_pct"], reverse=True)
    elif movement_filter == "negative":
        movers = [m for m in movers if m["change_pct"] < 0]
        movers.sort(key=lambda x: x["change_pct"])  # más negativo primero
    else:
        movers.sort(key=lambda x: abs(x["change_pct"]), reverse=True)

    return movers[:limit]

@app.route("/", methods=["GET", "POST"])
def index():
    quotes = get_distinct_quote_currencies()
    selected_quote = None
    top_n = 10
    movement_filter = "all"
    frequency = "1d"  # default 1 day
    results = []
    error = None

    if request.method == "POST":
        selected_quote = request.form.get("quote_currency")
        top_n_str = request.form.get("top_n", "10")
        movement_filter = request.form.get("movement_filter", "all")
        frequency = request.form.get("frequency", "1d")

        try:
            top_n = int(top_n_str)
            if top_n <= 0:
                top_n = 10
        except ValueError:
            top_n = 10

        if not selected_quote:
            error = "Please select a quote currency."
        else:
            results = get_top_movers(
                selected_quote,
                limit=top_n,
                movement_filter=movement_filter,
                frequency=frequency,
            )

    return render_template(
        "index.html",
        quotes=quotes,
        selected_quote=selected_quote,
        top_n=top_n,
        movement_filter=movement_filter,
        frequency=frequency,  # nuevo
        results=results,
        error=error,
        now=datetime.utcnow(),
    )


if __name__ == "__main__":
    # Para desarrollo; en producción usar gunicorn/uWSGI
    app.run(host="0.0.0.0", port=5001, debug=True)

