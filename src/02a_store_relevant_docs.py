"""
02_process_and_scrape.py — Step 2: The "Silver Layer" Processor.
Reads raw docs, filters relevance, scrapes full text, cleans safely for VADER, 
detects language, drops duplicates, and stores into 'processed_documents'.
"""

import os
import re
import logging
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

RAW_COLLECTION = "raw_documents"
PROCESSED_COLLECTION = "processed_documents"
ARTIFACTS_COLLECTION = "pipeline_artifacts"

MIN_TEXT_LENGTH = 40

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("process_scrape")

# ─── RELEVANCE PATTERNS ───────────────────────────────────────────────────────

IRRELEVANT_PATTERNS = [
    "airline", "luxury seat", "business class", "stock market", "share price", 
    "quarterly earnings", "premier league", "champions league", "weather forecast", 
    "real estate listing", "mortgage rate", "revenue report"
]

RELEVANT_PATTERNS = [
    "tourist", "tourism", "travel", "vacation", "holiday", "sightseeing", 
    "hotel", "airbnb", "overtourism", "expensive", "affordable", "safe", 
    "unsafe", "pickpocket", "scam", "tourist trap", "hidden gem", "crowds"
]

# ─── HELPER FUNCTIONS ─────────────────────────────────────────────────────────

def is_likely_relevant(title: str, snippet: str, city: str) -> bool:
    combined = f"{title} {snippet}".lower()
    for pattern in IRRELEVANT_PATTERNS:
        if pattern in combined:
            return False
    for pattern in RELEVANT_PATTERNS:
        if pattern in combined:
            return True
    if city.lower() in combined:
        return True
    return False

def scrape_full_text(url: str) -> str:
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        paragraphs = soup.find_all('p')
        full_text = "\n\n".join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
        
        return full_text if len(full_text) > 100 else ""
    except Exception as e:
        log.debug(f"[Scrape] Failed to parse {url}: {e}")
        return ""

def clean_text_vader_safe(text: str) -> str:
    """Cleans text but PRESERVES casing and punctuation for accurate VADER sentiment."""
    if not text:
        return ""
    text = re.sub(r"http\S+|www\.\S+", "", text)                  # Remove URLs
    text = re.sub(r'\[\+\d+\s*chars\]', '', text)                 # Remove NewsAPI truncation markers
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)         # Convert markdown links to just text
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">") # HTML entities
    text = re.sub(r"\s+", " ", text)                              # Normalize whitespace
    return text.strip()

def is_english(text: str) -> bool:
    try:
        from langdetect import detect
        return detect(text) == "en"
    except Exception:
        return True # Keep if detection fails rather than throwing away good data

# ─── MAIN PIPELINE ────────────────────────────────────────────────────────────

def process_documents(run_id: str):
    if not MONGO_URI:
        log.error("[DB] MONGO_URI missing.")
        return

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    
    raw_docs = list(db[RAW_COLLECTION].find({"run_id": run_id}))
    if not raw_docs:
        log.error(f"[Process] No raw documents found for run_id: {run_id}.")
        client.close()
        return

    log.info(f"[Process] Found {len(raw_docs)} raw documents for run_id: {run_id}")

    processed_docs = []
    seen_texts = set()
    
    # Metrics
    metrics = {
        "scraped": 0, "skipped_irrelevant": 0, 
        "skipped_short": 0, "skipped_lang": 0, "skipped_dupe": 0
    }

    for doc in raw_docs:
        title = doc.get("title", "")
        original_text = doc.get("text", "")
        city = doc.get("city", "Unknown")

        # 1. Relevance filter
        if not is_likely_relevant(title, original_text, city):
            metrics["skipped_irrelevant"] += 1
            continue

        # 2. Scrape full text (News only)
        full_text = ""
        was_scraped = False
        if doc.get("source") == "news":
            full_text = scrape_full_text(doc.get("url", ""))
            if full_text:
                metrics["scraped"] += 1
                was_scraped = True

        # Use scraped text if available, otherwise fallback to snippet
        raw_final_text = full_text if full_text else original_text

        # 3. Clean Text (VADER Safe)
        clean = clean_text_vader_safe(f"{title}. {raw_final_text}")

        # 4. Length check
        if len(clean) < MIN_TEXT_LENGTH:
            metrics["skipped_short"] += 1
            continue

        # 5. Language filter
        if not is_english(clean):
            metrics["skipped_lang"] += 1
            continue

        # 6. Deduplication (hash the first 120 chars to catch syndicated news/crossposts)
        text_key = f"{city}:{clean[:120]}"
        if text_key in seen_texts:
            metrics["skipped_dupe"] += 1
            continue
        seen_texts.add(text_key)

        # 7. Prepare final processed document
        processed_doc = doc.copy()
        processed_doc.pop("_id", None) 
        
        processed_doc.update({
            "text": clean,
            "full_text_scraped": was_scraped,
            "text_length": len(clean),
            "processed_time": datetime.now(timezone.utc).isoformat()
        })
        
        processed_docs.append(processed_doc)

    log.info(
        f"[Process] Kept {len(processed_docs)} | Scraped: {metrics['scraped']} | "
        f"Dropped: Irrelevant={metrics['skipped_irrelevant']}, Short={metrics['skipped_short']}, "
        f"Non-English={metrics['skipped_lang']}, Dupes={metrics['skipped_dupe']}"
    )

    # 8. Save to MongoDB
    if processed_docs:
        try:
            db[ARTIFACTS_COLLECTION].insert_one({
                "run_id": run_id,
                "artifact_type": "processed_scraped_docs",
                "timestamp": datetime.now(timezone.utc),
                "document_count": len(processed_docs),
                "metrics": metrics,
                "payload": processed_docs
            })
            
            operations = [
                UpdateOne({"doc_id": d["doc_id"]}, {"$set": d}, upsert=True)
                for d in processed_docs
            ]
            result = db[PROCESSED_COLLECTION].bulk_write(operations)
            log.info(f"[DB] Upserted {result.upserted_count + result.modified_count} processed documents.")

        except Exception as e:
            log.error(f"[DB] Failed to save processed data: {e}")
            
    client.close()

if __name__ == "__main__":
    test_run_id = input("Enter the run_id to process: ")
    if test_run_id.strip():
        process_documents(test_run_id.strip())