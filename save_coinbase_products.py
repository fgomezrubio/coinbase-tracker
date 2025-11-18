import requests
from pymongo import MongoClient, errors
from datetime import datetime

# -------- Configuration --------
COINBASE_URL = "https://api.exchange.coinbase.com/products"

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "CoinBase"            # Database name requested
COLLECTION_NAME = "products"


def fetch_products():
    """Fetch all available products from the public Coinbase API."""
    print("🔍 Fetching products from Coinbase public API...")

    resp = requests.get(COINBASE_URL, timeout=10)
    resp.raise_for_status()

    products = resp.json()
    print(f"✔ Products received: {len(products)}")
    return products


def connect_mongo():
    """Connect to MongoDB and return the collection."""
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    # Create unique index to avoid duplicates
    try:
        collection.create_index("product_id", unique=True)
    except errors.OperationFailure as e:
        print("⚠ Warning (index may already exist):", e)

    return collection


def save_products_to_mongo(products, collection):
    """Insert or update products in MongoDB using upsert."""
    inserted = 0
    updated = 0

    for p in products:
        product_id = p.get("id")

        document = {
            "product_id": product_id,
            "base_currency": p.get("base_currency"),
            "quote_currency": p.get("quote_currency"),
            "base_min_size": p.get("base_min_size"),
            "base_max_size": p.get("base_max_size"),
            "quote_increment": p.get("quote_increment"),
            "display_name": p.get("display_name"),
            "status": p.get("status"),
            "raw": p,  # full JSON for future use
            "updated_at": datetime.utcnow(),
        }

        result = collection.update_one(
            {"product_id": product_id},
            {
                "$set": document,
                "$setOnInsert": {"created_at": datetime.utcnow()},
            },
            upsert=True,
        )

        if result.matched_count == 0:
            inserted += 1
        else:
            updated += 1

    print(f"📥 Inserted new: {inserted}")
    print(f"♻ Updated: {updated}")


def main():
    try:
        products = fetch_products()
        collection = connect_mongo()
        save_products_to_mongo(products, collection)
        print("✅ Process completed successfully.")

    except requests.exceptions.RequestException as e:
        print("❌ Error calling Coinbase API:", e)

    except errors.PyMongoError as e:
        print("❌ MongoDB error:", e)

    except Exception as e:
        print("❌ Unexpected error:", e)


if __name__ == "__main__":
    main()

