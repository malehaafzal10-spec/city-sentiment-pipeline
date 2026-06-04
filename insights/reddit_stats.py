"""
export_reddit_stats_flat.py — Flat script to extract stats and back up the MongoDB collection.

Usage:
    python src/export_reddit_stats_flat.py

Environment variables required:
    MONGO_URI       — MongoDB connection string
    MONGO_DB_NAME   — MongoDB database name (defaults to travel_pipeline_db)
"""

import os
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient
from dotenv import load_dotenv

# ── 1. Setup & Configuration ──────────────────────────────────────────────────

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("reddit_export")

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
COLLECTION = "reddit_travel_posts"
EXPORT_DIR = Path("artifacts/exports")

if not MONGO_URI:
    log.error("MONGO_URI not set. Check your .env file.")
    exit(1)

# ── 2. Database Connection & Fetch ────────────────────────────────────────────

log.info("Connecting to MongoDB...")
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client[DB_NAME]
col = db[COLLECTION]

log.info(f"Connected. Fetching documents from {DB_NAME}.{COLLECTION}...")
# Fetch all documents, excluding the internal _id for a clean JSON export
docs = list(col.find({}, {"_id": 0}))

if not docs:
    log.warning("The collection is empty. Nothing to export or analyze.")
    client.close()
    exit(0)

# ── 3. Calculate Statistics ───────────────────────────────────────────────────

log.info("Calculating statistics...")
total_posts = len(docs)

city_counter = Counter()
country_counter = Counter()
dates = []

for doc in docs:
    # Tally locations
    locations = doc.get("locations", {})
    city_counter.update(locations.get("cities", []))
    country_counter.update(locations.get("countries", []))
    
    # Track dates
    pub_date = doc.get("published_at")
    if pub_date:
        try:
            # Parse ISO format to grab the date bounds
            dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
            dates.append(dt)
        except ValueError:
            pass

earliest_post = min(dates).isoformat() if dates else "Unknown"
latest_post = max(dates).isoformat() if dates else "Unknown"

# ── 4. Print Statistics ───────────────────────────────────────────────────────

print("\n" + "="*50)
print("📊 MONGODB DATA STATISTICS")
print("="*50)
print(f"Total Posts Stored  : {total_posts}")
print(f"Date Range          : {earliest_post} to {latest_post}")

print("\n🏙️  Top 10 Cities Mentioned:")
for city, count in city_counter.most_common(10):
    print(f"    - {city}: {count}")

print("\n🌎 Top 10 Countries Mentioned:")
for country, count in country_counter.most_common(10):
    print(f"    - {country}: {count}")
print("="*50 + "\n")

# ── 5. Save Local JSON Export ─────────────────────────────────────────────────

EXPORT_DIR.mkdir(parents=True, exist_ok=True)
timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
export_path = EXPORT_DIR / f"full_reddit_export_{timestamp}.json"

with open(export_path, "w", encoding="utf-8") as f:
    json.dump(docs, f, indent=2, ensure_ascii=False)
    
log.info(f"Successfully exported {total_posts} documents to {export_path}")

# Close the database connection
client.close()