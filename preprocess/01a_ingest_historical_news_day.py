"""
Backfill fetch for a single day using the same strategy as the daily ingest.py pipeline (one request per keyword per city).

Unlike 01a which combined all keywords into one OR query per city,
this matches the daily pipeline exactly — same doc_id, same fields,
same page_size — so results are comparable.

Stores into raw_documents_historical. Duplicates handled by doc_id.

Usage:
  python preprocess/01b_fetch_test_day.py --date 2026-04-07
"""

import os
import json
import hashlib
import logging
import argparse
from datetime import datetime, timezone

from newsapi import NewsApiClient
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

load_dotenv()

MONGO_URI             = os.getenv("MONGO_URI")
DB_NAME               = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
HISTORICAL_COLLECTION = "raw_documents_historical"
PAGE_SIZE             = 20  # matches daily pipeline

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("fetch_test_day")


def make_doc_id(url: str) -> str:
    """Matches daily ingest.py — no city in hash, same as production."""
    return hashlib.sha256(f"news:{url}".encode()).hexdigest()[:16]


def fetch_day(newsapi: NewsApiClient, config: dict, date_str: str) -> list[dict]:
    """Fetch all cities and keywords for a single day, one request per keyword."""
    all_docs = []

    for city in config["cities"]:
        city_name = city["name"]
        city_docs = []

        for keyword in city["keywords"]:
            try:
                response = newsapi.get_everything(
                    q=keyword,
                    language="en",
                    sort_by="publishedAt",
                    page_size=PAGE_SIZE,
                    from_param=date_str,
                    to=date_str,
                )
                for article in response.get("articles", []):
                    url         = article.get("url", "")
                    title       = article.get("title", "")       or ""
                    description = article.get("description", "") or ""
                    content     = article.get("content", "")     or ""
                    text        = f"{title}. {description} {content}".strip()

                    if title.strip() in ("[Removed]", "") and not url:
                        continue

                    city_docs.append({
                        "doc_id":         make_doc_id(url),
                        "source":         "news",
                        "city":           city_name,
                        "keyword":        keyword,
                        "title":          title,
                        "description":    description,
                        "text":           text,
                        "url":            url,
                        "published_at":   article.get("publishedAt", ""),
                        "fetch_date":     date_str,
                        "ingestion_time": datetime.now(timezone.utc).isoformat(),
                        "fetch_strategy": "per_keyword",
                    })

                log.info(f"  [{city_name}] '{keyword}' → {len(response.get('articles', []))} articles")

            except Exception as e:
                log.warning(f"  [{city_name}] Error fetching '{keyword}': {e}")

        # Deduplicate within city — same URL fetched by multiple keywords
        seen_urls = set()
        unique_docs = []
        for doc in city_docs:
            if doc["url"] not in seen_urls:
                seen_urls.add(doc["url"])
                unique_docs.append(doc)

        dupes = len(city_docs) - len(unique_docs)
        log.info(f"  [{city_name}] {len(unique_docs)} unique articles ({dupes} keyword dupes removed)")
        all_docs.extend(unique_docs)

    return all_docs


def save_to_db(docs: list[dict]) -> tuple[int, int]:
    if not docs or not MONGO_URI:
        return 0, 0
    try:
        client = MongoClient(MONGO_URI)
        col    = client[DB_NAME][HISTORICAL_COLLECTION]
        ops = [
            UpdateOne(
                {"doc_id": doc["doc_id"]},
                {"$setOnInsert": doc},
                upsert=True,
            )
            for doc in docs
        ]
        result   = col.bulk_write(ops)
        inserted = result.upserted_count
        skipped  = len(docs) - inserted
        log.info(f"[DB] +{inserted} inserted, {skipped} already in DB")
        client.close()
        return inserted, skipped
    except Exception as e:
        log.error(f"[DB] Bulk write failed: {e}")
        return 0, 0


def run(date_str: str) -> None:
    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key:
        log.error("NEWSAPI_KEY not set — aborting.")
        return

    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(BASE_DIR, "config/cities.json")) as f:
        config = json.load(f)

    newsapi = NewsApiClient(api_key=api_key)

    log.info(f"=== FETCH TEST DAY | {date_str} | {len(config['cities'])} cities | per-keyword ===")

    all_docs = fetch_day(newsapi, config, date_str)
    inserted, skipped = save_to_db(all_docs)

    log.info(
        f"=== DONE | {date_str} | "
        f"Total fetched: {len(all_docs)} | "
        f"Inserted: {inserted} | "
        f"Already in DB: {skipped} ==="
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch a single day using per-keyword strategy.")
    parser.add_argument("--date", type=str, required=True, help="Date in YYYY-MM-DD format e.g. 2026-04-07")
    args = parser.parse_args()
    run(args.date)