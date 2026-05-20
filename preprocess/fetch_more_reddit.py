"""
fetch_more_reddit.py — Fetch additional Reddit posts for all 8 cities via Apify.

- 100 posts per city
- Uses broader search queries than the weekly pipeline
- Stores to MongoDB raw_documents_historical (same as historical backfill)
- run_id: "reddit_top_up_<date>" — safe to run multiple times without conflicts
- Does NOT score — run s02 separately after this to process for relevance

Usage:
    python preprocess/fetch_more_reddit.py

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
ARTIFACTS_COLLECTION = "pipeline_artifacts"

BACKUP_DIR = Path("artifacts/reddit_top_up")

CITIES = [
    "Paris", "Rome", "Barcelona", "Lisbon",
    "Amsterdam", "Prague", "Athens", "London"
]

# Broader search queries than the weekly pipeline (which only uses 2)
CITY_QUERIES = [
    "{city} travel",
    "visit {city}",
    "{city} tourism",
    "{city} trip",
    "{city} holiday",
    "{city} vacation",
    "{city} travel tips",
    "{city} travel guide",
]

MAX_ITEMS_PER_CITY = 100

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("fetch_more_reddit")


def make_doc_id(source: str, url: str) -> str:
    return hashlib.sha256(f"{source}:{url}".encode()).hexdigest()[:16]


def test_mongodb_connection() -> bool:
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
        log.error("[MongoDB] Check your IP whitelist in Atlas: Network Access → Add 0.0.0.0/0")
        return False


def fetch_reddit_for_city(city: str, run_id: str) -> list:
    if not APIFY_TOKEN:
        log.error("No APIFY_TOKEN set — cannot fetch from Apify")
        return []

    searches = [q.format(city=city) for q in CITY_QUERIES]
    log.info(f"[{city}] Starting Apify fetch ({MAX_ITEMS_PER_CITY} posts, {len(searches)} queries)...")

    try:
        response = requests.post(
            f"https://api.apify.com/v2/acts/trudax~reddit-scraper-lite/runs?token={APIFY_TOKEN}",
            json={
                "searches": searches,
                "searchPosts": True,
                "searchComments": True,
                "maxItems": MAX_ITEMS_PER_CITY,
                "sort": "new"
            },
            timeout=30
        )

        run_data = response.json()
        apify_run_id = run_data.get("data", {}).get("id")

        if not apify_run_id:
            log.warning(f"[{city}] Could not start Apify run: {run_data}")
            return []

        log.info(f"[{city}] Apify run started ({apify_run_id}), waiting for results...")
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
                "doc_id": make_doc_id("reddit_top_up", url),
                "source": "reddit",
                "city": city,
                "title": title,
                "text": text,
                "published_at": created_at,
                "url": url,
                "ingestion_time": datetime.now(timezone.utc).isoformat(),
                "run_id": run_id,
                "is_historical": True
            })

        log.info(f"[{city}] Got {len(docs)} posts/comments")
        return docs

    except Exception as e:
        log.error(f"[{city}] Error: {e}")
        return []


def save_city_backup(city: str, docs: list):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"reddit_{city.lower()}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2, ensure_ascii=False)
    log.info(f"[Backup] {city} saved locally → {path}")


def save_full_backup(all_docs: list) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"reddit_top_up_full_{timestamp}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(all_docs, f, indent=2, ensure_ascii=False)
    log.info(f"[Backup] Full backup saved → {path}")
    return path


def save_to_mongo(all_docs: list, run_id: str) -> bool:
    if not all_docs or not MONGO_URI:
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
        log.info(f"[MongoDB] {inserted} new inserted, {skipped} already existed → '{HISTORICAL_COLLECTION}'")

        db[ARTIFACTS_COLLECTION].insert_one({
            "run_id": run_id,
            "artifact_type": "reddit_top_up",
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
    run_id = f"reddit_top_up_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    log.info("=" * 60)
    log.info("REDDIT TOP-UP FETCH")
    log.info(f"run_id:   {run_id}")
    log.info(f"Cities:   {', '.join(CITIES)}")
    log.info(f"Per city: {MAX_ITEMS_PER_CITY} posts")
    log.info(f"Queries:  {len(CITY_QUERIES)} per city")
    log.info("=" * 60)

    # ── Pre-flight: test MongoDB before spending any Apify credits ────────────
    log.info("\n[Pre-flight] Testing MongoDB connection...")
    if not test_mongodb_connection():
        log.error("Aborting — fix MongoDB connection first (no Apify credits spent)")
        return

    if not APIFY_TOKEN:
        log.error("APIFY_TOKEN not set in .env — cannot continue")
        return

    # ── Fetch per city ────────────────────────────────────────────────────────
    all_docs = []

    for i, city in enumerate(CITIES):
        log.info(f"\n[{i+1}/{len(CITIES)}] Fetching {city}...")
        city_docs = fetch_reddit_for_city(city, run_id)
        all_docs.extend(city_docs)
        save_city_backup(city, city_docs)

        if i < len(CITIES) - 1:
            log.info("Waiting 5 seconds before next city...")
            time.sleep(5)

    log.info(f"\n{'='*60}")
    log.info(f"Total documents fetched: {len(all_docs)}")

    # ── Save full local backup (safe even if MongoDB fails) ───────────────────
    backup_path = save_full_backup(all_docs)

    # ── Save to MongoDB ───────────────────────────────────────────────────────
    mongo_success = save_to_mongo(all_docs, run_id)

    if not mongo_success:
        log.error("=" * 60)
        log.error("MongoDB save FAILED — but data is safe locally!")
        log.error(f"Backup: {backup_path}")
        log.error("=" * 60)
    else:
        city_counts = Counter(doc["city"] for doc in all_docs)
        log.info("\nSummary by city:")
        for city in CITIES:
            log.info(f"  {city:12} {city_counts.get(city, 0)} posts")

        log.info("=" * 60)
        log.info("TOP-UP COMPLETE")
        log.info(f"run_id: {run_id}")
        log.info(f"Next step: run s02_store_relevant_docs.py with run_id='{run_id}'")
        log.info("=" * 60)


if __name__ == "__main__":
    main()