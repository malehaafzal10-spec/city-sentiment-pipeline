"""
r01_fetch_reddit.py — Daily fetch of r/travel posts published on date n-2 (2 days ago).
Uses Playwright to bypass Reddit's bot detection.

Saves to:
    - Local JSON backup: artifacts/daily_reddit/rtravel_<target_date>_<timestamp>.json
    - MongoDB collection: r01_reddit_posts_raw_final
    - MongoDB artifact:   pipeline_artifacts (artifact_type: raw_ingestion)

Run ID format: run-YYYYMMDD-AUTO  (where YYYYMMDD = target date, i.e. n-2)

Usage:
    python src/r01_fetch_reddit.py
"""

import os
import json
import time
import hashlib
import logging
from datetime import datetime, timezone, timedelta
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
COLLECTION = "r01_reddit_posts_raw_final"
ARTIFACTS_COLLECTION = "pipeline_artifacts"
BACKUP_DIR = Path("artifacts/daily_reddit")

POSTS_PER_PAGE = 100
NUM_PAGES = 10

# ── TARGET DATE: n-2 ──────────────────────────────────────────────────────────

def get_target_date() -> datetime:
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=2)

TARGET_DATE     = get_target_date()
TARGET_DATE_STR = TARGET_DATE.strftime("%Y-%m-%d")
RUN_ID          = f"run-{TARGET_DATE.strftime('%Y%m%d')}-AUTO"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("r01_fetch_reddit")


# ── LOCATION PROCESSOR ────────────────────────────────────────────────────────

def build_processor():
    cities, countries = [], []
    for country in pycountry.countries:
        countries.append(country.name)
        if hasattr(country, "common_name"):
            countries.append(country.common_name)
    gc = geonamescache.GeonamesCache()
    for city in gc.get_cities().values():
        name = city.get("name", "")
        if name and city.get("population", 0) > 50000:
            cities.append(name)
    processor = KeywordProcessor(case_sensitive=False)
    for c in cities:
        processor.add_keyword(c, f"City:{c}")
    for c in countries:
        processor.add_keyword(c, f"Country:{c}")
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

def post_is_on_target_date(created_utc: float) -> bool:
    post_date = datetime.fromtimestamp(created_utc, tz=timezone.utc)
    return post_date.strftime("%Y-%m-%d") == TARGET_DATE_STR

def post_is_older_than_target(created_utc: float) -> bool:
    post_date = datetime.fromtimestamp(created_utc, tz=timezone.utc)
    return post_date.strftime("%Y-%m-%d") < TARGET_DATE_STR


# ── REDDIT FETCH ──────────────────────────────────────────────────────────────

def fetch_page(page, after: str = None) -> tuple:
    url = f"https://www.reddit.com/r/travel/new.json?limit={POSTS_PER_PAGE}"
    if after:
        url += f"&after={after}"
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=15000)
        if response.status != 200:
            log.error(f"Reddit returned {response.status}")
            return [], None
        content = page.inner_text("pre") if page.locator("pre").count() > 0 else page.content()
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

def process_posts(raw_posts: list) -> tuple:
    docs = []
    dropped_wrong_date = 0
    dropped_no_location = 0
    fetched_at = datetime.now(timezone.utc).isoformat()

    for p in raw_posts:
        title      = p.get("title", "") or ""
        text       = p.get("selftext", "") or ""
        post_id    = p.get("id", "") or ""
        url        = f"https://www.reddit.com{p.get('permalink', '')}"
        created_utc = p.get("created_utc")

        if not created_utc:
            continue

        if not post_is_on_target_date(created_utc):
            dropped_wrong_date += 1
            continue

        published_at = datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat()

        if text in ("[deleted]", "[removed]"):
            text = ""

        if not title_has_location(title):
            dropped_no_location += 1
            continue

        locations = extract_locations(f"{title} {text}")

        docs.append({
            "doc_id":          make_doc_id(url),
            "post_id":         post_id,
            "run_id":          RUN_ID,
            "type":            "post",
            "title":           title,
            "text":            text,
            "published_at":    published_at,
            "target_date":     TARGET_DATE_STR,
            "locations":       locations,
            "location_source": "post_title",
            "url":             url,
            "fetched_at":      fetched_at,
            "source":          "reddit",
            "subreddit":       "r/travel",
        })

    metrics = {
        "kept":                len(docs),
        "dropped_wrong_date":  dropped_wrong_date,
        "dropped_no_location": dropped_no_location,
    }
    log.info(
        f"Kept: {len(docs)} | "
        f"Dropped (wrong date): {dropped_wrong_date} | "
        f"Dropped (no location): {dropped_no_location}"
    )
    return docs, metrics


