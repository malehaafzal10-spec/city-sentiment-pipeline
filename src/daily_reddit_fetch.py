"""
daily_reddit_fetch.py — Daily fetch of r/travel posts.

- Runs every day at 8pm Denmark time via GitHub Actions
- Rotates through a list of Apify keys (one per day)
- Only fetches posts published in the last 24 hours
- Filters posts where title mentions a city or country (FlashText)
- Saves to MongoDB collection: reddit_travel_posts
- Also saves local JSON backup

Usage:
    python src/daily_reddit_fetch.py

Environment variables (GitHub Secrets):
    APIFY_KEYS          — comma-separated list of Apify tokens
    MONGO_URI           — MongoDB connection string
    MONGO_DB_NAME       — MongoDB database name
"""

import os
import re
import json
import time
import hashlib
import logging
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pycountry
import geonamescache
from flashtext import KeywordProcessor
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv

load_dotenv()

# ── CONFIG ────────────────────────────────────────────────────────────────────

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
COLLECTION = "reddit_travel_posts"

# Path to the key schedule config file
KEY_SCHEDULE_FILE = Path("config/apify_key_schedule.txt")

# All Apify keys stored as GitHub Secret (comma-separated)
# e.g. "key1,key2,key3,..."
APIFY_KEYS = [k.strip() for k in os.getenv("APIFY_KEYS", "").split(",") if k.strip()]

MAX_ITEMS = 500  # fetch enough to cover 24 hours worth of posts
HOURS_BACK = 24
BACKUP_DIR = Path("artifacts/daily_reddit")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("daily_reddit_fetch")


# ── APIFY KEY ROTATION ────────────────────────────────────────────────────────

def get_todays_key() -> str:
    """
    Pick Apify key based on today's date from the schedule file.
    
    Schedule file format (config/apify_key_schedule.txt):
        2026-05-21, APIFY_KEY_1
        2026-05-22, APIFY_KEY_2
        ...
    
    The value in the file is the INDEX (1-based) into the APIFY_KEYS list
    stored in GitHub Secrets, or the literal key itself.
    """
    if not KEY_SCHEDULE_FILE.exists():
        raise FileNotFoundError(f"Key schedule file not found: {KEY_SCHEDULE_FILE}")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Parse the schedule file
    schedule = {}
    with open(KEY_SCHEDULE_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",", 1)]
            if len(parts) == 2:
                schedule[parts[0]] = parts[1]

    if today not in schedule:
        raise ValueError(
            f"No Apify key scheduled for today ({today}). "
            f"Add an entry to {KEY_SCHEDULE_FILE}"
        )

    key_name = schedule[today]
    log.info(f"Schedule: using key '{key_name}' for {today}")

    # Debug: show all available env vars that start with APIFY
    apify_env_vars = [k for k in os.environ.keys() if "APIFY" in k]
    log.info(f"Available APIFY env vars: {apify_env_vars}")

    # The schedule file stores key names like APIFY_KEY_1
    # Try to resolve from environment variable first, then from APIFY_KEYS list
    env_val = os.getenv(key_name)
    if env_val:
        return env_val

    # Fallback: treat as 1-based index into APIFY_KEYS list
    # e.g. APIFY_KEY_1 -> index 0
    match = re.search(r"(\d+)$", key_name)
    if match and APIFY_KEYS:
        idx = int(match.group(1)) - 1
        if 0 <= idx < len(APIFY_KEYS):
            return APIFY_KEYS[idx]

    raise ValueError(
        f"Could not resolve key '{key_name}' — "
        f"make sure it's set as a GitHub Secret or in APIFY_KEYS"
    )


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


def extract_post_id(url: str) -> str:
    match = re.search(r'/comments/([a-z0-9]+)/', url)
    return match.group(1) if match else make_doc_id(url)


def get_type(url: str) -> str:
    parts = [p for p in url.rstrip('/').split('/') if p]
    comments_idx = next((i for i, p in enumerate(parts) if p == 'comments'), None)
    if comments_idx is None:
        return "post"
    after_comments = parts[comments_idx + 1:]
    return "comment" if len(after_comments) >= 3 else "post"


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


def parse_published_at(raw: str) -> datetime | None:
    """Parse published_at string to datetime."""
    if not raw:
        return None
    try:
        # Handle both ISO format and Unix timestamp
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        raw = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def is_within_24_hours(published_at_str: str) -> bool:
    """Check if a post was published within the last 24 hours."""
    dt = parse_published_at(published_at_str)
    if not dt:
        return True  # keep if we can't parse the date
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_BACK)
    return dt >= cutoff


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


# ── APIFY FETCH ───────────────────────────────────────────────────────────────

