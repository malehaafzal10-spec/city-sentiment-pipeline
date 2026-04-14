"""
historical_preprocess.py — One-time script to process raw_documents_historical.

Two-stage relevance filtering:
  Stage 1 — Keyword filter (fast, free)
             Drops bots, wrong subreddits, non-travel content
  Stage 2 — Groq LLM filter (only on Stage 1 survivors)
             Checks if genuinely about visiting the city as a tourist

Safety features:
  - Tests MongoDB connection BEFORE doing any work
  - Saves all relevant docs to local JSON backup BEFORE pushing to MongoDB
  - Only relevant documents are pushed to processed_documents

Usage:
    python historical_preprocess.py

Requirements:
    - MONGO_URI in .env
    - MONGO_DB_NAME in .env
    - GROQ_API_KEY in .env
"""

import os
import re
import json
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"

RAW_COLLECTION = "raw_documents_historical"
PROCESSED_COLLECTION = "processed_documents"
BACKUP_DIR = Path("artifacts/historical")

MIN_TEXT_LENGTH = 40

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("historical_preprocess")

# ─── IRRELEVANT PATTERNS ──────────────────────────────────────────────────────

IRRELEVANT_PATTERNS = [
    # Bots and automoderator
    "i am a bot", "this action was performed automatically",
    "contact the moderators", "automoderator", "automod",
    "your post has been", "your post was", "this post has been locked",
    "this post was removed", "this submission has been",
    "subreddit rules", "please read the rules",
    # Wrong subreddits
    "m4f", "f4m", "m4m", "f4f", "r4r",
    "onlyfans", "hookup", "18+",
    # Irrelevant topics
    "airline", "business class", "first class seat", "flight deal", "airfare",
    "stock market", "share price", "quarterly earnings", "revenue report",
    "ipo", "merger", "acquisition", "hedge fund",
    "premier league", "champions league", "match result", "transfer window",
    "real estate", "mortgage", "property for sale",
    "job offer", "hiring", "job listing", "salary",
    "local election", "city council", "municipal",
]

RELEVANT_PATTERNS = [
    "tourist", "tourism", "travel", "traveller", "traveler",
    "visit", "visitor", "vacation", "holiday", "trip",
    "backpack", "sightseeing", "hotel", "hostel", "airbnb",
    "crowded", "crowds", "overtourism", "overrun",
    "expensive", "affordable", "cheap", "overpriced", "value",
    "safe", "unsafe", "pickpocket", "scam",
    "recommend", "avoid", "worth it", "overrated", "must see",
    "things to do", "best time to visit", "travel guide",
    "local tips", "hidden gem", "tourist trap", "day trip",
    "first time", "planning a trip", "going to", "spent a week",
    "just got back", "been to", "staying in", "accommodation",
    "itinerary", "budget", "solo travel", "backpacking",
]


# ─── MONGODB CONNECTION TEST ──────────────────────────────────────────────────

def test_mongodb_connection() -> bool:
    """Test MongoDB connection before doing any work."""
    if not MONGO_URI:
        log.error("[MongoDB] MONGO_URI not set in .env")
        return False
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        client.close()
        log.info("[MongoDB] Connection test passed ✓")
        return True
    except Exception as e:
        log.error(f"[MongoDB] Connection FAILED: {e}")
        log.error("[MongoDB] Make sure VPN is OFF and try again")
        return False


# ─── LOCAL BACKUP ─────────────────────────────────────────────────────────────

def save_local_backup(docs: list) -> Path:
    """Save relevant docs to local JSON before pushing to MongoDB."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"processed_relevant_{timestamp}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2, ensure_ascii=False, default=str)
    log.info(f"[Backup] {len(docs)} relevant docs saved locally → {path}")
    return path


# ─── STAGE 1: KEYWORD FILTER ──────────────────────────────────────────────────

def keyword_filter(title: str, text: str, city: str) -> tuple:
    """
    Fast keyword check. Returns (keep: bool, reason: str).
    Drops bots, wrong subreddits, irrelevant topics.
    Keeps only posts with a genuine travel signal.
    """
    combined = f"{title} {text}".lower()

    # Hard drop
    for pattern in IRRELEVANT_PATTERNS:
        if pattern in combined:
            return False, f"keyword_drop: '{pattern}'"

    # Must have travel signal
    for pattern in RELEVANT_PATTERNS:
        if pattern in combined:
            return True, f"keyword_keep: '{pattern}'"

    # City name present but no travel signal — send to Groq to decide
    if city.lower() in combined:
        return True, "keyword_keep: city present, sending to Groq"

    return False, "keyword_drop: no travel signal"


# ─── STAGE 2: GROQ LLM FILTER ─────────────────────────────────────────────────

def build_system_prompt(city: str) -> str:
    return f"""You are a travel content classifier.
