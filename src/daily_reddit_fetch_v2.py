"""
daily_reddit_fetch.py — Daily fetch of r/travel posts using Reddit's public JSON API.

No Apify, no Reddit API key needed — uses Reddit's free public JSON endpoint.

Fields per document:
  - doc_id          : hash of URL for deduplication
  - post_id         : Reddit post ID
  - type            : "post"
  - title           : post title
  - text            : post body
  - published_at    : when posted (ISO format)
  - locations       : { cities: [...], countries: [...] } via FlashText
  - location_source : where location was extracted from
  - url             : full Reddit post URL
  - fetched_at      : when we fetched it
  - source          : "reddit"
  - subreddit       : "r/travel"

Output: saves to MongoDB collection reddit_travel_posts + local JSON backup

Usage:
    python src/daily_reddit_fetch.py

Environment variables:
    MONGO_URI       — MongoDB connection string
    MONGO_DB_NAME   — MongoDB database name
"""

import os
import re
import json
import time
import hashlib
import logging
import requests
from datetime import datetime, timezone
from pathlib import Path

import pycountry
import geonamescache
from flashtext import KeywordProcessor
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
COLLECTION = "reddit_travel_posts"
BACKUP_DIR = Path("artifacts/daily_reddit")

# Reddit JSON API — fetch up to 100 posts per request, paginate for more
REDDIT_URL = "https://www.reddit.com/r/travel/new.json"
POSTS_PER_PAGE = 100
NUM_PAGES = 5  # 5 x 100 = 500 posts max per run
HEADERS = {"User-Agent": "travel-sentiment-research/1.0"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("daily_reddit_fetch")


# ── BUILD FLASHTEXT PROCESSOR ─────────────────────────────────────────────────

def build_processor():
    cities = []
    countries = []

    for country in pycountry.countries:
        countries.append(country.name)
        if hasattr(country, 'common_name'):
            countries.append(country.common_name)

    gc = geonamescache.GeonamesCache()
    for city in gc.get_cities().values():
        name = city.get("name", "")
        population = city.get("population", 0)
        if name and population > 50000:
            cities.append(name)

    processor = KeywordProcessor(case_sensitive=False)
    for city in cities:
        processor.add_keyword(city, f"City:{city}")
    for country in countries:
        processor.add_keyword(country, f"Country:{country}")

    log.info(f"FlashText processor built: {len(cities)} cities, {len(countries)} countries")
    return processor


log.info("Building location processor...")
PROCESSOR = build_processor()


# ── HELPERS ───────────────────────────────────────────────────────────────────

def make_doc_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def extract_locations(text: str) -> dict:
    extracted = PROCESSOR.extract_keywords(text)
    results = {"cities": [], "countries": []}
    seen = set()
    for item in extracted:
        if ":" not in item:
            continue
        category, name = item.split(":", 1)
        if name not in seen:
            seen.add(name)
            if category == "City":
                results["cities"].append(name)
            elif category == "Country":
                results["countries"].append(name)
    return results


def title_has_location(title: str) -> bool:
    locs = extract_locations(title)
    return bool(locs["cities"] or locs["countries"])


# ── REDDIT FETCH ──────────────────────────────────────────────────────────────

def fetch_rtravel() -> list:
    log.info(f"Fetching posts from r/travel (up to {POSTS_PER_PAGE * NUM_PAGES} posts)...")

    all_posts = []
    after = None  # pagination cursor

    for page in range(NUM_PAGES):
        params = {"limit": POSTS_PER_PAGE}
        if after:
            params["after"] = after

        try:
            response = requests.get(REDDIT_URL, headers=HEADERS, params=params, timeout=15)

            if response.status_code != 200:
                log.error(f"Reddit returned {response.status_code} on page {page + 1}")
                break

            data = response.json()
            posts = data.get("data", {}).get("children", [])
            after = data.get("data", {}).get("after")

            log.info(f"Page {page + 1}: got {len(posts)} posts")

            for post in posts:
                p = post.get("data", {})
                all_posts.append(p)

            if not after:
                log.info("No more pages")
                break

            time.sleep(1)  # be polite to Reddit

        except Exception as e:
            log.error(f"Error on page {page + 1}: {e}")
            break

    log.info(f"Total raw posts fetched: {len(all_posts)}")
    return all_posts


# ── PROCESS POSTS ─────────────────────────────────────────────────────────────

def process_posts(raw_posts: list) -> list:
    docs = []
    dropped_no_location = 0
    fetched_at = datetime.now(timezone.utc).isoformat()

    for p in raw_posts:
        title = p.get("title", "") or ""
        text = p.get("selftext", "") or ""
        post_id = p.get("id", "") or ""
        url = f"https://www.reddit.com{p.get('permalink', '')}"
        created_utc = p.get("created_utc")
        published_at = datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat() if created_utc else ""

        # Skip deleted/removed posts
        if text in ("[deleted]", "[removed]"):
            text = ""

        # Title must mention a location
        if not title_has_location(title):
            dropped_no_location += 1
            continue

        locations = extract_locations(f"{title} {text}")

        docs.append({
            "doc_id": make_doc_id(url),
            "post_id": post_id,
            "type": "post",
            "title": title,
            "text": text,
            "published_at": published_at,
            "locations": locations,
            "location_source": "post_title",
            "url": url,
            "fetched_at": fetched_at,
            "source": "reddit",
            "subreddit": "r/travel",
        })

    log.info(f"Kept: {len(docs)} | Dropped (no location in title): {dropped_no_location}")
    return docs


# ── MONGODB ───────────────────────────────────────────────────────────────────

def test_mongo() -> bool:
    if not MONGO_URI:
        log.error("MONGO_URI not set")
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


def save_to_mongo(docs: list) -> bool:
    if not docs or not MONGO_URI:
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
            for doc in docs
        ]
        result = db[COLLECTION].bulk_write(operations)
        log.info(f"MongoDB: {result.upserted_count} new inserted, {len(docs) - result.upserted_count} already existed → '{COLLECTION}'")
        client.close()
        return True
    except Exception as e:
        log.error(f"MongoDB save failed: {e}")
        return False


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("DAILY r/travel FETCH")
    log.info(f"Date:       {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    log.info(f"Collection: {COLLECTION}")
    log.info("=" * 60)

    if not test_mongo():
        log.error("Aborting — fix MongoDB connection first")
        return

    # Fetch
    raw_posts = fetch_rtravel()
    if not raw_posts:
        log.warning("No posts fetched")
        return

    # Process
    docs = process_posts(raw_posts)
    if not docs:
        log.warning("No documents after filtering")
        return

    # Local backup
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"rtravel_{timestamp}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2, ensure_ascii=False)
    log.info(f"Backup saved → {backup_path}")

    # Push to MongoDB
    save_to_mongo(docs)

    log.info("=" * 60)
    log.info("DONE")
    log.info(f"Total docs saved: {len(docs)}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()