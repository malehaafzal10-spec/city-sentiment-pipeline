"""
fetch_rtravel_test.py — Test script to scrape r/travel, extract locations,
filter for relevance, and save results locally for inspection.

Does NOT push to MongoDB — local JSON output only so you can check the data first.

Output saved to: insights/data/rtravel_test_<timestamp>.json

Usage:
    python insights/fetch_rtravel_test.py

Requirements:
    - APIFY_TOKEN in .env
    - GROQ_API_KEY in .env
"""

import os
import json
import time
import hashlib
import logging
import requests
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

APIFY_TOKEN = os.getenv("APIFY_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"

OUTPUT_DIR = Path("insights/data")
MAX_ITEMS = 100  # number of posts to fetch from r/travel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("rtravel_test")


def make_doc_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


# ── APIFY FETCH ───────────────────────────────────────────────────────────────

def fetch_rtravel() -> list:
    if not APIFY_TOKEN:
        log.error("APIFY_TOKEN not set in .env")
        return []

    log.info(f"Fetching {MAX_ITEMS} posts from r/travel via Apify...")

    try:
        response = requests.post(
            f"https://api.apify.com/v2/acts/trudax~reddit-scraper-lite/runs?token={APIFY_TOKEN}",
            json={
                "startUrls": [
                    {"url": "https://www.reddit.com/r/travel/"}
                ],
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
            log.error(f"Unexpected response format: {type(items)}")
            return []

        # Keep only actual Reddit posts
        raw = []
        skipped = 0
        for item in items:
            url = item.get("url", "") or ""
            if "reddit.com" not in url.lower():
                skipped += 1
                continue
            raw.append({
                "doc_id": make_doc_id(url),
                "url": url,
                "title": item.get("title", "") or "",
                "text": item.get("body", "") or item.get("selftext", "") or "",
                "published_at": item.get("createdAt", "") or item.get("created", "") or "",
            })

        log.info(f"Fetched {len(raw)} Reddit posts ({skipped} non-Reddit URLs dropped)")
        return raw

    except Exception as e:
        log.error(f"Fetch error: {e}")
        return []


# ── LLM: LOCATION EXTRACTION + RELEVANCE ─────────────────────────────────────

SYSTEM_PROMPT = """You are a travel content analyser.

Given a Reddit post from r/travel, do two things:
1. Decide if the post is genuinely about travelling to or experiencing a specific destination
2. If yes, extract the location(s) mentioned (city, country, or region)

Relevant posts:
- Personal travel experiences, trip reports, travel questions
- Tips, recommendations, itineraries for a specific place
- Asking for or giving advice about visiting somewhere
- Opinions about a destination (safety, cost, crowds, vibe)

NOT relevant:
- General travel discussion not about a specific place
- Gear, visas, insurance, flights not tied to a destination
- Memes, jokes, meta posts about r/travel itself

Respond ONLY with valid JSON, nothing else:
{"relevant": "yes", "locations": [{"name": "Paris", "type": "city", "country": "France"}, {"name": "France", "type": "country"}], "reason": "short explanation"}
or
{"relevant": "no", "locations": [], "reason": "short explanation"}

For type use: "city", "country", or "region". Extract ALL specific locations mentioned."""


def extract_location_and_relevance(title: str, text: str) -> dict:
    if not GROQ_API_KEY:
        return {"relevant": "unknown", "locations": [], "reason": "no groq key"}

    content = f"Title: {title}\nPost: {text[:600]}"

    try:
        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": GROQ_MODEL,
                "temperature": 0,
                "max_tokens": 200,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": content}
                ]
            },
            timeout=15
        )
        raw = response.json()["choices"][0]["message"]["content"].strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        return json.loads(raw)

    except Exception as e:
        log.warning(f"LLM error: {e}")
        return {"relevant": "unknown", "locations": [], "reason": f"error: {e}"}


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("r/travel TEST FETCH")
    log.info(f"Max posts: {MAX_ITEMS}")
    log.info(f"Output:    insights/data/")
    log.info("=" * 60)

    if not APIFY_TOKEN:
        log.error("APIFY_TOKEN missing — cannot continue")
        return

    # ── Step 1: Fetch from Apify ──────────────────────────────────────────────
    raw_posts = fetch_rtravel()

    if not raw_posts:
        log.error("No posts fetched — check Apify token")
        return

    # ── Step 2: Location extraction + relevance filtering ────────────────────
    log.info(f"\nRunning location extraction on {len(raw_posts)} posts...")

    results = []
    relevant_count = 0
    irrelevant_count = 0

    for i, post in enumerate(raw_posts):
        log.info(f"[{i+1}/{len(raw_posts)}] {post['title'][:60]}")

        analysis = extract_location_and_relevance(post["title"], post["text"])

        post["relevant"] = analysis.get("relevant", "unknown")
        post["locations"] = analysis.get("locations", [])
        post["llm_reason"] = analysis.get("reason", "")
        post["processed_at"] = datetime.now(timezone.utc).isoformat()

        results.append(post)

        if post["relevant"] == "yes":
            relevant_count += 1
            loc_names = [l.get("name") for l in post["locations"]]
            log.info(f"  ✓ RELEVANT | locations: {loc_names}")
        else:
            irrelevant_count += 1
            log.info(f"  ✗ NOT RELEVANT | {post['llm_reason']}")

        time.sleep(1.5)  # Groq rate limit

    # ── Step 3: Save locally ──────────────────────────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # Full results (all posts)
    full_path = OUTPUT_DIR / f"rtravel_all_{timestamp}.json"
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Relevant only
    relevant_only = [r for r in results if r["relevant"] == "yes"]
    relevant_path = OUTPUT_DIR / f"rtravel_relevant_{timestamp}.json"
    with open(relevant_path, "w", encoding="utf-8") as f:
        json.dump(relevant_only, f, indent=2, ensure_ascii=False)

    # ── Summary ───────────────────────────────────────────────────────────────
    log.info("\n" + "=" * 60)
    log.info("DONE")
    log.info(f"Total fetched:    {len(raw_posts)}")
    log.info(f"Relevant:         {relevant_count} ({relevant_count/len(raw_posts)*100:.0f}%)")
    log.info(f"Not relevant:     {irrelevant_count}")
    log.info(f"All results:      {full_path}")
    log.info(f"Relevant only:    {relevant_path}")
    log.info("=" * 60)
    log.info("Check the JSON files in insights/data/ before pushing to MongoDB")


if __name__ == "__main__":
    main()