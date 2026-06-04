"""
check_post_dates.py — Aggregates and counts documents in reddit_posts_final by publication date.

Usage:
    python check_post_dates.py
"""

import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(override=True)

# ==========================================
# Configuration
# ==========================================
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
COLLECTION_NAME = "reddit_posts_final"

def main():
    if not MONGO_URI:
        print("❌ MONGO_URI not found in environment variables.")
        return

    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()  # Test connection
        db = client[DB_NAME]
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        return

    print("📊 Fetching publication dates...\n")

    # The pipeline groups the data by the first 10 characters of `published_at` (YYYY-MM-DD)
    pipeline = [
        {
            # Ensure the field exists and is a string to prevent pipeline errors
            "$match": { "published_at": { "$exists": True, "$type": "string" } }
        },
        {
            # Substring extracts just the date part, ignoring the exact time/timezone
            "$group": {
                "_id": { "$substr": ["$published_at", 0, 10] },
                "document_count": { "$sum": 1 }
            }
        },
        {
            # Sort chronologically (oldest to newest)
            "$sort": { "_id": 1 }
        }
    ]

    try:
        results = list(db[COLLECTION_NAME].aggregate(pipeline))
    except Exception as e:
        print(f"⚠️ Error executing aggregation: {e}")
        return

    if not results:
        print(f"No valid 'published_at' dates found in the '{COLLECTION_NAME}' collection.")
        return

    # ==========================================
    # Render the Table
    # ==========================================
    header_str = f"{'PUBLICATION DATE'.ljust(20)} | {'DOCUMENTS (POSTS)'}"
    separator = "=" * len(header_str)

    print(separator)
    print(header_str)
    print(separator)

    total_documents = 0

    for row in results:
        # '_id' now holds the isolated YYYY-MM-DD string
        date = row.get("_id", "Unknown")
        count = row.get("document_count", 0)
        total_documents += count
        
        print(f"{date.ljust(20)} | {count}")

    print(separator)
    print(f"{'GRAND TOTAL'.ljust(20)} | {total_documents}")
    print(separator)

if __name__ == "__main__":
    main()