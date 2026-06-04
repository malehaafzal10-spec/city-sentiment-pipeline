"""
s02_tourist_alert.py — Step 2: Extract daily news and filter tourist alerts.
Uses Groq (llama-3.1-8b-instant) to detect negative events for tourists.
"""

import os
import json
import argparse
import logging
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from groq import Groq

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
SOURCE_COLLECTION = "raw_documents_historical"
TARGET_COLLECTION = "news_alert"

# Initialize Groq client
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("tourist_alert")


def clean_json_response(raw_text: str) -> str:
    """Helper to strip markdown formatting from LLM JSON responses."""
    text = raw_text.strip()
    
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
        
    if text.endswith("```"):
        text = text[:-3]
        
    return text.strip()


def evaluate_article_with_llm(article: dict) -> dict:
    """Uses Groq to determine if the news negatively affects tourists."""
    
    prompt = f"""
    You are an AI safety monitor for a tourism pipeline. 
    Analyze the following news article and determine if it describes an event that could 
    negatively affect a tourist's experience (e.g., severe weather, protests, 
    strikes, high crime, wars, natural disasters, health hazards)
    Avoid tax implications.
    
    Article Title: {article.get('title', 'Unknown')}
    Database City: {article.get('city', 'Unknown')}
    Content: {article.get('text', '')}
    
    Respond ONLY with a valid JSON object in the exact format below. Do not include any other text.
    {{
        "is_negative": true/false,
        "main_event": "<short 2-5 word description of the event triggering the alert, or null if none>",
        "llm_city": "<Extract the main CITY discussed. Output ONLY the official city name (e.g., 'Paris'). Do NOT output specific venues, landmarks, neighborhoods, or generic locations like 'airport' or 'stadium'.>"
    }}
    """
    
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a precise JSON-outputting analytical engine."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=150 # Slightly increased to accommodate the new JSON field
        )
        
        raw_response = completion.choices[0].message.content
        cleaned_json = clean_json_response(raw_response)
        result = json.loads(cleaned_json)
        
        return result
        
    except Exception as e:
        log.warning(f"Failed to process article {article.get('doc_id')} with Groq: {e}")
        return None


def run_extraction(target_date: str, test_mode: int):
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        source_run_id = f"run_{dt.strftime('%d%m%Y')}"
        target_run_id = f"run_{dt.strftime('%Y%m%d')}"
    except ValueError:
        log.error("Invalid date format. Please use YYYY-MM-DD.")
        return
        
    log.info(f"=== STEP 2: TOURIST ALERTS ===")
    log.info(f"[Config] Querying source ID: {source_run_id}")
    log.info(f"[Config] Target saving ID: {target_run_id}")
    log.info(f"[Config] Test mode: {test_mode}")
    
    if not MONGO_URI or not GROQ_API_KEY:
        log.error("Missing MONGO_URI or GROQ_API_KEY. Check your .env file.")
        return

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    source_col = db[SOURCE_COLLECTION]
    
    query = {"run_id": source_run_id}
    
    cursor = source_col.find(query)
    if test_mode == 1:
        log.info("[Alerts] Test mode enabled: Limiting query to 30 documents.")
        cursor = cursor.limit(30)
        
    articles = list(cursor)
    log.info(f"[Alerts] Found {len(articles)} articles for run_id '{source_run_id}'")
    
    if not articles:
        log.info("No articles found to process. Exiting.")
        client.close()
        return

    negative_alerts = []
    
    log.info(f"[Alerts] Evaluating documents through llama-3.1-8b-instant...")
    for idx, article in enumerate(articles):
        if idx % 10 == 0 and idx > 0:
            log.info(f"[Alerts] Processed {idx}/{len(articles)} documents...")
            
        evaluation = evaluate_article_with_llm(article)
        
        if evaluation and evaluation.get("is_negative") is True:
            alert_payload = {
                "run_id": target_run_id,
                "original_doc_id": article.get("doc_id"),
                "title": article.get("title"),
                "date": article.get("published_at"), 
                "city": article.get("city"),                 # The city metadata from the ingestion step
                "llm_city": evaluation.get("llm_city"),      # <-- NEW FIELD: Extracted by the LLM
                "url": article.get("url"),           
                "main_event": evaluation.get("main_event"), 
                "processed_at": datetime.now(timezone.utc).isoformat()
            }
            negative_alerts.append(alert_payload)
            
        # Pacing to avoid Groq 429 Rate Limits
        time.sleep(2)
            
    log.info(f"[Alerts] Detected {len(negative_alerts)} negative events.")

    if test_mode == 1:
        output_file = f"tourist_alerts_{target_run_id}.json"
        with open(output_file, "w") as f:
            json.dump(negative_alerts, f, indent=4)
        log.info(f"[Alerts] Saved results locally to '{output_file}'")
        
    elif test_mode == 0:
        if not negative_alerts:
            log.info("[Alerts] No negative events to insert into DB.")
        else:
            target_col = db[TARGET_COLLECTION]
            operations = [
                UpdateOne(
                    {"original_doc_id": alert["original_doc_id"]},
                    {"$setOnInsert": alert},
                    upsert=True
                )
                for alert in negative_alerts
            ]
            result = target_col.bulk_write(operations)
            log.info(f"[DB] Inserted {result.upserted_count} new alerts into '{TARGET_COLLECTION}'.")

    client.close()
    log.info("=== PROCESS COMPLETE ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract negative tourist news via Groq.")
    parser.add_argument("--date", type=str, required=True, help="Target date in YYYY-MM-DD format (e.g., 2026-06-01)")
    parser.add_argument("--test", type=int, choices=[0, 1], default=0, help="1 to test 30 docs and save locally, 0 to process all and save to DB")
    
    args = parser.parse_args()
    run_extraction(args.date, args.test)