Decide if this Reddit post is genuinely about travelling to, visiting, or experiencing {city} as a travel destination.

Relevant posts:
- Personal travel experiences in {city}
- Tips, recommendations, questions about visiting {city}
- Hotels, restaurants, attractions, costs in {city}
- Asking for advice about a trip to {city}
- Reviews or opinions about {city} as a destination
- Overtourism, crowding, safety for visitors in {city}

NOT relevant:
- Posts where {city} is briefly mentioned but topic is something else
- Local news, politics, crime unrelated to tourism
- Sports, business, dating posts
- Bot or automod messages

Respond ONLY with valid JSON:
{{"relevant": "yes", "reason": "short explanation"}}
or
{{"relevant": "no", "reason": "short explanation"}}"""


def groq_filter(title: str, text: str, city: str) -> tuple:
    """
    Groq LLM relevance check. Returns (keep: bool, reason: str).
    Falls back to keeping the post if Groq fails.
    """
    if not GROQ_API_KEY:
        return True, "groq_skipped: no API key"

    user_message = f"City: {city}\nTitle: {title}\nPost: {text[:400]}"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": GROQ_MODEL,
        "temperature": 0,
        "max_tokens": 80,
        "messages": [
            {"role": "system", "content": build_system_prompt(city)},
            {"role": "user", "content": user_message},
        ],
    }

    try:
        response = requests.post(GROQ_URL, headers=headers, json=body, timeout=15)
        response.raise_for_status()
        raw_text = response.json()["choices"][0]["message"]["content"].strip()

        try:
            result = json.loads(raw_text)
            is_relevant = result.get("relevant", "yes") == "yes"
            reason = result.get("reason", "")
            return is_relevant, f"groq: {reason}"
        except json.JSONDecodeError:
            log.warning(f"[Groq] Could not parse: {raw_text[:80]}")
            return True, "groq_parse_error: keeping"

    except Exception as e:
        log.warning(f"[Groq] Error: {e}")
        return True, "groq_error: keeping"


# ─── TEXT CLEANING ─────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"http\S+|www\.\S+", "", text)
    text = re.sub(r"\[\+\d+\s*chars\]", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_english(text: str) -> bool:
    try:
        from langdetect import detect
        return detect(text) == "en"
    except Exception:
        return True


# ─── SAVE TO MONGODB ──────────────────────────────────────────────────────────

def save_to_mongo(docs: list, db) -> bool:
    """
    Save ONLY relevant processed documents to processed_documents.
    Returns True if successful.
    """
    if not docs:
        log.warning("[MongoDB] No documents to save")
        return False

    try:
        operations = [
            UpdateOne(
                {"doc_id": d["doc_id"]},
                {"$set": d},
                upsert=True
            )
            for d in docs
        ]
        result = db[PROCESSED_COLLECTION].bulk_write(operations)
        log.info(
            f"[MongoDB] Saved {result.upserted_count + result.modified_count} "
            f"relevant documents to '{PROCESSED_COLLECTION}'"
        )

        # Save artifact record
        db["pipeline_artifacts"].insert_one({
            "run_id": "historical_bulk_backfill",
            "artifact_type": "historical_processed_docs",
            "timestamp": datetime.now(timezone.utc),
            "document_count": len(docs)
        })
        return True

    except Exception as e:
        log.error(f"[MongoDB] Save failed: {e}")
        return False


# ─── MAIN ──────────────────────────────────────────────────────────────────────

def run():
    log.info("=" * 60)
    log.info("HISTORICAL REDDIT PREPROCESSING")
    log.info(f"Source:      {RAW_COLLECTION}")
    log.info(f"Destination: {PROCESSED_COLLECTION}")
    log.info(f"Groq filter: {'enabled' if GROQ_API_KEY else 'DISABLED — no key'}")
    log.info("=" * 60)

    # ── Step 1: Test MongoDB connection first ──────────────────────────────────
    log.info("\n[Pre-flight] Testing MongoDB connection...")
    if not test_mongodb_connection():
        log.error("Aborting — fix MongoDB connection first (check VPN is OFF)")
        return

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    # ── Step 2: Load raw historical docs ──────────────────────────────────────
    raw_docs = list(db[RAW_COLLECTION].find({}))
    log.info(f"\nLoaded {len(raw_docs)} raw historical documents from MongoDB")

    if not raw_docs:
        log.error(f"No documents in '{RAW_COLLECTION}' — run historical_reddit_backfill.py first")
        client.close()
        return

    # Skip already processed docs
    already_processed = {
        doc["doc_id"]
        for doc in db[PROCESSED_COLLECTION].find(
            {"doc_id": {"$in": [d["doc_id"] for d in raw_docs]}},
            {"doc_id": 1}
        )
    }
    new_docs = [d for d in raw_docs if d["doc_id"] not in already_processed]
    log.info(f"{len(new_docs)} to process | {len(already_processed)} already done")

    if not new_docs:
        log.info("All documents already processed — nothing to do")
        client.close()
        return

    # ── Step 3: Filter and clean ───────────────────────────────────────────────
    relevant_docs = []
    seen_texts = set()
    processed_at = datetime.now(timezone.utc).isoformat()

    metrics = {
        "total": len(new_docs),
        "dropped_keyword": 0,
        "passed_keyword": 0,
        "groq_calls": 0,
        "dropped_groq": 0,
        "passed_groq": 0,
        "dropped_short": 0,
        "dropped_lang": 0,
        "dropped_dupe": 0
    }

    for i, doc in enumerate(new_docs):
        title = doc.get("title", "") or ""
        text = doc.get("text", "") or ""
        city = doc.get("city", "Unknown")

        if i % 100 == 0:
            log.info(
                f"[{i}/{len(new_docs)}] "
                f"relevant={len(relevant_docs)} | "
                f"groq_calls={metrics['groq_calls']} | "
                f"keyword_dropped={metrics['dropped_keyword']}"
            )

        # Stage 1: keyword filter
        kw_keep, kw_reason = keyword_filter(title, text, city)
        if not kw_keep:
            metrics["dropped_keyword"] += 1
            continue
        metrics["passed_keyword"] += 1

        # Stage 2: Groq LLM filter
        groq_keep, groq_reason = groq_filter(title, text, city)
        metrics["groq_calls"] += 1
        time.sleep(0.3)  # rate limit

        if not groq_keep:
            metrics["dropped_groq"] += 1
            log.debug(f"[Groq DROP] {city}: {title[:50]} — {groq_reason}")
            continue
        metrics["passed_groq"] += 1

        # Clean text
        combined = f"{title}. {text}".strip()
        clean = clean_text(combined)

        # Length filter
        if len(clean) < MIN_TEXT_LENGTH:
            metrics["dropped_short"] += 1
            continue

        # Language filter
        if not is_english(clean):
            metrics["dropped_lang"] += 1
            continue

        # Deduplication
        text_key = f"{city}:{clean[:120]}"
        if text_key in seen_texts:
            metrics["dropped_dupe"] += 1
            continue
        seen_texts.add(text_key)

        # Build processed document — only relevant ones reach here
        relevant_docs.append({
            "doc_id": doc["doc_id"],
            "city": city,
            "source": "reddit",
            "title": title,
            "text": clean,
            "text_length": len(clean),
            "published_at": doc.get("published_at", ""),
            "url": doc.get("url", ""),
            "full_text_scraped": False,
            "llm_relevant": True,
            "llm_reason": groq_reason,
            "processed_time": processed_at,
            "run_id": "historical_bulk_backfill"
        })

    log.info(f"\nFiltering complete — {len(relevant_docs)} relevant documents found")

    if not relevant_docs:
        log.warning("No relevant documents found — nothing to save")
        client.close()
        return

    # ── Step 4: Save local backup BEFORE pushing to MongoDB ───────────────────
    log.info("\n[Backup] Saving relevant docs locally before MongoDB push...")
    backup_path = save_local_backup(relevant_docs)
    log.info(f"[Backup] Data is safe at: {backup_path}")

    # ── Step 5: Push ONLY relevant docs to MongoDB ────────────────────────────
    log.info(f"\n[MongoDB] Pushing {len(relevant_docs)} relevant docs to '{PROCESSED_COLLECTION}'...")
    success = save_to_mongo(relevant_docs, db)

    client.close()

    if not success:
        log.error("=" * 60)
        log.error("MongoDB push FAILED but data is safe locally!")
        log.error(f"Backup: {backup_path}")
        log.error("Fix MongoDB connection and retry")
        log.error("=" * 60)
        return

    # ── Final summary ──────────────────────────────────────────────────────────
    log.info("\n" + "=" * 60)
    log.info("PREPROCESSING COMPLETE")
    log.info(f"Total raw:              {metrics['total']}")
    log.info(f"Dropped by keyword:     {metrics['dropped_keyword']} ({metrics['dropped_keyword']/metrics['total']*100:.0f}%)")
    log.info(f"Sent to Groq:           {metrics['groq_calls']}")
    log.info(f"Dropped by Groq:        {metrics['dropped_groq']}")
    log.info(f"Dropped short/lang/dupe:{metrics['dropped_short'] + metrics['dropped_lang'] + metrics['dropped_dupe']}")
    log.info(f"Final relevant docs:    {len(relevant_docs)}")
    log.info(f"Saved to MongoDB:       {PROCESSED_COLLECTION}")
    log.info(f"Local backup:           {backup_path}")
    log.info("=" * 60)


if __name__ == "__main__":
    run()