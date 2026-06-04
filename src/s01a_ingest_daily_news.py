"""
s01a_ingest_daily_news.py — Step 1: Fetch raw text from NewsAPI.
Stores resulting data and raw artifacts into MongoDB.
"""

import os
import json
import hashlib
import logging
import argparse
from datetime import datetime, timezone, timedelta

from newsapi import NewsApiClient
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

load_dotenv(override=True)

ARTIFACTS_DIR = os.getenv("PIPELINE_ARTIFACTS_DIR", "artifacts")
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

DOCUMENTS_COLLECTION = "raw_documents_historical"
ARTIFACTS_COLLECTION = "pipeline_artifacts"

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("ingest")


def load_config():
    with open("config/cities.json") as f:
        return json.load(f)


def make_doc_id(source: str, url: str) -> str:
    return hashlib.sha256(f"{source}:{url}".encode()).hexdigest()[:16]


# ─── NEWSAPI ──────────────────────────────────────────────────────────────────

def fetch_news(config: dict, run_id: str, query_date_str: str) -> list:
    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key:
        log.info("[News] No NEWSAPI_KEY set — skipping")
        return []

    newsapi = NewsApiClient(api_key=api_key)
    all_docs = []
    
    log.info(f"[News] Fetching articles published on: {query_date_str}")

    for city in config["cities"]:
        city_name = city["name"]
        log.info(f"[News] Fetching articles for {city_name}")

        for keyword in city["keywords"]:
            try:
                response = newsapi.get_everything(
                    q=keyword,
                    language="en",
                    sort_by="publishedAt",
                    page_size=20,
                    from_param=query_date_str,
                    to=query_date_str
                )
                for article in response.get("articles", []):
                    url = article.get("url", "")
                    title = article.get("title", "") or ""
                    description = article.get("description", "") or ""
                    content = article.get("content", "") or ""
                    text = f"{title}. {description} {content}".strip()

                    all_docs.append({
                        "doc_id": make_doc_id("news", url),
                        "source": "news",
                        "city": city_name,
                        "title": title,
                        "text": text,
                        "published_at": article.get("publishedAt", ""),
                        "url": url,
                        "ingestion_time": datetime.now(timezone.utc).isoformat(),
                        "run_id": run_id
                    })
            except Exception as e:
                log.warning(f"[News] Error fetching '{keyword}': {e}")

    log.info(f"[News] Fetched {len(all_docs)} articles")
    return all_docs


# ─── STORAGE ──────────────────────────────────────────────────────────────────

def save_raw_artifacts(news_docs: list, run_id: str):
    """Saves the entire batch as a JSON file AND pushes it to MongoDB as an artifact."""
    if not news_docs:
        log.info("[Artifacts] No documents to save as an artifact.")
        return

    if MONGO_URI:
        try:
            client = MongoClient(MONGO_URI)
            db = client[DB_NAME]
            artifacts_col = db[ARTIFACTS_COLLECTION]
            
            artifact_document = {
                "run_id": run_id,
                "artifact_type": "raw_ingestion",
                "timestamp": datetime.now(timezone.utc),
                "document_count": len(news_docs),
                "payload": news_docs  
            }
            
            artifacts_col.insert_one(artifact_document)
            log.info(f"[Artifacts] Saved artifact snapshot to MongoDB collection '{ARTIFACTS_COLLECTION}'")
            
        except Exception as e:
            log.error(f"[Artifacts] Failed to save artifact to MongoDB: {e}")
        finally:
            if 'client' in locals():
                client.close()


def save_to_db(docs: list):
    """Saves individual documents into the raw_documents collection."""
    if not docs:
        return

    if not MONGO_URI:
        log.error("[DB] MONGO_URI is missing. Cannot save to MongoDB.")
        return

    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db[DOCUMENTS_COLLECTION]

        operations = [
            UpdateOne(
                {"doc_id": doc["doc_id"]},
                {"$setOnInsert": doc},
                upsert=True
            )
            for doc in docs
        ]

        result = collection.bulk_write(operations)
        inserted = result.upserted_count
        skipped = len(docs) - inserted
        
        log.info(f"[DB] Inserted {inserted} new, skipped {skipped} duplicates in '{DOCUMENTS_COLLECTION}'")

    except Exception as e:
        log.error(f"[DB] Failed to insert documents to MongoDB: {e}")
    finally:
        if 'client' in locals():
            client.close()


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run(target_date: datetime, force: bool) -> dict:
    # Generate run_id based on the target date provided
    run_id = f"run_{target_date.strftime('%d%m%Y')}"
    # Calculate the query date (NewsAPI fetches data from the day before the run)
    query_date_str = (target_date - timedelta(days=1)).strftime('%Y-%m-%d')
    
    log.info(f"=== STEP 1: INGEST | run_id={run_id} | mode=news_only ===")
    
    if MONGO_URI:
        try:
            client = MongoClient(MONGO_URI)
            db = client[DB_NAME]
            
            existing_run = db[ARTIFACTS_COLLECTION].find_one({
                "run_id": run_id,
                "artifact_type": "raw_ingestion"
            })
            
            # Allow bypassing the check if --force is used
            if existing_run and not force:
                log.info(f"⏭️  [Ingest] Run ID '{run_id}' already exists. Skipping API ingestion to save quota.")
                client.close()
                return {"run_id": run_id, "total_docs": 0, "status": "skipped"}
            elif existing_run and force:
                log.info(f"⚠️  [Ingest] Run ID '{run_id}' exists, but --force flag is active. Proceeding with backfill.")
                
        except Exception as e:
            log.error(f"[DB] Could not check for existing run_id. Proceeding anyway. Error: {e}")
        finally:
            if 'client' in locals() and getattr(client, "close", None):
                client.close()

    config = load_config()

    # Pass the accurately calculated query date to the fetch function
    all_docs = fetch_news(config, run_id, query_date_str)
    
    save_raw_artifacts(all_docs, run_id)
    save_to_db(all_docs)

    log.info(f"[Ingest] Complete — {len(all_docs)} total documents fetched.")
    return {"run_id": run_id, "total_docs": len(all_docs), "status": "completed"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest daily news into MongoDB.")
    parser.add_argument("--date", type=str, help="Target date for the run in YYYY-MM-DD format (e.g., 2026-06-01). Defaults to today.")
    parser.add_argument("--force", action="store_true", help="Force ingestion even if the run_id already exists.")
    
    args = parser.parse_args()

    # Set the target date based on input, or default to current time
    if args.date:
        target_dt = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        target_dt = datetime.now(timezone.utc)

    # Trigger the pipeline
    result = run(target_dt, args.force)
    print(f"\nIngestion status: {result.get('status')}")