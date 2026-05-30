"""
fetch_comments.py — Fetch top 10 comments for all posts in reddit_relevant collection.
Uses Playwright to bypass Reddit's bot detection.
Saves to MongoDB collection: reddit_comments_final

Usage:
    python insights/fetch_comments.py

Requirements:
    - MONGO_URI in .env
    - MONGO_DB_NAME in .env
    - pip install playwright
    - playwright install chromium
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
SOURCE_COLLECTION = "reddit_relevant"
DEST_COLLECTION = "reddit_comments_final"
BACKUP_DIR = Path("artifacts/comments")
COMMENTS_PER_POST = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("fetch_comments")


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


# ── MONGODB ───────────────────────────────────────────────────────────────────

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


def save_to_mongo(docs: list):
    if not docs:
        return
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
        result = db[DEST_COLLECTION].bulk_write(operations)
        log.info(f"MongoDB: {result.upserted_count} new inserted, {len(docs) - result.upserted_count} already existed → '{DEST_COLLECTION}'")
        client.close()
    except Exception as e:
        log.error(f"MongoDB save failed: {e}")


# ── FETCH COMMENTS VIA PLAYWRIGHT ─────────────────────────────────────────────

def fetch_comments_for_post(page, post: dict) -> list:
    post_id = post.get("post_id", "")
    post_url = post.get("url", "")
    title = post.get("title", "")
    post_locations = post.get("locations", {"cities": [], "countries": []})

    if not post_id:
        return []

    comments_url = f"https://www.reddit.com/r/travel/comments/{post_id}.json?sort=top&limit={COMMENTS_PER_POST}"

    try:
        response = page.goto(comments_url, wait_until="domcontentloaded", timeout=15000)

        if response.status != 200:
            log.warning(f"[{post_id}] Reddit returned {response.status}")
            return []

        content = page.content()

        # Extract JSON from page
        start = content.find("[{")
        if start == -1:
            start = content.find("{")
        end = content.rfind("}") + 1

        if start == -1 or end == 0:
            log.warning(f"[{post_id}] Could not find JSON in response")
            return []

        raw_json = content[start:end]

        # Handle both list and dict responses
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            # Try extracting from pre tag
            pre_start = content.find("<pre>")
            pre_end = content.find("</pre>")
            if pre_start != -1 and pre_end != -1:
                raw_json = content[pre_start+5:pre_end]
                data = json.loads(raw_json)
            else:
                log.warning(f"[{post_id}] Could not parse JSON")
                return []

        if not isinstance(data, list) or len(data) < 2:
            return []

        comments_data = data[1].get("data", {}).get("children", [])
        comments = []

        for child in comments_data:
            if child.get("kind") != "t1":
                continue

            c = child.get("data", {})
            body = c.get("body", "") or ""

            if body in ("[deleted]", "[removed]", ""):
                continue

            comment_id = c.get("id", "")
            comment_url = f"https://www.reddit.com{c.get('permalink', '')}"
            created_utc = c.get("created_utc")
            published_at = datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat() if created_utc else ""

            comment_locations = extract_locations(body)
            if comment_locations["cities"] or comment_locations["countries"]:
                locations = comment_locations
                location_source = "comment_text"
            else:
                locations = post_locations
                location_source = "inherited_from_post"

            comments.append({
                "doc_id": make_doc_id(comment_url),
                "post_id": post_id,
                "comment_id": comment_id,
                "type": "comment",
                "title": title,
                "text": body,
                "published_at": published_at,
                "locations": locations,
                "location_source": location_source,
                "url": comment_url,
                "parent_url": post_url,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source": "reddit",
                "subreddit": "r/travel",
            })

        return comments

    except Exception as e:
        log.error(f"[{post_id}] Error: {e}")
        return []


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    run_id = f"comments_run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    log.info("=" * 60)
    log.info("FETCH COMMENTS FOR reddit_relevant POSTS")
    log.info(f"run_id:     {run_id}")
    log.info(f"Source:     {SOURCE_COLLECTION}")
    log.info(f"Dest:       {DEST_COLLECTION}")
    log.info(f"Per post:   top {COMMENTS_PER_POST} comments")
    log.info("=" * 60)

    if not test_mongo():
        log.error("Aborting — fix MongoDB connection first")
        return

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    posts = list(db[SOURCE_COLLECTION].find({}, {"post_id": 1, "url": 1, "title": 1, "locations": 1}))
    client.close()

    if not posts:
        log.error(f"No posts found in '{SOURCE_COLLECTION}'")
        return

    log.info(f"Found {len(posts)} posts to fetch comments for")

    all_comments = []

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

        for i, post in enumerate(posts):
            log.info(f"[{i+1}/{len(posts)}] {post.get('post_id', '')} — {post.get('title', '')[:60]}")

            comments = fetch_comments_for_post(page, post)

            for c in comments:
                c["run_id"] = run_id

            all_comments.extend(comments)
            log.info(f"  → {len(comments)} comments")

            time.sleep(2)

        browser.close()

    log.info(f"\nTotal comments fetched: {len(all_comments)}")

    if not all_comments:
        log.warning("No comments fetched")
        return

    # Save locally
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"comments_{timestamp}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(all_comments, f, indent=2, ensure_ascii=False)
    log.info(f"Backup saved → {backup_path}")

    save_to_mongo(all_comments)

    log.info("=" * 60)
    log.info("DONE")
    log.info(f"run_id:         {run_id}")
    log.info(f"Total comments: {len(all_comments)}")
    log.info(f"Collection:     {DEST_COLLECTION}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()