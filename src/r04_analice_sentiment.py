"""
process_mongo_sentiment.py — Script to fetch comments from MongoDB,
analyze them with Groq API, and save relevant ones to a new collection.

Requirements:
    - MONGO_URI in .env
    - MONGO_DB_NAME in .env
    - GROQ_API_KEY in .env

Usage in Pipeline:
    python r04_analice_sentiment.py --date 20260526
"""

import os
import sys
import json
import time
import logging
import requests
import argparse
import re
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv

load_dotenv(override=True)

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
SOURCE_COLLECTION = "reddit_comments_final"
TARGET_COLLECTION = "reddit_comments_relevant"

# ==========================================
# Test Mode
# ==========================================
TEST_MODE = False
TEST_LIMIT = 10
TEST_OUTPUT_FILE = "test_output.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("process_mongo_data")

if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable is not set.")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is not set. Required for Groq API.")

class GroqConnectionError(Exception):
    """Custom exception raised when Groq API fails repeatedly."""
    pass

PROMPT_TEMPLATE = """You are an expert sentiment analyst specializing in travel reviews. 

Your task is to read the text of a Reddit travel post and do the following:

1. Determine if the comments are relevant to general tourism.
2. Identify all relevant travel aspects discussed and evaluate the sentiment for each.

INSTRUCTIONS:
- relevant:
    -Set to "yes" if the post contains relevant information, tips, or firsthand experiences about a tourist destination.
    -Set to "no" if the text only expresses gratitude, praises photos, or lacks any actual opinion or insight about the destination.
- aspects: For every travel aspect found in the text, extract:
  - aspect: The general category relevant for tourism. 
  - sentiment_score: A rating from 1 to 5 (1 = very negative, 3 = neutral, 5 = very positive).
  - city: The specific city associated with the aspect.
  - country: The country associated with the aspect (infer this if only the city is mentioned).

OUTPUT FORMAT:
Return strictly a single JSON object. Do not include markdown formatting like ```json or any conversational text.

EXAMPLE:
Title: "Traveling to Dhërmi, Albania"
{   
  "relevant": "yes",
  "aspects": [
    {
      "aspect": "aspect1",
      "sentiment_score": 4,
      "city": "Dhërmi",
      "country": "Albania"
    }
  ]
}

Now analyze the following post:
"""

# ==========================================
# Core Processing Logic
# ==========================================
def analyze_post(text, max_retries=4):
    """
    Sends the text to the Groq API and returns parsed JSON object.
    """
    user_content = f"Text: \"{text}\""
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
            # 30-second timeout is generally enough for cloud APIs
            response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)
            
            # Catch Rate Limits (429) specifically to back off longer
            if response.status_code == 429:
                wait_time = 15 * attempt
                log.warning(f"Groq Rate Limit (429) hit. Backing off for {wait_time}s...")
                time.sleep(wait_time)
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
            wait = 5 * attempt
            log.warning(f"Groq API error on attempt {attempt}/{max_retries}: {e}. Waiting {wait}s...")
            time.sleep(wait)
        except json.JSONDecodeError as e:
            log.error(f"JSON parse error (attempt {attempt}/{max_retries}): {e}")
            return {"relevant": "no", "aspects": []}
        except KeyError as e:
            log.error(f"Unexpected API response structure: {e}")
            return {"relevant": "no", "aspects": []}

    raise GroqConnectionError(f"Failed to connect to Groq API after {max_retries} attempts.")


