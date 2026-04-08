"""
02_process_and_scrape.py — Step 2: Read raw docs from DB, filter relevance, scrape full text.
Uses BeautifulSoup for scraping to avoid dependency issues. Stores to MongoDB.
"""

import os
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

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("process_scrape")

IRRELEVANT_PATTERNS = [
    "airline", "luxury seat", "business class", "stock market", "share price", 
    "quarterly earnings", "premier league", "champions league", "weather forecast", 
    "real estate listing", "mortgage rate"
]

RELEVANT_PATTERNS = [
    "tourist", "tourism", "travel", "vacation", "holiday", "sightseeing", 
    "hotel", "airbnb", "overtourism", "expensive", "affordable", "safe", 
    "unsafe", "pickpocket", "scam", "tourist trap", "hidden gem"
]

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
    """Scrapes the full paragraph text from a given article URL using BeautifulSoup."""
    try:
        # Many sites block requests without a standard User-Agent header
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        # Timeout ensures the pipeline doesn't hang forever on a slow website
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract text from all paragraph tags
        paragraphs = soup.find_all('p')
        full_text = "\n\n".join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
        
        # Return only if we got a substantial amount of text
        if len(full_text) > 100:
            return full_text
        return ""
        
    except requests.exceptions.RequestException as e:
        log.warning(f"[Scrape] Network/HTTP error scraping {url}: {e}")
        return ""
    except Exception as e:
        log.warning(f"[Scrape] Failed to parse {url}: {e}")
        return ""

def process_documents(run_id: str):
    if not MONGO_URI:
        log.error("[DB] MONGO_URI missing.")
        return

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    
    # Fetch raw docs for this specific run_id
    raw_docs = list(db[RAW_COLLECTION].find({"run_id": run_id}))
    
    if not raw_docs:
        log.error(f"[Process] No raw documents found for run_id: {run_id}. Did you run step 01?")
        client.close()
        return

    log.info(f"[Process] Found {len(raw_docs)} raw documents for run_id: {run_id}")

    processed_docs = []
    scraped_count = 0
    skipped_irrelevant = 0

    for doc in raw_docs:
        # 1. Relevance check
        is_relevant = is_likely_relevant(doc.get("title", ""), doc.get("text", ""), doc.get("city", ""))
        
        if not is_relevant:
            skipped_irrelevant += 1
            continue

        # 2. Scrape full text if it's a News article (Reddit already has full text)
        full_text = ""
        was_scraped = False
        
        if doc.get("source") == "news":
            log.info(f" ↳ Scraping: {doc.get('title', '')[:50]}...")
            full_text = scrape_full_text(doc.get("url", ""))
            if full_text:
                scraped_count += 1
                was_scraped = True

        # Use full_text if scraped successfully; otherwise keep the original snippet
        final_text = full_text if full_text else doc.get("text", "")

        # 3. Prepare processed document
        processed_doc = doc.copy()
        processed_doc.pop("_id", None) 
        
        processed_doc.update({
            "text": final_text,
            "full_text_scraped": was_scraped,
            "processed_time": datetime.now(timezone.utc).isoformat()
        })
        
        processed_docs.append(processed_doc)

    log.info(f"[Process] Relevant docs: {len(processed_docs)} | Scraped: {scraped_count} | Irrelevant dropped: {skipped_irrelevant}")

    # 4. Save to MongoDB
    if processed_docs:
        try:
            # Save artifact payload
            db[ARTIFACTS_COLLECTION].insert_one({
                "run_id": run_id,
                "artifact_type": "processed_scraped_docs",
                "timestamp": datetime.now(timezone.utc),
                "document_count": len(processed_docs),
                "metrics": {
                    "scraped_count": scraped_count,
                    "dropped_count": skipped_irrelevant
                },
                "payload": processed_docs
            })
            
            # Upsert into processed_documents
            operations = [
                UpdateOne({"doc_id": d["doc_id"]}, {"$set": d}, upsert=True)
                for d in processed_docs
            ]
            result = db[PROCESSED_COLLECTION].bulk_write(operations)
            log.info(f"[DB] Upserted {result.upserted_count + result.modified_count} processed documents into '{PROCESSED_COLLECTION}'.")

        except Exception as e:
            log.error(f"[DB] Failed to save processed data: {e}")
            
    client.close()

if __name__ == "__main__":
    test_run_id = input("Enter the run_id to process: ")
    process_documents(test_run_id)