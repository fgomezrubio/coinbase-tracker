from flask import Flask, render_template, request
from pymongo import MongoClient
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import time  # <-- agrega esto

RSI_CACHE = {}  # key -> {"ts": epoch, "payload": dict}
RSI_CACHE_TTL = 10  # seconds

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

def fetch_closes(product_id, frequency="15m", periods=100):
    """
    Fetch closing prices from Coinbase candles for RSI/EMA/etc.

    - frequency: "5m", "15m", "1h", "6h", "1d"
    - periods: how many candles back we want (approx; based on time window)
    Returns: list[float] closes sorted from oldest -> latest, or None
    """
    config = FREQUENCIES.get(frequency)
    if not config:
        return None

    granularity = config["granularity"]

    end = datetime.utcnow()
    # pedimos una ventana suficientemente grande para obtener 'periods' velas
    start = end - timedelta(seconds=granularity * periods)

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

        # Coinbase devuelve más reciente primero, lo invertimos
        candles = list(reversed(candles))

        closes = []
        for c in candles:
            # Formato: [time, low, high, open, close, volume]
            closes.append(float(c[4]))

        return closes
    except Exception:
        return None

def compute_rsi(closes, period=14):
    """
    RSI with Wilder smoothing.
    closes: list of floats ordered oldest -> latest
    Returns: float RSI or None
    """
    if not closes or len(closes) < period + 1:
        return None

    # Cambios entre closes
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    # Promedios iniciales (simple) para los primeros 'period'
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Wilder smoothing para el resto
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0  # sin pérdidas -> RSI máximo

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi

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

def _compute_mover_for_product(p, frequency):
    """
    Helper para obtener stats de un producto.
    Retorna el diccionario listo para movers[], o None si falla.
    """
    product_id = p.get("product_id") or p.get("id")
    if not product_id:
        return None

    stats = fetch_stats(product_id, frequency=frequency)
    if not stats:
        return None

    return {
        "product_id": product_id,
        "display_name": p.get("display_name", product_id),
        "base_currency": p.get("base_currency"),
        "quote_currency": p.get("quote_currency"),
        "open": stats["open"],
        "last": stats["last"],
        "change_pct": stats["change_pct"],
    }

def get_top_movers(quote_currency, limit=10, max_products=80,
                   movement_filter="all", frequency="1d",
                   max_workers=8):
    """
    Get top 'limit' products with biggest movement for a given quote_currency.

    movement_filter:
        - "all"       -> sort by absolute change
        - "positive"  -> only positive movers
        - "negative"  -> only negative movers

    frequency:
        - "5m", "15m", "1h", "6h", "1d"

    max_workers:
        - número de hilos en el pool para llamadas HTTP concurrentes
    """
    col = get_collection()
    query = {"quote_currency": quote_currency}

    # leemos los productos en memoria para poder iterar con threads
    products = list(col.find(query).limit(max_products))

    movers = []

    # Pool de threads para hacer requests en paralelo
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_compute_mover_for_product, p, frequency)
            for p in products
        ]

        for fut in as_completed(futures):
            try:
                result = fut.result()
                if result:
                    movers.append(result)
            except Exception as e:
                # si alguna llamada truena, no queremos que rompa toda la página
                print(f"Error computing mover: {e}")

    # Filtro según tipo de movimiento (igual que antes)
    if movement_filter == "positive":
        movers = [m for m in movers if m["change_pct"] > 0]
        movers.sort(key=lambda x: x["change_pct"], reverse=True)
    elif movement_filter == "negative":
        movers = [m for m in movers if m["change_pct"] < 0]
        movers.sort(key=lambda x: x["change_pct"])
    else:
        movers.sort(key=lambda x: abs(x["change_pct"]), reverse=True)

    return movers[:limit]

def get_online_products_by_quote(quote_currency):
    """
    Return all products with given quote_currency and status='online'
    from MongoDB (no limit).
    """
    col = get_collection()
    query = {
        "quote_currency": quote_currency,
        "status": "online"
    }

    cursor = col.find(query).sort("base_currency", 1)

    products = []
    for p in cursor:
        product_id = p.get("product_id") or p.get("id")
        if not product_id:
            continue
        products.append({
            "product_id": product_id,
            "display_name": p.get("display_name") or f"{p.get('base_currency')}-{p.get('quote_currency')}",
            "base_currency": p.get("base_currency"),
            "quote_currency": p.get("quote_currency"),
            "status": p.get("status"),
        })
    return products