# ── MONGODB ───────────────────────────────────────────────────────────────────

def get_mongo_db():
    if not MONGO_URI:
        return None
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        log.info("MongoDB connection OK ✓")
        return client[DB_NAME]
    except Exception as e:
        log.error(f"MongoDB connection failed: {e}")
        return None

def save_posts(db, docs: list):
    operations = [
        UpdateOne({"doc_id": doc["doc_id"]}, {"$setOnInsert": doc}, upsert=True)
        for doc in docs
    ]
    result = db[COLLECTION].bulk_write(operations)
    log.info(
        f"MongoDB: {result.upserted_count} new inserted, "
        f"{len(docs) - result.upserted_count} already existed → '{COLLECTION}'"
    )

def save_artifact(db, docs: list, metrics: dict):
    artifact = {
        "run_id":        RUN_ID,
        "artifact_type": "raw_ingestion",
        "stage":         "R01",
        "document_count": len(docs),
        "metrics":       metrics,
        "payload":       [{k: v for k, v in d.items() if k != "_id"} for d in docs[:10]],
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "target_date":   TARGET_DATE_STR,
    }
    db[ARTIFACTS_COLLECTION].update_one(
        {"run_id": RUN_ID, "artifact_type": "raw_ingestion"},
        {"$set": artifact},
        upsert=True
    )
    log.info(f"Artifact saved → '{ARTIFACTS_COLLECTION}' (run_id: {RUN_ID})")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("R01 — r/travel DAILY FETCH (n-2)")
    log.info(f"Run today:   {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    log.info(f"Target date: {TARGET_DATE_STR}  (2 days ago)")
    log.info(f"Run ID:      {RUN_ID}")
    log.info(f"Collection:  {COLLECTION}")
    log.info("=" * 60)

    all_raw = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-US",
        )
        page = context.new_page()

        log.info("Warming up browser session...")
        page.goto("https://www.reddit.com/r/travel/", wait_until="domcontentloaded", timeout=15000)
        time.sleep(3)

        after      = None
        stop_early = False

        for page_num in range(NUM_PAGES):
            log.info(f"Fetching page {page_num + 1}/{NUM_PAGES}...")
            posts, after = fetch_page(page, after)

            if not posts:
                log.info("No more posts returned")
                break

            all_raw.extend(posts)
            log.info(f"  → {len(posts)} posts (total so far: {len(all_raw)})")

            for post in posts:
                created_utc = post.get("created_utc")
                if created_utc and post_is_older_than_target(created_utc):
                    log.info(f"Scrolled past {TARGET_DATE_STR} — stopping pagination")
                    stop_early = True
                    break

            if stop_early or not after:
                break

            time.sleep(2)

        browser.close()

    log.info(f"Total raw posts fetched: {len(all_raw)}")

    if not all_raw:
        log.warning("No posts fetched")
        return

    docs, metrics = process_posts(all_raw)

    if not docs:
        log.warning(f"No posts found for target date {TARGET_DATE_STR}")
        return

    # ── Local backup ──────────────────────────────────────────────────────────
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp   = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"rtravel_{TARGET_DATE_STR}_{timestamp}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2, ensure_ascii=False)
    log.info(f"Local backup → {backup_path}")

    # ── MongoDB ───────────────────────────────────────────────────────────────
    db = get_mongo_db()
    if db is not None:
        save_posts(db, docs)
        save_artifact(db, docs, metrics)

    log.info("=" * 60)
    log.info("DONE")
    log.info(f"Run ID:      {RUN_ID}")
    log.info(f"Target date: {TARGET_DATE_STR}")
    log.info(f"Posts saved: {len(docs)}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()