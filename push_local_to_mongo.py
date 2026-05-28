"""
push_local_to_mongo.py — One-time script to push existing local JSON files
from artifacts/daily_reddit/ to MongoDB collection reddit_travel_posts.

Usage:
    python insights/push_local_to_mongo.py

Requirements:
    - MONGO_URI in .env
    - MONGO_DB_NAME in .env
"""

import json
import logging
from pathlib import Path

from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
COLLECTION = "reddit_posts_final"
DATA_DIR = Path("artifacts/daily_reddit")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("push_local_to_mongo")


def test_mongo() -> bool:
    if not MONGO_URI:
        log.error("MONGO_URI not set in .env")
        return False
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        client.close()
        log.info("MongoDB connection OK ✓")
        return True
    except Exception as e:
        log.error(f"MongoDB connection failed: {e}")
        return False


def push_file(path: Path, db) -> int:
    with open(path, "r", encoding="utf-8") as f:
        docs = json.load(f)

    if not docs:
        log.warning(f"{path.name}: empty file, skipping")
        return 0

    operations = [
        UpdateOne(
            {"doc_id": doc["doc_id"]},
            {"$setOnInsert": doc},
            upsert=True
        )
        for doc in docs
    ]

    result = db[COLLECTION].bulk_write(operations)
    inserted = result.upserted_count
    skipped = len(docs) - inserted
    log.info(f"{path.name}: {inserted} new inserted, {skipped} already existed")
    return inserted


def main():
    log.info("=" * 60)
    log.info("PUSH LOCAL JSON FILES TO MONGODB")
    log.info(f"Source:     {DATA_DIR}")
    log.info(f"Collection: {COLLECTION}")
    log.info("=" * 60)

    if not test_mongo():
        log.error("Aborting — fix MongoDB connection first")
        return

    json_files = sorted(DATA_DIR.glob("rtravel_*.json"))

    if not json_files:
        log.error(f"No JSON files found in {DATA_DIR}")
        return

    log.info(f"Found {len(json_files)} files to push")

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    total_inserted = 0
    for f in json_files:
        total_inserted += push_file(f, db)

    client.close()

    log.info("=" * 60)
    log.info(f"DONE — {total_inserted} new documents inserted into '{COLLECTION}'")
    log.info("=" * 60)


if __name__ == "__main__":
    main()