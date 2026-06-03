"""
process_mongo_sentiment.py — Script to fetch posts from MongoDB,
analyze them with a local vLLM server, and save relevant ones to a new collection.

Requirements:
    - MONGO_URI in .env
    - MONGO_DB_NAME in .env

Usage in SLURM:
    python r02_save_relevant.py --date 20260526
"""

import os
import sys
import json
import time
import logging
import requests
import argparse
from datetime import datetime
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# Configuration & Setup
# ==========================================

# Local vLLM Configuration (Matching Scenario B)
VLLM_API_KEY = "local-execution" 
VLLM_MODEL = "casperhansen/llama-3.3-70b-instruct-awq"
VLLM_URL = "http://localhost:8000/v1/chat/completions"

# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
SOURCE_COLLECTION = "reddit_posts_final"
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

if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable is not set.")

class VLLMConnectionError(Exception):
    """Custom exception raised when local vLLM server is unreachable."""
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
  - aspect: The general category relevant for tourism. 
  - sentiment_score: A rating from 1 to 5 (1 = very negative, 3 = neutral, 5 = very positive).
  - city: The specific city associated with the aspect.
  - country: The country associated with the aspect (infer this if only the city is mentioned).

OUTPUT FORMAT:
Return strictly a single JSON object. Do not include markdown formatting like ```json or any conversational text.

EXAMPLE:
Title: "Traveling to Dhërmi, Albania"
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
def analyze_post(title, text, max_retries=3):
    """
    Sends the title and text to the local vLLM API and returns parsed JSON object.
    """
    user_content = f"Title: \"{title}\"\nText: \"{text}\""
    full_prompt = f"{PROMPT_TEMPLATE}\n\n{user_content}"

    headers = {
        "Authorization": f"Bearer {VLLM_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": VLLM_MODEL,
        "messages": [{"role": "user", "content": full_prompt}],
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(VLLM_URL, headers=headers, json=payload, timeout=600)
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
            wait = 5
            log.warning(f"Local vLLM error on attempt {attempt}/{max_retries}: {e}. Waiting {wait}s...")
            time.sleep(wait)
        except json.JSONDecodeError as e:
            log.error(f"JSON parse error (attempt {attempt}/{max_retries}): {e}")
            return {"relevant": "no", "aspects": []}
        except KeyError as e:
            log.error(f"Unexpected API response structure: {e}")
            return {"relevant": "no", "aspects": []}

    raise VLLMConnectionError(f"Failed to connect to local vLLM after {max_retries} attempts.")


def main():
    log.info("=" * 60)
    log.info("PROCESS MONGO POSTS WITH LOCAL VLLM")
    
    # ── Handle SLURM arguments for date input ──────────────────────────────
    parser = argparse.ArgumentParser(description="Process Reddit posts for a specific date.")
    parser.add_argument(
        "--date", 
        type=str, 
        help="Publication date to process (YYYYMMDD). Defaults to today.", 
        default=datetime.now().strftime("%Y%m%d")
    )
    args = parser.parse_args()
    user_date = args.date

    if len(user_date) != 8 or not user_date.isdigit():
        log.error("Invalid date format. Must be YYYYMMDD.")
        sys.exit(1)
        
    db_date_str = f"{user_date[:4]}-{user_date[4:6]}-{user_date[6:8]}"
    run_id = f"run_{user_date}_local"

    log.info(f"Targeting Run ID: {run_id}")
    log.info(f"Searching for posts starting with date: {db_date_str}")
    log.info("=" * 60)

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

    # ── Fetch posts filtered by Date ─────────────────────────────────────────
    date_query = {"published_at": {"$regex": f"^{db_date_str}"}}

    if TEST_MODE:
        posts = None
        try:
            test_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            test_client.server_info()
            db_temp = test_client[DB_NAME]
            posts = list(db_temp[SOURCE_COLLECTION].find(date_query).limit(TEST_LIMIT))
        except Exception as e:
            log.warning(f"MongoDB unavailable in TEST_MODE. Trying local fixture...")

        if posts is None:
            if os.path.exists(TEST_FIXTURE_FILE):
                with open(TEST_FIXTURE_FILE, "r", encoding="utf-8") as f:
                    all_fixture = json.load(f)
                posts = [p for p in all_fixture if str(p.get("published_at", "")).startswith(db_date_str)][:TEST_LIMIT]
            else:
                log.error("No MongoDB connection and no local fixture found.")
                return
    else:
        posts = list(db[SOURCE_COLLECTION].find(date_query))

    total_posts = len(posts)

    if total_posts == 0:
        log.info(f"No posts found in '{SOURCE_COLLECTION}' for date {db_date_str}.")
        return

    log.info(f"Found {total_posts} posts to process for {db_date_str}.")

    total_processed = 0
    total_saved = 0
    operations = []
    test_results = []

    for idx, post in enumerate(posts):
        doc_id = post.get('doc_id', post.get('post_id', f"unknown_{idx}"))
        log.info(f"Processing post {idx + 1}/{total_posts}: {doc_id}...")

        title = post.get('title', '')
        text = post.get('text', '')

        if not title and not text:
            analysis_result = {"relevant": "no", "aspects": []}
        else:
            try:
                analysis_result = analyze_post(title, text)
            except VLLMConnectionError as e:
                log.error(f"❌ LOCAL SERVER ERROR: {e}")
                log.info("Stopping execution. Will save all currently processed posts...")
                break  

            # time.sleep(6) -- REMOVED: Local LLM doesn't need artificial rate limit delays

        post['analysis'] = analysis_result
        total_processed += 1

        # ── Check relevance and attach RUN_ID ──────────────────────────────
        if analysis_result.get("relevant", "").lower() == "yes":
            post.pop('_id', None)
            post['run_id'] = run_id  

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
    log.info(f"Run ID:                  {run_id}")
    log.info(f"Total Posts Found:       {total_posts}")
    log.info(f"Total Posts Processed:   {total_processed}")
    log.info(f"Total Relevant Saved:    {total_saved}")
    if total_processed > 0:
        log.info(f"Relevancy Rate:          {(total_saved / total_processed) * 100:.2f}%")
    log.info("=" * 60)

if __name__ == "__main__":
    main()