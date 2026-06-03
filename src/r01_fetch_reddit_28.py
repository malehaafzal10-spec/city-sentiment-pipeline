"""
r01_fetch_reddit_28.py — One-time fetch of r/travel posts from May 28th 2026 onwards.
Uses Playwright to bypass Reddit's bot detection.
Saves locally to JSON AND pushes to MongoDB.

Usage:
    python src/r01_fetch_reddit_28.py

Output:
    - Local: artifacts/daily_reddit/rtravel_<timestamp>.json
    - MongoDB: reddit_posts_final collection
"""

import os
import json
import time
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pycountry
import geonamescache
from flashtext import KeywordProcessor
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
COLLECTION = "reddit_posts_final"
BACKUP_DIR = Path("artifacts/daily_reddit")

POSTS_PER_PAGE = 100
NUM_PAGES = 10
FROM_DATE = datetime(2026, 5, 28, tzinfo=timezone.utc)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("fetch_reddit_onetime")


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


# ── REDDIT FETCH VIA PLAYWRIGHT ───────────────────────────────────────────────

def fetch_page(page, after: str = None) -> tuple:
    """Fetch one page of r/travel posts. Returns (posts, after_cursor)."""
    url = f"https://www.reddit.com/r/travel/new.json?limit={POSTS_PER_PAGE}"
    if after:
        url += f"&after={after}"

    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=15000)

        if response.status != 200:
            log.error(f"Reddit returned {response.status}")
            return [], None

        content = page.inner_text("pre") if page.locator("pre").count() > 0 else page.content()

        # Strip HTML if needed
        if "<html" in content.lower():
            start = content.find("{")
            end = content.rfind("}") + 1
            content = content[start:end]

        data = json.loads(content)
        posts = [child["data"] for child in data.get("data", {}).get("children", []) if child.get("kind") == "t3"]
        after_cursor = data.get("data", {}).get("after")
        return posts, after_cursor

    except Exception as e:
        log.error(f"Error fetching page: {e}")
        return [], None


# ── PROCESS POSTS ─────────────────────────────────────────────────────────────

def process_posts(raw_posts: list) -> list:
    docs = []
    dropped_old = 0
    dropped_no_location = 0
    fetched_at = datetime.now(timezone.utc).isoformat()

    for p in raw_posts:
        title = p.get("title", "") or ""
        text = p.get("selftext", "") or ""
        post_id = p.get("id", "") or ""
        url = f"https://www.reddit.com{p.get('permalink', '')}"
        created_utc = p.get("created_utc")
        published_at = datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat() if created_utc else ""

        if created_utc and datetime.fromtimestamp(created_utc, tz=timezone.utc) < FROM_DATE:
            dropped_old += 1
            continue

        if text in ("[deleted]", "[removed]"):
            text = ""

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

    log.info(f"Kept: {len(docs)} | Dropped (older than May 28): {dropped_old} | Dropped (no location): {dropped_no_location}")
    return docs


# ── MONGODB ───────────────────────────────────────────────────────────────────

def test_mongo() -> bool:
    if not MONGO_URI:
        log.warning("MONGO_URI not set — skipping MongoDB push")
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


def save_to_mongo(docs: list):
    if not MONGO_URI or not docs:
        return
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
        db = client[DB_NAME]
        operations = [
            UpdateOne({"doc_id": doc["doc_id"]}, {"$setOnInsert": doc}, upsert=True)
            for doc in docs
        ]
        result = db[COLLECTION].bulk_write(operations)
        log.info(f"MongoDB: {result.upserted_count} new inserted, {len(docs) - result.upserted_count} already existed → '{COLLECTION}'")
        client.close()
    except Exception as e:
        log.error(f"MongoDB save failed: {e}")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("r/travel ONE-TIME FETCH (May 28 onwards)")
    log.info(f"Date:       {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    log.info(f"From:       {FROM_DATE.strftime('%Y-%m-%d')}")
    log.info(f"Collection: {COLLECTION}")
    log.info("=" * 60)

    all_raw = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-US",
        )
        page = context.new_page()

        # Warm up session
        log.info("Warming up browser session...")
        page.goto("https://www.reddit.com/r/travel/", wait_until="domcontentloaded", timeout=15000)
        time.sleep(3)

        after = None
        stop_early = False

        for page_num in range(NUM_PAGES):
            log.info(f"Fetching page {page_num + 1}/{NUM_PAGES}...")
            posts, after = fetch_page(page, after)

            if not posts:
                log.info("No more posts")
                break

            # Check if we've gone past our date range
            for post in posts:
                created_utc = post.get("created_utc")
                if created_utc and datetime.fromtimestamp(created_utc, tz=timezone.utc) < FROM_DATE:
                    log.info(f"Reached posts older than May 28 — stopping early")
                    stop_early = True
                    break

            all_raw.extend(posts)
            log.info(f"  → {len(posts)} posts fetched (total so far: {len(all_raw)})")

            if stop_early or not after:
                break

            time.sleep(2)

        browser.close()

    log.info(f"Total raw posts: {len(all_raw)}")

    if not all_raw:
        log.warning("No posts fetched")
        return

    docs = process_posts(all_raw)

    if not docs:
        log.warning("No documents after filtering")
        return

    # Save locally
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"rtravel_{timestamp}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2, ensure_ascii=False)
    log.info(f"Saved locally → {backup_path}")

    if test_mongo():
        save_to_mongo(docs)

    log.info("=" * 60)
    log.info("DONE")
    log.info(f"Total posts saved: {len(docs)}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()