def fetch_rtravel(apify_token: str) -> list:
    log.info(f"Fetching up to {MAX_ITEMS} posts from r/travel (last {HOURS_BACK}h)...")

    try:
        response = requests.post(
            f"https://api.apify.com/v2/acts/trudax~reddit-scraper-lite/runs?token={apify_token}",
            json={
                "startUrls": [{"url": "https://www.reddit.com/r/travel/"}],
                "searchPosts": True,
                "searchComments": False,
                "maxItems": MAX_ITEMS,
                "sort": "new"
            },
            timeout=30
        )

        run_data = response.json()
        apify_run_id = run_data.get("data", {}).get("id")

        if not apify_run_id:
            log.error(f"Could not start Apify run: {run_data}")
            return []

        log.info(f"Apify run started ({apify_run_id}), waiting...")

        for attempt in range(90):
            time.sleep(3)
            status_resp = requests.get(
                f"https://api.apify.com/v2/actor-runs/{apify_run_id}?token={apify_token}",
                timeout=10
            )
            status = status_resp.json().get("data", {}).get("status", "")
            if status == "SUCCEEDED":
                break
            elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
                log.error(f"Apify run {status}")
                return []
            if attempt % 10 == 0:
                log.info(f"Still waiting... status={status}")

        items_resp = requests.get(
            f"https://api.apify.com/v2/actor-runs/{apify_run_id}/dataset/items?token={apify_token}",
            timeout=30
        )
        items = items_resp.json()

        if not isinstance(items, list):
            log.error("Unexpected response format")
            return []

        # ── First pass: build post_map ────────────────────────────────────────
        post_map = {}
        raw_items = []
        dropped_non_reddit = 0
        dropped_old = 0
        dropped_no_location = 0

        for item in items:
            url = item.get("url", "") or ""
            title = item.get("title", "") or ""
            text = item.get("body", "") or item.get("selftext", "") or ""
            published_at = item.get("createdAt", "") or item.get("created", "") or ""

            if "reddit.com" not in url.lower():
                dropped_non_reddit += 1
                continue

            if not is_within_24_hours(published_at):
                dropped_old += 1
                continue

            doc_type = get_type(url)
            post_id = extract_post_id(url)

            if doc_type == "post":
                if not title_has_location(title):
                    dropped_no_location += 1
                    continue
                locations = extract_locations(f"{title} {text}")
                post_map[post_id] = {"locations": locations, "title": title}

            raw_items.append({
                "doc_id": make_doc_id(url),
                "post_id": post_id,
                "type": doc_type,
                "title": title,
                "text": text,
                "published_at": published_at,
                "url": url,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source": "reddit",
                "subreddit": "r/travel",
            })

        # ── Second pass: assign locations ─────────────────────────────────────
        final = []
        for doc in raw_items:
            post_id = doc["post_id"]
            doc_type = doc["type"]

            if doc_type == "post":
                doc["locations"] = post_map.get(post_id, {}).get("locations", {"cities": [], "countries": []})
                doc["location_source"] = "post_title"

            elif doc_type == "comment":
                if not doc["title"] and post_id in post_map:
                    doc["title"] = post_map[post_id]["title"]

                comment_locations = extract_locations(doc["text"])
                if comment_locations["cities"] or comment_locations["countries"]:
                    doc["locations"] = comment_locations
                    doc["location_source"] = "comment_text"
                elif post_id in post_map:
                    doc["locations"] = post_map[post_id]["locations"]
                    doc["location_source"] = "inherited_from_post"
                else:
                    doc["locations"] = {"cities": [], "countries": []}
                    doc["location_source"] = "none"

            final.append(doc)

        log.info(
            f"Kept: {len(final)} | "
            f"Dropped (non-Reddit): {dropped_non_reddit} | "
            f"Dropped (older than 24h): {dropped_old} | "
            f"Dropped (no location): {dropped_no_location}"
        )
        return final

    except Exception as e:
        log.error(f"Fetch error: {e}")
        return []


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("DAILY r/travel FETCH")
    log.info(f"Date:       {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    log.info(f"Window:     last {HOURS_BACK} hours")
    log.info(f"Collection: {COLLECTION}")
    log.info("=" * 60)

    # Pre-flight checks
    if not test_mongo():
        log.error("Aborting — fix MongoDB connection first")
        return

    try:
        apify_token = get_todays_key()
    except ValueError as e:
        log.error(str(e))
        return

    # Fetch
    docs = fetch_rtravel(apify_token)

    if not docs:
        log.warning("No documents fetched — nothing to save")
        return

    # Save local backup
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"rtravel_{timestamp}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2, ensure_ascii=False)
    log.info(f"Backup saved → {backup_path}")

    # Push to MongoDB
    save_to_mongo(docs)

    posts = [d for d in docs if d["type"] == "post"]
    comments = [d for d in docs if d["type"] == "comment"]
    inherited = [d for d in comments if d.get("location_source") == "inherited_from_post"]

    log.info("=" * 60)
    log.info("DONE")
    log.info(f"Total docs:          {len(docs)}")
    log.info(f"Posts:               {len(posts)}")
    log.info(f"Comments:            {len(comments)}")
    log.info(f"Inherited locations: {len(inherited)}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()