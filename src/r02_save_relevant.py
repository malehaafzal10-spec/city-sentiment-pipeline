"""
process_mongo_sentiment.py — Script to fetch posts from MongoDB,
analyze them with Groq, and save relevant ones to a new collection.

Requirements:
    - MONGO_URI in .env
    - MONGO_DB_NAME in .env
    - GROQ_API_KEY in .env

Flags:
    TEST_MODE (bool): When True, processes only the first 10 posts and
                      saves results to a local JSON file instead of MongoDB.
"""

import os
import sys
import argparse
import json
import time
import logging
import requests
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# Configuration & Setup
# ==========================================

# Groq API Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
SOURCE_COLLECTION = "r01_reddit_posts_raw_final"
TARGET_COLLECTION = "reddit_relevant"

# ==========================================
# Test Mode
# ==========================================
TEST_MODE = False
TEST_LIMIT = 10
TEST_OUTPUT_FILE = "test_output.json"
TEST_FIXTURE_FILE = "test_fixture.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("process_mongo_data")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is not set.")
if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable is not set.")

class GroqLimitError(Exception):
    """Custom exception raised when Groq API key limits or quota are hit."""
    pass

PROMPT_TEMPLATE = """You are an expert sentiment analyst specializing in travel reviews. 

Your task is to read the title and text of a Reddit travel post and do two things:
1. Categorize the intent of the post (review vs. help).
2. Determine if the post's comments are worth scraping based on its relevance to general tourism.
3. Identify all relevant travel aspects discussed and evaluate the sentiment for each.

INSTRUCTIONS:
- relevant: Evaluate the title and overall content. Set this to "yes" if the post contains relevant information, tips, or experiences about a tourist destination. Set this to "no" if the post is primarily a complaint about specific services (e.g., an airline lost bag, a specific hotel booking error) or information not relevant to a general tourist (e.g. car rental services, eSIM, insurance).
- text_type: Categorize the overall intent of the post. Set to "review" if the user is sharing an experience or opinion about a location they have visited. Set to "help" if the text is primarily asking for recommendations, advice, or assistance for an upcoming trip.
- aspects: For every travel aspect found in the text, extract:
  - aspect: The general category (e.g., "transportation", "nature", "food", "accommodation").
  - sentiment_score: A rating from 1 to 5 (1 = very negative, 3 = neutral, 5 = very positive).
  - city: The specific city associated with the aspect.
  - country: The country associated with the aspect (infer this if only the city is mentioned).

OUTPUT FORMAT:
Return strictly a single JSON object. Do not include markdown formatting like ```json or any conversational text.

EXAMPLE:
Title: "Traveling to Dhërmi, Albania"
... (omitted for brevity, assume the full example here from your code)
{   
  "text_type": "review",
  "relevant": "yes",
  "aspects": [
    {
      "aspect": "aspect1",
      "sentiment_score": 4,
      "city": "Dhermi",
      "country": "Albania"
    }
  ]
}

Now analyze the following post:
"""

# ==========================================
# Core Processing Logic
# ==========================================
def analyze_post(title, text, max_retries=5):
    """
    Sends the title and text to the Groq API and returns parsed JSON object.
    Raises GroqLimitError if the API key is invalid, quota is exceeded, or 
    if retries are exhausted.
    """

    user_content = f"Title: \"{title}\"\nText: \"{text}\""
    full_prompt = f"{PROMPT_TEMPLATE}\n\n{user_content}"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": full_prompt}],
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(GROQ_URL, headers=headers, json=payload)

            # ── Check for hard API issues (quota, auth) ─────────────
            if response.status_code in (401, 402, 403):
                raise GroqLimitError(f"API Key or Quota issue. Status: {response.status_code}. Details: {response.text}")

            # ── Rate limit: respect Retry-After header ──────────────
            if response.status_code == 429:
                # Distinguish between rate limit and hard quota limit
                try:
                    err_msg = response.json().get("error", {}).get("message", "").lower()
                    if "quota" in err_msg or "billing" in err_msg or "insufficient" in err_msg:
                        raise GroqLimitError(f"Groq API quota exceeded: {err_msg}")
                except ValueError:
                    pass

                MAX_RETRY_WAIT = 60
                raw_retry_after = int(response.headers.get("Retry-After", 0))
                if raw_retry_after > 0:
                    wait = min(raw_retry_after, MAX_RETRY_WAIT)
                else:
                    wait = min(2 ** attempt, MAX_RETRY_WAIT)
                    
                log.warning(f"Rate limit hit (attempt {attempt}/{max_retries}). Waiting {wait}s before retry...")
                time.sleep(wait)
                continue

            # ── Transient server errors ──────────────────────────────
            if response.status_code in (500, 502, 503, 504):
                wait = min(2 ** attempt, 60)
                log.warning(f"Server error {response.status_code} (attempt {attempt}/{max_retries}). Waiting {wait}s...")
                time.sleep(wait)
                continue

            response.raise_for_status()

            response_data = response.json()
            raw_content = response_data["choices"][0]["message"]["content"]

            start_idx = raw_content.find('{')
            end_idx = raw_content.rfind('}')

            if start_idx != -1 and end_idx != -1:
                raw_content = raw_content[start_idx:end_idx + 1]
            else:
                raw_content = raw_content.strip()

            return json.loads(raw_content)

        except requests.exceptions.RequestException as e:
            wait = min(2 ** attempt, 60)
            log.error(f"Network/API error on attempt {attempt}/{max_retries}: {e}. Waiting {wait}s...")
            time.sleep(wait)
        except json.JSONDecodeError as e:
            log.error(f"JSON parse error (attempt {attempt}/{max_retries}): {e}")
            return {"relevant": "no", "aspects": []}
        except KeyError as e:
            log.error(f"Unexpected API response structure: {e}")
            return {"relevant": "no", "aspects": []}

    # Exhausted all retries (likely persistent 429 that wasn't caught as a quota error)
    raise GroqLimitError(f"All {max_retries} attempts exhausted due to persistent API limits.")


