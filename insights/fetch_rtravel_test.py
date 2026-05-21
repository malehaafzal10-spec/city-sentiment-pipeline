"""
fetch_rtravel_test.py — Fetch posts from r/travel where the title mentions
a city or country. Saves locally to JSON for inspection before pushing to MongoDB.

Fields per document:
  - doc_id        : hash of URL for deduplication
  - post_id       : Reddit post ID extracted from URL (shared between post + its comments)
  - type          : "post" or "comment"
  - title         : post title (comments inherit from parent post)
  - text          : post body or comment text
  - published_at  : when posted
  - locations     : { cities: [...], countries: [...] } extracted via FlashText
                    if comment has no locations, inherits from parent post

No LLM used — location extraction via FlashText + pycountry/geonamescache.

Output: insights/data/rtravel_<timestamp>.json

Usage:
    python insights/fetch_rtravel_test.py

Requirements:
    - APIFY_TOKEN in .env
    - pip install flashtext pycountry geonamescache
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
from dotenv import load_dotenv

load_dotenv()

APIFY_TOKEN = os.getenv("APIFY_TOKEN")
OUTPUT_DIR = Path("insights/data")
MAX_ITEMS = 300

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("rtravel_test")


# ── BUILD LOCATION LISTS + FLASHTEXT PROCESSOR ───────────────────────────────

def build_processor():
    """Build FlashText processor and location lists from pycountry + geonamescache."""
    cities = []
    countries = []

    # Countries from pycountry
    for country in pycountry.countries:
        countries.append(country.name)
        if hasattr(country, 'common_name'):
            countries.append(country.common_name)

    # Cities from geonamescache
    gc = geonamescache.GeonamesCache()
    for city in gc.get_cities().values():
        name = city.get("name", "")
        if name:
            cities.append(name)

    # Build FlashText processor — case insensitive
    processor = KeywordProcessor(case_sensitive=False)
    for city in cities:
        processor.add_keyword(city, f"City:{city}")
    for country in countries:
        processor.add_keyword(country, f"Country:{country}")

    log.info(f"FlashText processor built: {len(cities)} cities, {len(countries)} countries")
    return processor, cities, countries


log.info("Building location processor...")
PROCESSOR, ALL_CITIES, ALL_COUNTRIES = build_processor()


# ── HELPERS ───────────────────────────────────────────────────────────────────

def make_doc_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def extract_post_id(url: str) -> str:
    """Extract Reddit post ID from URL e.g. /comments/abc123/ -> abc123"""
    match = re.search(r'/comments/([a-z0-9]+)/', url)
    return match.group(1) if match else make_doc_id(url)


def get_type(url: str) -> str:
    """Determine if URL is a post or comment based on URL structure."""
    parts = [p for p in url.rstrip('/').split('/') if p]
    comments_idx = next((i for i, p in enumerate(parts) if p == 'comments'), None)
    if comments_idx is None:
        return "post"
    after_comments = parts[comments_idx + 1:]
    return "comment" if len(after_comments) >= 3 else "post"


def extract_locations(text: str) -> dict:
    """Extract cities and countries from text using FlashText."""
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
    """Check if title mentions any known city or country."""
    locs = extract_locations(title)
    return bool(locs["cities"] or locs["countries"])


# ── APIFY FETCH ───────────────────────────────────────────────────────────────

def fetch_rtravel() -> list:
    if not APIFY_TOKEN:
        log.error("APIFY_TOKEN not set in .env")
        return []

    log.info(f"Fetching up to {MAX_ITEMS} posts from r/travel...")

    try:
        response = requests.post(
            f"https://api.apify.com/v2/acts/trudax~reddit-scraper-lite/runs?token={APIFY_TOKEN}",
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
                f"https://api.apify.com/v2/actor-runs/{apify_run_id}?token={APIFY_TOKEN}",
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
            f"https://api.apify.com/v2/actor-runs/{apify_run_id}/dataset/items?token={APIFY_TOKEN}",
            timeout=30
        )
        items = items_resp.json()

        if not isinstance(items, list):
            log.error("Unexpected response format")
            return []

        # ── First pass: process posts, build post_map ─────────────────────────
        post_map = {}  # post_id -> {locations, title}
        raw_items = []
        dropped_non_reddit = 0
        dropped_no_location = 0

        for item in items:
            url = item.get("url", "") or ""
            title = item.get("title", "") or ""
            text = item.get("body", "") or item.get("selftext", "") or ""
            published_at = item.get("createdAt", "") or item.get("created", "") or ""

            if "reddit.com" not in url.lower():
                dropped_non_reddit += 1
                continue

            doc_type = get_type(url)
            post_id = extract_post_id(url)

            if doc_type == "post":
                if not title_has_location(title):
                    dropped_no_location += 1
                    log.debug(f"No location in title: {title[:60]}")
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
                # Inherit title from parent post if missing
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

            loc = doc.get("locations", {})
            log.info(
                f"✓ [{doc_type}] cities={loc.get('cities', [])} countries={loc.get('countries', [])} | "
                f"{doc.get('title', '')[:60]}"
            )
            final.append(doc)

        log.info(
            f"\nTotal kept: {len(final)} | "
            f"Dropped (non-Reddit): {dropped_non_reddit} | "
            f"Dropped (no location in title): {dropped_no_location}"
        )
        return final

    except Exception as e:
        log.error(f"Fetch error: {e}")
        return []


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("r/travel TEST FETCH")
    log.info(f"Max posts:  {MAX_ITEMS}")
    log.info(f"Filter:     title must mention a city or country")
    log.info(f"Output:     insights/data/")
    log.info("=" * 60)

    docs = fetch_rtravel()

    if not docs:
        log.error("No documents fetched")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"rtravel_{timestamp}.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2, ensure_ascii=False)

    posts = [d for d in docs if d["type"] == "post"]
    comments = [d for d in docs if d["type"] == "comment"]
    inherited = [d for d in comments if d.get("location_source") == "inherited_from_post"]

    log.info("=" * 60)
    log.info(f"Total docs:          {len(docs)}")
    log.info(f"Posts:               {len(posts)}")
    log.info(f"Comments:            {len(comments)}")
    log.info(f"Inherited locations: {len(inherited)}")
    log.info(f"Saved → {out_path}")
    log.info("Check the data before pushing to MongoDB")
    log.info("=" * 60)


if __name__ == "__main__":
    main()