@app.route("/api/price/<product_id>")
def api_price(product_id):
    stats = fetch_stats(product_id, frequency="5m")  # se usa la función que ya tienes
    if not stats:
        return {"error": "No data"}, 404
    
    return {
        "product_id": product_id,
        "last_price": stats["last"],
        "time_utc": datetime.utcnow().isoformat() + "Z"
    }
    
@app.route("/api/rsi/<product_id>")
def api_rsi(product_id):
    # defaults
    frequency = request.args.get("frequency", "15m")
    period_str = request.args.get("period", "14")

    try:
        period = int(period_str)
        if period <= 1:
            period = 14
    except ValueError:
        period = 14

    # cache (ya con frequency/period definidos)
    cache_key = f"{product_id}:{frequency}:{period}"
    now = time.time()

    cached = RSI_CACHE.get(cache_key)
    if cached and (now - cached["ts"] < RSI_CACHE_TTL):
        return cached["payload"]

    periods = max(100, period * 10)
    closes = fetch_closes(product_id, frequency=frequency, periods=periods)

    if not closes:
        return {"error": "No candles"}, 404

    rsi = compute_rsi(closes, period=period)
    if rsi is None:
        return {"error": "Not enough data"}, 404

    payload = {
        "product_id": product_id,
        "frequency": frequency,
        "period": period,
        "rsi": round(rsi, 2),
        "time_utc": datetime.utcnow().isoformat() + "Z"
    }

    RSI_CACHE[cache_key] = {"ts": now, "payload": payload}
    return payload
    
@app.route("/", methods=["GET", "POST"])
def index():
    quotes = get_distinct_quote_currencies()
    selected_quote = None
    top_n = 10
    movement_filter = "all"
    frequency = "1d"
    results = []
    error = None

    # Para la card de Available Markets
    markets_quote_currency = None
    markets_products = []

    if request.method == "POST":
        form_id = request.form.get("form_id", "top_movers")

        # -----------------------------
        # FORMULARIO 1: TOP MOVERS
        # -----------------------------
        if form_id == "top_movers":
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

        # ----------------------------------------------
        # FORMULARIO 2: AVAILABLE MARKETS (NO BORRAR TOP MOVERS)
        # ----------------------------------------------
        elif form_id == "markets":
            markets_quote_currency = request.form.get("markets_quote_currency")

            # 1) Recuperamos snapshot de Top Movers (sin recalcular)
            snapshot_str = request.form.get("top_movers_snapshot")
            if snapshot_str:
                try:
                    results = json.loads(snapshot_str)
                except json.JSONDecodeError:
                    results = []

            # 2) Recuperamos filtros de Top Movers solo para reimprimirlos
            selected_quote = request.form.get("selected_quote") or None
            top_n_str = request.form.get("top_n", "10")
            movement_filter = request.form.get("movement_filter", "all")
            frequency = request.form.get("frequency", "1d")

            try:
                top_n = int(top_n_str)
                if top_n <= 0:
                    top_n = 10
            except ValueError:
                top_n = 10

            # 3) Cargar la lista de markets para esa quote
            if not markets_quote_currency:
                error = "Please select a quote currency for markets."
            else:
                markets_products = get_online_products_by_quote(markets_quote_currency)

    print(
        "DEBUG >>>",
        "frequency:", frequency,
        "| selected_quote (TopMovers):", selected_quote,
        "| markets_quote_currency (Available):", markets_quote_currency
    )

    return render_template(
        "index.html",
        quotes=quotes,
        selected_quote=selected_quote,
        top_n=top_n,
        movement_filter=movement_filter,
        frequency=frequency,
        results=results,
        error=error,
        now=datetime.utcnow(),
        markets_quote_currency=markets_quote_currency,
        markets_products=markets_products,
    )

if __name__ == "__main__":
    # Para desarrollo; en producción usar gunicorn/uWSGI
    app.run(host="0.0.0.0", port=5001, debug=True)

