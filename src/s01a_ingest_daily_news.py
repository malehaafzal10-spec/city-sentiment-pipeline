"""
ingest.py — Step 2: Fetch raw text from NewsAPI.
Stores resulting data and raw artifacts into MongoDB.
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timezone, timedelta

from newsapi import NewsApiClient
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

load_dotenv()

ARTIFACTS_DIR = os.getenv("PIPELINE_ARTIFACTS_DIR", "artifacts")
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

# We now have two collections: one for individual articles, one for pipeline run artifacts
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

def fetch_news(config: dict, run_id: str) -> list:
    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key:
        log.info("[News] No NEWSAPI_KEY set — skipping")
        return []

    newsapi = NewsApiClient(api_key=api_key)
    all_docs = []
    
    # Calculate yesterday's date in YYYY-MM-DD format for the API
    yesterday_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')
    log.info(f"[News] Fetching articles published on: {yesterday_str}")

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
                    from_param=yesterday_str,
                    to=yesterday_str
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

    # Save to MongoDB Artifacts Collection
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
                "payload": news_docs  # Storing the entire JSON list inside this field
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

def run(run_id: str) -> dict:
    log.info(f"=== STEP 2: INGEST | run_id={run_id} | mode=news_only ===")
    
    config = load_config()

    all_docs = fetch_news(config, run_id)
    
    save_raw_artifacts(all_docs, run_id)
    save_to_db(all_docs)

    log.info(f"[Ingest] Complete — {len(all_docs)} total documents")
    return {"run_id": run_id, "total_docs": len(all_docs)}


if __name__ == "__main__":
    # Generate a unique ID for this execution using the requested DDMMYYYY format
    current_run_id = f"run_{datetime.now(timezone.utc).strftime('%d%m%Y')}"
    
    # Trigger the pipeline
    run(current_run_id)