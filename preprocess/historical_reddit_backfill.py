"""
historical_reddit_backfill.py — One-time script to fetch bulk Reddit posts
for all 8 cities and store in BOTH:
  1. Local JSON file (artifacts/historical/reddit_backfill.json) — backup
  2. MongoDB raw_documents_historical collection

This means even if MongoDB fails, your data is safe locally.

Usage:
    python historical_reddit_backfill.py

Requirements:
    - APIFY_TOKEN in .env
    - MONGO_URI in .env
    - MONGO_DB_NAME in .env
"""

import os
import json
import time
import hashlib
import logging
from datetime import datetime, timezone
from collections import Counter
from pathlib import Path

import requests
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

load_dotenv()

APIFY_TOKEN = os.getenv("APIFY_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
HISTORICAL_COLLECTION = "raw_documents_historical"

# Local backup directory
BACKUP_DIR = Path("artifacts/historical")

CITIES = [
    "Paris", "Rome", "Barcelona", "Lisbon",
    "Amsterdam", "Prague", "Athens", "London"
]

# Balanced allocation — more posts for cities with less existing data
CITY_MAX_ITEMS = {
    "Paris": 75,
    "Rome": 100,
    "Barcelona": 100,
    "Lisbon": 150,
    "Amsterdam": 150,
    "Prague": 75,
    "Athens": 75,
    "London": 100,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("historical_backfill")


def make_doc_id(source: str, url: str) -> str:
    return hashlib.sha256(f"{source}:{url}".encode()).hexdigest()[:16]


def test_mongodb_connection() -> bool:
    """Test MongoDB connection BEFORE spending any Apify credits."""
    if not MONGO_URI:
        log.error("[MongoDB] MONGO_URI not set in .env")
        return False
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        client.close()
        log.info("[MongoDB] Connection test passed ✓")
        return True
    except Exception as e:
        log.error(f"[MongoDB] Connection FAILED: {e}")
        log.error("[MongoDB] Fix your IP whitelist in Atlas before running this script")
        log.error("[MongoDB] Go to: mongodb.com/atlas → Network Access → Add 0.0.0.0/0")
        return False


def save_local_backup(all_docs: list):
    """Save all fetched documents to a local JSON file as backup."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"reddit_backfill_{timestamp}.json"

    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(all_docs, f, indent=2, ensure_ascii=False)

    log.info(f"[Backup] Saved {len(all_docs)} documents locally → {backup_path}")
    return backup_path


def load_from_backup(backup_path: str) -> list:
    """Load documents from a local backup file to retry MongoDB save."""
    with open(backup_path, encoding="utf-8") as f:
        docs = json.load(f)
    log.info(f"[Backup] Loaded {len(docs)} documents from {backup_path}")
    return docs


def fetch_reddit_for_city(city: str) -> list:
    """Fetch bulk Reddit posts for a city."""
    if not APIFY_TOKEN:
        log.error("No APIFY_TOKEN set — cannot fetch from Apify")
        return []

    log.info(f"[{city}] Starting Apify bulk fetch...")

    try:
        response = requests.post(
            f"https://api.apify.com/v2/acts/trudax~reddit-scraper-lite/runs?token={APIFY_TOKEN}",
            json={
                "searches": [
                    f"{city} travel",
                    f"visit {city}",
                    f"{city} tourism",
                    f"{city} trip",
                    f"{city} holiday",
                    f"{city} vacation"
                ],
                "searchPosts": True,
                "searchComments": False,
                "maxItems": CITY_MAX_ITEMS.get(city, 100),
                "sort": "new"
            },
            timeout=30
        )

        run_data = response.json()
        apify_run_id = run_data.get("data", {}).get("id")

        if not apify_run_id:
            log.warning(f"[{city}] Could not start Apify run: {run_data}")
            return []

        log.info(f"[{city}] Waiting for Apify run {apify_run_id}...")
        succeeded = False
        for attempt in range(90):
            time.sleep(3)
            status_resp = requests.get(
                f"https://api.apify.com/v2/actor-runs/{apify_run_id}?token={APIFY_TOKEN}",
                timeout=10
            )
            status = status_resp.json().get("data", {}).get("status", "")
            if status == "SUCCEEDED":
                succeeded = True
                break
            elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
                log.warning(f"[{city}] Run {status}")
                break
            if attempt % 10 == 0:
                log.info(f"[{city}] Still waiting... status={status}")

        if not succeeded:
            log.warning(f"[{city}] Run did not succeed — skipping")
            return []

        items_resp = requests.get(
            f"https://api.apify.com/v2/actor-runs/{apify_run_id}/dataset/items?token={APIFY_TOKEN}",
            timeout=30
        )
        items = items_resp.json()

        if not isinstance(items, list):
            log.warning(f"[{city}] Unexpected response format")
            return []

        docs = []
        for item in items:
            url = item.get("url", "") or item.get("id", "") or ""
            title = item.get("title", "") or ""
            text = item.get("body", "") or item.get("selftext", "") or title
            created_at = item.get("createdAt", "") or item.get("created", "") or ""

            docs.append({
                "doc_id": make_doc_id("reddit_historical", url),
                "source": "reddit",
                "city": city,
                "title": title,
                "text": text,
                "published_at": created_at,
                "url": url,
                "ingestion_time": datetime.now(timezone.utc).isoformat(),
                "run_id": "historical_bulk_backfill",
                "is_historical": True
            })

        log.info(f"[{city}] Got {len(docs)} posts")
        return docs

    except Exception as e:
        log.error(f"[{city}] Error: {e}")
        return []


def save_to_mongo(all_docs: list) -> bool:
    """Save all historical documents to MongoDB. Returns True if successful."""
    if not all_docs:
        log.warning("No documents to save")
        return False

    if not MONGO_URI:
        log.error("MONGO_URI missing")
        return False

    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
        db = client[DB_NAME]

        operations = [
            UpdateOne(
                {"doc_id": doc["doc_id"]},
                {"$setOnInsert": doc},
                upsert=True
            )
            for doc in all_docs
        ]

        result = db[HISTORICAL_COLLECTION].bulk_write(operations)
        inserted = result.upserted_count
        skipped = len(all_docs) - inserted

        log.info(
            f"[MongoDB] Saved to '{HISTORICAL_COLLECTION}': "
            f"{inserted} new inserted, {skipped} already existed"
        )

        db["pipeline_artifacts"].insert_one({
            "run_id": "historical_bulk_backfill",
            "artifact_type": "historical_reddit_backfill",
            "timestamp": datetime.now(timezone.utc),
            "document_count": len(all_docs),
            "cities": CITIES
        })

        client.close()
        return True

    except Exception as e:
        log.error(f"[MongoDB] Failed to save: {e}")
        return False


def main():
    log.info("=" * 60)
    log.info("HISTORICAL REDDIT BULK BACKFILL")
    log.info(f"Cities: {', '.join(CITIES)}")
    log.info(f"Max posts per city: 175")
    log.info(f"Collection: {HISTORICAL_COLLECTION}")
    log.info("=" * 60)

    # ── STEP 1: Test MongoDB BEFORE spending Apify credits ────────────────────
    log.info("\n[Pre-flight] Testing MongoDB connection...")
    if not test_mongodb_connection():
        log.error("Aborting — fix MongoDB connection first, then re-run")
        log.error("No Apify credits were spent")
        return

    if not APIFY_TOKEN:
        log.error("APIFY_TOKEN not set in .env — cannot continue")
        return

    # ── STEP 2: Fetch from Apify ──────────────────────────────────────────────
    all_docs = []

    for i, city in enumerate(CITIES):
        log.info(f"\n[{i+1}/{len(CITIES)}] Fetching {city}...")
        city_docs = fetch_reddit_for_city(city)
        all_docs.extend(city_docs)

        # Save city backup immediately after each city
        # So if it crashes mid-way you still have what was fetched so far
        city_backup_path = BACKUP_DIR / f"reddit_{city.lower()}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        with open(city_backup_path, "w", encoding="utf-8") as f:
            json.dump(city_docs, f, indent=2, ensure_ascii=False)
        log.info(f"[Backup] {city} saved locally → {city_backup_path}")

        log.info(f"[{i+1}/{len(CITIES)}] {city} complete — {len(city_docs)} posts")

        if i < len(CITIES) - 1:
            log.info("Waiting 5 seconds before next city...")
            time.sleep(5)

    log.info(f"\n{'='*60}")
    log.info(f"Total documents fetched: {len(all_docs)}")

    # ── STEP 3: Save full backup locally ─────────────────────────────────────
    backup_path = save_local_backup(all_docs)
    log.info(f"[Backup] Full backup saved — data is safe even if MongoDB fails")

    # ── STEP 4: Save to MongoDB ───────────────────────────────────────────────
    mongo_success = save_to_mongo(all_docs)

    if not mongo_success:
        log.error("=" * 60)
        log.error("MongoDB save FAILED but your data is safe locally!")
        log.error(f"Backup file: {backup_path}")
        log.error("Fix MongoDB connection and run:")
        log.error(f"  python historical_reddit_backfill.py --from-backup {backup_path}")
        log.error("=" * 60)
    else:
        # Summary
        city_counts = Counter(doc["city"] for doc in all_docs)
        log.info("\nSummary by city:")
        for city in CITIES:
            log.info(f"  {city:12} {city_counts.get(city, 0)} posts")

        log.info("=" * 60)
        log.info("BACKFILL COMPLETE")
        log.info(f"Data saved to MongoDB: {HISTORICAL_COLLECTION}")
        log.info(f"Local backup: {backup_path}")
        log.info("=" * 60)


def retry_from_backup(backup_path: str):
    """Retry saving to MongoDB from a local backup file."""
    log.info(f"[Retry] Loading from backup: {backup_path}")

    if not test_mongodb_connection():
        log.error("MongoDB still not reachable — fix IP whitelist first")
        return

    all_docs = load_from_backup(backup_path)
    success = save_to_mongo(all_docs)

    if success:
        log.info("Retry successful — all documents saved to MongoDB")
    else:
        log.error("Retry failed — check MongoDB connection")


if __name__ == "__main__":
    import sys

    # Allow retrying from backup: python historical_reddit_backfill.py --from-backup path/to/file.json
    if "--from-backup" in sys.argv:
        idx = sys.argv.index("--from-backup")
        if idx + 1 < len(sys.argv):
            retry_from_backup(sys.argv[idx + 1])
        else:
            log.error("Please provide backup file path: --from-backup path/to/file.json")
    else:
        main()