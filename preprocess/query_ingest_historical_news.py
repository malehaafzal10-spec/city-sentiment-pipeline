"""
01a_ingest_historical_news.py — Backfill: Fetch news from Mar 7 – Apr 8 2026.
Stores lightweight article records (no full content) into a separate
MongoDB collection: raw_documents_historical.

Rate limit strategy: keywords are combined into a single OR query per city
per day, reducing requests from (days × cities × keywords) to (days × cities).

Usage:
    python preprocess/01a_ingest_historical_news.py --from-date 2026-03-07 --to-date 2026-03-13
"""

import os
import hashlib
import logging
import argparse
from datetime import datetime, timedelta, timezone

from newsapi import NewsApiClient
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
HISTORICAL_COLLECTION = "raw_documents_historical"

# ── Date range defaults (overridden by CLI args) ───────────────────────────────
DEFAULT_FROM = "2026-03-09"
DEFAULT_TO   = "2026-04-08"

# NewsAPI free tier: max 100 results per request, max 30 days back
PAGE_SIZE = 100

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("ingest_historical")


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_doc_id(url: str, date: str) -> str:
    return hashlib.sha256(f"news:{url}:{date}".encode()).hexdigest()[:16]


def date_range(start: datetime, end: datetime):
    """Yield each day from start up to (but not including) end."""
    current = start
    while current < end:
        yield current
        current += timedelta(days=1)


def parse_published_at(raw: str) -> datetime | None:
    """Parse ISO 8601 string from NewsAPI into a datetime, or return None."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_day(newsapi: NewsApiClient, city: dict, day: datetime) -> list[dict]:
    """
    Fetch lightweight article records for one city on one day.
    All keywords are combined into a single OR query to minimise API requests.
    Returns only: doc_id, source, city, keywords, title, description, url,
                  published_at (datetime), fetch_date, ingestion_time.
    No full article content is stored.
    """
    from_str  = day.strftime("%Y-%m-%d")
    to_str    = (day + timedelta(days=1)).strftime("%Y-%m-%d")
    city_name = city["name"]

    # Combine all keywords into one query: "paris travel OR visit paris OR paris tourism"
    combined_query = " OR ".join(city["keywords"])

    docs = []
    try:
        response = newsapi.get_everything(
            q=combined_query,
            language="en",
            sort_by="publishedAt",
            from_param=from_str,
            to=to_str,
            page_size=PAGE_SIZE,
        )
        for article in response.get("articles", []):
            url   = article.get("url") or ""
            title = (article.get("title") or "").strip()
            desc  = (article.get("description") or "").strip()
            raw_published = article.get("publishedAt", "")

            # Skip placeholder / removed articles
            if title in ("[Removed]", "") and not url:
                continue

            docs.append({
                "doc_id":         make_doc_id(url, from_str),
                "source":         "news",
                "city":           city_name,
                "keywords":       city["keywords"],
                "title":          title,
                "description":    desc,
                "url":            url,
                "published_at":   parse_published_at(raw_published),
                "fetch_date":     from_str,
                "ingestion_time": datetime.now(timezone.utc),
            })

    except Exception as e:
        log.warning(f"[{city_name}] Error for {from_str}: {e}")

    return docs


# ── Storage ───────────────────────────────────────────────────────────────────

def save_to_db(docs: list[dict]) -> None:
    if not docs:
        return
    if not MONGO_URI:
        log.error("[DB] MONGO_URI not set — cannot save.")
        return

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
        log.info(f"[DB] +{inserted} inserted, {skipped} skipped (duplicates)")

    except Exception as e:
        log.error(f"[DB] Bulk write failed: {e}")
    finally:
        if "client" in locals():
            client.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def run(from_date: datetime, to_date: datetime) -> None:
    import json

    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key:
        log.error("NEWSAPI_KEY not set — aborting.")
        return

    # Path is relative to project root
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(BASE_DIR, "config/cities.json")) as f:
        config = json.load(f)

    newsapi = NewsApiClient(api_key=api_key)

    total_inserted = 0
    days = list(date_range(from_date, to_date))

    log.info(
        f"=== HISTORICAL BACKFILL | "
        f"{from_date.date()} → {to_date.date()} | "
        f"{len(days)} days | {len(config['cities'])} cities | "
        f"{len(days) * len(config['cities'])} total requests ==="
    )

    for day in days:
        day_docs = []
        for city in config["cities"]:
            docs = fetch_day(newsapi, city, day)
            day_docs.extend(docs)

        log.info(f"[{day.date()}] Fetched {len(day_docs)} articles — saving...")
        save_to_db(day_docs)
        total_inserted += len(day_docs)

    log.info(f"=== BACKFILL COMPLETE | {total_inserted} total articles processed ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Historical news backfill")
    parser.add_argument(
        "--from-date",
        default=DEFAULT_FROM,
        help=f"Start date inclusive (YYYY-MM-DD). Default: {DEFAULT_FROM}"
    )
    parser.add_argument(
        "--to-date",
        default=DEFAULT_TO,
        help=f"End date exclusive (YYYY-MM-DD). Default: {DEFAULT_TO}"
    )
    args = parser.parse_args()

    try:
        from_dt = datetime.strptime(args.from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        to_dt   = datetime.strptime(args.to_date,   "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        print("Error: dates must be in YYYY-MM-DD format, e.g. 2026-03-07")
        exit(1)

    if from_dt >= to_dt:
        print("Error: --from-date must be earlier than --to-date")
        exit(1)

    run(from_dt, to_dt)