def get_unprocessed_run_ids(db) -> list:
    """
    Returns list of run_ids from SOURCE_COLLECTION that have no entries in TARGET_COLLECTION yet.
    Ordered oldest first so we always process in chronological order.
    """
    all_run_ids = db[SOURCE_COLLECTION].distinct("run_id")
    processed_run_ids = set(db[TARGET_COLLECTION].distinct("run_id"))
    unprocessed = [r for r in all_run_ids if r not in processed_run_ids]
    unprocessed.sort()  # oldest first
    return unprocessed


def process_run_id(db, run_id: str):
    """Process all posts for a single run_id."""

    # Derive date string from run_id for querying published_at
    # run_id format: run-YYYYMMDD-AUTO or run_YYYYMMDD_local
    import re
    match = re.search(r"(\d{8})", run_id)
    if not match:
        log.error(f"Cannot extract date from run_id: {run_id}")
        return
    date_compact = match.group(1)
    db_date_str = f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}"

    log.info("=" * 60)
    log.info(f"Processing run_id: {run_id}")
    log.info(f"Date: {db_date_str}")
    log.info("=" * 60)

    date_query = {"published_at": {"$regex": f"^{db_date_str}"}}
    posts = list(db[SOURCE_COLLECTION].find(date_query))

    if not posts:
        log.info(f"No posts found in '{SOURCE_COLLECTION}' for date {db_date_str}.")
        return

    log.info(f"Found {len(posts)} posts for {db_date_str}.")

    # ── Skip already-processed doc_ids for this run_id ───────────────────
    already_processed = set(
        doc["doc_id"] for doc in db[TARGET_COLLECTION].find(
            {"run_id": run_id}, {"doc_id": 1}
        )
    )
    if already_processed:
        before = len(posts)
        posts = [p for p in posts if p.get("doc_id") not in already_processed]
        log.info(f"Skipping {before - len(posts)} already-processed posts. {len(posts)} remaining.")

    if not posts:
        log.info(f"All posts for run_id '{run_id}' already processed.")
        return

    total_posts     = len(posts)
    total_processed = 0
    total_saved     = 0
    operations      = []

    for idx, post in enumerate(posts):
        doc_id = post.get('doc_id', post.get('post_id', f"unknown_{idx}"))
        log.info(f"Processing post {idx + 1}/{total_posts}: {doc_id}...")

        title = post.get('title', '')
        text  = post.get('text', '')

        if not title and not text:
            analysis_result = {"relevant": "no", "aspects": []}
        else:
            try:
                analysis_result = analyze_post(title, text)
            except GroqLimitError as e:
                log.error(f"❌ GROQ API LIMITATION ENCOUNTERED: {e}")
                log.info("Stopping execution. Saving processed posts so far...")
                break
            time.sleep(6)

        post['analysis'] = analysis_result
        total_processed += 1

        if analysis_result.get("relevant", "").lower() == "yes":
            post.pop('_id', None)
            post['run_id'] = run_id
            operations.append(
                UpdateOne({"doc_id": doc_id}, {"$set": post}, upsert=True)
            )
            total_saved += 1

        if len(operations) >= 50:
            db[TARGET_COLLECTION].bulk_write(operations)
            operations = []

    if operations:
        log.info(f"Flushing {len(operations)} remaining operations...")
        db[TARGET_COLLECTION].bulk_write(operations)

    log.info("=" * 60)
    log.info(f"SUMMARY — {run_id}")
    log.info(f"Posts found:      {total_posts}")
    log.info(f"Posts processed:  {total_processed}")
    log.info(f"Relevant saved:   {total_saved}")
    if total_processed > 0:
        log.info(f"Relevancy rate:   {(total_saved / total_processed) * 100:.2f}%")
    log.info("=" * 60)


def main():
    log.info("=" * 60)
    log.info("R02 — RELEVANCE FILTER ON POSTS")

    parser = argparse.ArgumentParser(description="Process Reddit posts — auto-detects unprocessed run_ids.")
    parser.add_argument("--date", required=False, default=None,
                        help="Optional: force a specific date YYYYMMDD instead of auto-detecting")
    args = parser.parse_args()

    # ── MongoDB setup ───────────────────────────────────────────────────────
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        db = client[DB_NAME]
        log.info("MongoDB connection OK ✓")
    except Exception as e:
        log.error(f"MongoDB connection failed: {e}")
        return

    # ── Determine which run_ids to process ──────────────────────────────────
    if args.date:
        user_date = args.date
        if len(user_date) != 8 or not user_date.isdigit():
            log.error("Invalid date format. Use YYYYMMDD.")
            sys.exit(1)
        cutoff = "20260601"
        run_ids_to_process = [
            f"run_{user_date}_local" if user_date <= cutoff else f"run-{user_date}-AUTO"
        ]
        log.info(f"Manual override: processing run_id {run_ids_to_process[0]}")
    else:
        run_ids_to_process = get_unprocessed_run_ids(db)
        if not run_ids_to_process:
            log.info("✅ All run_ids already processed. Nothing to do.")
            return
        log.info(f"Found {len(run_ids_to_process)} unprocessed run_id(s): {run_ids_to_process}")

    log.info("=" * 60)

    for run_id in run_ids_to_process:
        process_run_id(db, run_id)

    log.info("ALL DONE")

if __name__ == "__main__":
    main()