from flask import Flask, render_template, request
from pymongo import MongoClient
import requests
from datetime import datetime

# ---------- Config ----------
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "CoinBase"
COLLECTION_NAME = "products"

COINBASE_STATS_URL = "https://api.exchange.coinbase.com/products/{product_id}/stats"

app = Flask(__name__)


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


def get_top_movers(quote_currency, limit=10, max_products=80):
    """
    Get top 'limit' products with biggest 24h movement for a given quote_currency.

    - quote_currency: filter (e.g., 'USD', 'USDT').
    - limit: how many top movers to return.
    - max_products: max number of products to check to avoid too many API calls.
    """
    col = get_collection()

    # Filtramos por quote_currency y status "online" (si existe)
    query = {"quote_currency": quote_currency}
    # Algunos documentos tienen status en 'status'
    # Puedes ajustar según lo que tengas guardado
    # query["status"] = "online"

    products_cursor = col.find(query).limit(max_products)

    movers = []

    for p in products_cursor:
        product_id = p.get("product_id") or p.get("id")
        if not product_id:
            continue

        stats = fetch_24h_stats(product_id)
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

    # Ordenamos por movimiento absoluto (mayor cambio)
    movers.sort(key=lambda x: abs(x["change_pct"]), reverse=True)

    # Top N
    return movers[:limit]


@app.route("/", methods=["GET", "POST"])
def index():
    quotes = get_distinct_quote_currencies()
    selected_quote = None
    top_n = 10
    results = []
    error = None

    if request.method == "POST":
        selected_quote = request.form.get("quote_currency")
        top_n_str = request.form.get("top_n", "10")

        try:
            top_n = int(top_n_str)
            if top_n <= 0:
                top_n = 10
        except ValueError:
            top_n = 10

        if not selected_quote:
            error = "Please select a quote currency."
        else:
            results = get_top_movers(selected_quote, limit=top_n)

    return render_template(
        "index.html",
        quotes=quotes,
        selected_quote=selected_quote,
        top_n=top_n,
        results=results,
        error=error,
        now=datetime.utcnow(),
    )


if __name__ == "__main__":
    # Para desarrollo; en producción usar gunicorn/uWSGI
    app.run(host="0.0.0.0", port=5001, debug=True)

