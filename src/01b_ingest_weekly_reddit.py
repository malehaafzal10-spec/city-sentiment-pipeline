"""
01b_ingest_reddit.py — Step 1b: Fetch raw text from Reddit via Apify.
Stores resulting data and raw artifacts into MongoDB.
"""

import os
import json
import time
import hashlib
import logging
from datetime import datetime, timezone
import requests
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

DOCUMENTS_COLLECTION = "raw_documents"
ARTIFACTS_COLLECTION = "pipeline_artifacts"

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("ingest_reddit")


def load_config():
    with open("config/cities.json") as f:
        return json.load(f)

def make_doc_id(source: str, url: str) -> str:
    return hashlib.sha256(f"{source}:{url}".encode()).hexdigest()[:16]

def fetch_reddit_apify(config: dict, run_id: str) -> list:
    APIFY_TOKEN = os.getenv("APIFY_TOKEN")
    if not APIFY_TOKEN:
        log.error("[Reddit] No APIFY_TOKEN set — skipping")
        return []

    all_docs = []

    for city in config["cities"]:
        city_name = city["name"]
        log.info(f"[Reddit] Fetching posts for {city_name}")

        try:
            response = requests.post(
                f"https://api.apify.com/v2/acts/trudax~reddit-scraper-lite/runs?token={APIFY_TOKEN}",
                json={
                    "searches": [f"{city_name} travel", f"visit {city_name}"],
                    "searchPosts": True,
                    "searchComments": False,
                    "maxItems": 25,
                    "sort": "new"
                },
                timeout=30
            )

            run_data = response.json()
            apify_run_id = run_data.get("data", {}).get("id")

            if not apify_run_id:
                log.warning(f"[Reddit] Could not start run for {city_name}: {run_data}")
                continue

            log.info(f"[Reddit] Waiting for results for {city_name}...")
            succeeded = False
            for _ in range(45):
                time.sleep(2)
                status_resp = requests.get(
                    f"https://api.apify.com/v2/actor-runs/{apify_run_id}?token={APIFY_TOKEN}",
                    timeout=10
                )
                status = status_resp.json().get("data", {}).get("status", "")
                if status == "SUCCEEDED":
                    succeeded = True
                    break
                elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
                    log.warning(f"[Reddit] Run {status} for {city_name}")
                    break

            if not succeeded:
                log.warning(f"[Reddit] Skipping {city_name} — run did not succeed")
                continue

            items_resp = requests.get(
                f"https://api.apify.com/v2/actor-runs/{apify_run_id}/dataset/items?token={APIFY_TOKEN}",
                timeout=30
            )
            items = items_resp.json()

            if isinstance(items, list):
                for item in items:
                    url = item.get("url", "") or item.get("id", "") or ""
                    title = item.get("title", "") or ""
                    text = item.get("body", "") or item.get("selftext", "") or title

                    all_docs.append({
                        "doc_id": make_doc_id("reddit", url),
                        "source": "reddit",
                        "city": city_name,
                        "title": title,
                        "text": text,
                        "published_at": item.get("createdAt", "") or item.get("created", ""),
                        "url": url,
                        "ingestion_time": datetime.now(timezone.utc).isoformat(),
                        "run_id": run_id
                    })

            log.info(f"[Reddit] Got {len(items)} posts for {city_name}")

        except Exception as e:
            log.warning(f"[Reddit] Error for {city_name}: {e}")

    log.info(f"[Reddit] Total: {len(all_docs)} posts fetched")
    return all_docs

def save_to_mongo(docs: list, run_id: str):
    if not docs or not MONGO_URI:
        return

    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        
        # 1. Save Artifact
        db[ARTIFACTS_COLLECTION].insert_one({
            "run_id": run_id,
            "artifact_type": "raw_ingestion_reddit",
            "timestamp": datetime.now(timezone.utc),
            "document_count": len(docs),
            "payload": docs
        })
        log.info(f"[Artifacts] Saved reddit artifact to MongoDB.")

        # 2. Save Documents
        operations = [
            UpdateOne({"doc_id": doc["doc_id"]}, {"$setOnInsert": doc}, upsert=True)
            for doc in docs
        ]
        result = db[DOCUMENTS_COLLECTION].bulk_write(operations)
        log.info(f"[DB] Inserted {result.upserted_count} new Reddit docs, skipped {len(docs) - result.upserted_count} duplicates.")

    except Exception as e:
        log.error(f"[DB] Failed to save to MongoDB: {e}")
    finally:
        if 'client' in locals():
            client.close()

def run(run_id: str) -> dict:
    log.info(f"=== STEP 1b: INGEST REDDIT | run_id={run_id} ===")
    config = load_config()
    reddit_docs = fetch_reddit_apify(config, run_id)
    save_to_mongo(reddit_docs, run_id)
    return {"run_id": run_id, "total_docs": len(reddit_docs)}

if __name__ == "__main__":
    current_run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    run(current_run_id)