def main():
    log.info("=" * 60)
    log.info("PROCESS MONGO COMMENTS WITH GROQ API")
    
    # ── Handle Required pipeline argument ───────────────────────────────────
    parser = argparse.ArgumentParser(description="Process Reddit comments.")
    parser.add_argument(
        "--date", 
        type=str, 
        required=True,
        help="Target date in YYYYMMDD format to match the run_id (e.g., 20260526)"
    )
    args = parser.parse_args()
    user_date = args.date

    if not re.match(r"^\d{8}$", user_date):
        log.error("Invalid date format. Must be YYYYMMDD.")
        sys.exit(1)

    # Output formatting logic: forcing run_YYYYMMDD_local
    output_run_id = f"run_{user_date}_local"

    log.info(f"Target Date:             {user_date}")
    log.info(f"Output Run ID:           {output_run_id}")

    # ── MongoDB setup ───────────────────────────────────────────────────────
    db = None
    if not TEST_MODE:
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            client.server_info()
            db = client[DB_NAME]
        except Exception as e:
            log.error(f"MongoDB connection failed: {e}")
            return

    # ── Fetch comments filtered by Date Prefix ───────────────────────────────
    # Look for any incoming run_id that starts with 'run_YYYYMMDD' 
    search_query = {"run_id": {"$regex": f"^run_{user_date}"}}

    if TEST_MODE:
        posts = None
        try:
            test_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            test_client.server_info()
            db_temp = test_client[DB_NAME]
            posts = list(db_temp[SOURCE_COLLECTION].find(search_query).limit(TEST_LIMIT))
        except Exception as e:
            log.warning(f"MongoDB unavailable in TEST_MODE. Trying local fixture...")
    else:
        posts = list(db[SOURCE_COLLECTION].find(search_query))

    total_posts = len(posts)

    if total_posts == 0:
        log.info(f"No posts found matching date {user_date} in '{SOURCE_COLLECTION}'.")
        return

    log.info(f"Found {total_posts} comments from this run to process.")
    
    # ── Prevent Re-processing Already Processed Comments ────────────────────
    existing_docs = set()
    if not TEST_MODE:
        # Check target collection to find docs already processed for THIS exact output_run_id
        existing_docs = {
            doc["doc_id"] for doc in db[TARGET_COLLECTION].find({"run_id": output_run_id}, {"doc_id": 1})
        }
        if existing_docs:
            log.info(f"Identified {len(existing_docs)} comments already processed in a previous execution. Skipping them.")

    log.info("=" * 60)

    total_processed = 0
    total_saved = 0
    total_skipped = 0
    operations = []
    test_results = []

    for idx, post in enumerate(posts):
        doc_id = post.get('doc_id', post.get('post_id', f"unknown_{idx}"))
        
        # Skip logic
        if doc_id in existing_docs:
            log.info(f"Skipping comment {idx + 1}/{total_posts}: {doc_id} (Already processed)")
            total_skipped += 1
            continue

        log.info(f"Processing comment {idx + 1}/{total_posts}: {doc_id}...")

        text = post.get('text', '')

        if not text:
            analysis_result = {"relevant": "no", "aspects": []}
        else:
            try:
                analysis_result = analyze_post(text)
            except GroqConnectionError as e:
                log.error(f"❌ GROQ API ERROR: {e}")
                log.info("Stopping execution. Will save all currently processed posts...")
                break
            
            # Pacing to avoid hitting Groq's Requests Per Minute (RPM) limits
            if not TEST_MODE:
                time.sleep(6) 

        post['analysis'] = analysis_result
        total_processed += 1

        # ── Check relevance and attach RUN_ID ──────────────────────────────
        if analysis_result.get("relevant", "").lower() == "yes":
            post.pop('_id', None)
            
            # Explicitly force the normalized run_id on save
            post['run_id'] = output_run_id

            # ── Extract cities and countries for top-level access ──────────
            aspects = analysis_result.get("aspects")
            if not isinstance(aspects, list):
                aspects = []
                
            mentioned_cities = list({str(a.get("city")) for a in aspects if isinstance(a, dict) and a.get("city")})
            mentioned_countries = list({str(a.get("country")) for a in aspects if isinstance(a, dict) and a.get("country")})
            
            post['mentioned_cities'] = mentioned_cities
            post['mentioned_countries'] = mentioned_countries
            
            if mentioned_cities:
                log.info(f"Relevant comment analyzed! Cities extracted: {mentioned_cities}")
            # ───────────────────────────────────────────────────────────────

            if TEST_MODE:
                test_results.append(post)
            else:
                operations.append(
                    UpdateOne({"doc_id": doc_id}, {"$set": post}, upsert=True)
                )
            total_saved += 1

        # ── Batch write ─────────────────────────────────────────────────────
        if not TEST_MODE and len(operations) >= 50:
            db[TARGET_COLLECTION].bulk_write(operations)
            operations = []

    # ── Flush remaining writes ──────────────────────────────────────────────
    if not TEST_MODE and operations:
        log.info(f"Flushing {len(operations)} remaining operations to MongoDB...")
        db[TARGET_COLLECTION].bulk_write(operations)

    # ── Test mode: save locally ─────────────────────────────────────────────
    if TEST_MODE:
        with open(TEST_OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(test_results, f, indent=2, default=str)
        log.info(f"Test results saved to '{TEST_OUTPUT_FILE}'.")

    # ── Summary ─────────────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("PROCESSING SUMMARY")
    log.info(f"Output Run ID:           {output_run_id}")
    log.info(f"Total Comments Found:    {total_posts}")
    log.info(f"Total Already Skipped:   {total_skipped}")
    log.info(f"Total Comments Processed:{total_processed}")
    log.info(f"Total Relevant Saved:    {total_saved}")
    if total_processed > 0:
        log.info(f"Relevancy Rate:          {(total_saved / total_processed) * 100:.2f}%")
    log.info("=" * 60)

if __name__ == "__main__":
    main()