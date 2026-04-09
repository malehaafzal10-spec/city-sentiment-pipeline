"""
02a_store_relevant_docs.py — Step 2: Silver Layer Processor.

Two-stage relevance filtering:
  Stage 1 — Keyword pre-filter (fast, free)
             Drops obvious irrelevant articles before calling Groq.
             Saves API calls and time.

  Stage 2 — LLM relevance filter (Groq / Llama 3)
             Sends title + description to Groq for each article that
             passed Stage 1. Groq decides if the article is genuinely
             about visiting the city as a travel destination.
             Stores the reason for traceability.

Only relevant articles get:
  - Full text scraped via BeautifulSoup
  - Cleaned and deduplicated
  - Stored in processed_documents collection

Reddit posts skip Stage 2 (already travel-relevant by search query).
"""

import os
import re
import json
import time
import logging
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"

RAW_COLLECTION = "raw_documents"
PROCESSED_COLLECTION = "processed_documents"
ARTIFACTS_COLLECTION = "pipeline_artifacts"

MIN_TEXT_LENGTH = 40

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("store_relevant_docs")

# ─── STAGE 1: KEYWORD PRE-FILTER ─────────────────────────────────────────────
# Fast check on title + snippet only.
# Purpose: drop obvious non-travel articles BEFORE calling Groq.
# This saves ~60% of Groq API calls.

IRRELEVANT_PATTERNS = [
    "airline", "luxury seat", "business class", "first class seat",
    "flight deal", "airfare", "fare sale", "seat upgrade",
    "stock market", "share price", "quarterly earnings", "revenue report",
    "ipo", "merger", "acquisition", "hedge fund",
    "premier league", "champions league", "match result", "transfer window",
    "football club", "rugby", "cricket match",
    "weather forecast", "temperature forecast",
    "local election", "city council", "municipal", "residential",
    "real estate listing", "property market", "mortgage rate",
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
    "local tips", "hidden gem", "tourist trap",
]


def keyword_pre_filter(title: str, snippet: str, city: str) -> bool:
    """
    Stage 1: fast keyword check.
    Returns True if article should proceed to LLM check.
    Returns False if article should be dropped immediately.
    """
    combined = f"{title} {snippet}".lower()
    for pattern in IRRELEVANT_PATTERNS:
        if pattern in combined:
            return False
    for pattern in RELEVANT_PATTERNS:
        if pattern in combined:
            return True
    # If city name is present but no travel signal — still send to LLM
    # The LLM will make the final call
    if city.lower() in combined:
        return True
    return False


# ─── STAGE 2: LLM RELEVANCE FILTER ───────────────────────────────────────────
# Sends title + description to Groq for each article that passed Stage 1.
# Returns {"relevant": "yes"/"no", "reason": "..."}

def build_system_prompt(city: str) -> str:
    return f"""You are a travel news classifier.
Your job is to decide if a news article is genuinely about traveling to, visiting, or experiencing {city} as a travel destination.

Relevant articles are about:
- Tourism in {city} (things to do, see, eat)
- Travel tips or guides for visiting {city}
- Visitor experiences in {city}
- Hotels, restaurants, attractions in {city}
- Travel trends or statistics about {city} tourism
- Overtourism, crowding, costs for travellers in {city}

NOT relevant:
- Sports, politics, crime, business, technology
- Articles that just mention {city} briefly but are about something else
- General travel articles where {city} is not the focus
- Airline routes, flight deals, airport news

Respond ONLY with valid JSON in this exact format, nothing else:
{{"relevant": "yes", "reason": "short explanation"}}
or
{{"relevant": "no", "reason": "short explanation"}}"""


def llm_classify(title: str, description: str, city: str) -> dict:
    """
    Stage 2: ask Groq if this article is relevant for the given city.
    Returns dict with 'relevant' (yes/no/unknown) and 'reason'.
    Falls back gracefully if Groq is unavailable.
    """
    if not GROQ_API_KEY:
        # No Groq key — skip LLM filter, treat as relevant
        return {"relevant": "yes", "reason": "LLM filter skipped — no GROQ_API_KEY"}

    user_message = f"Title: {title}\nDescription: {description}"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    body = {
        "model": GROQ_MODEL,
        "temperature": 0,
        "max_tokens": 100,
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
        except json.JSONDecodeError:
            log.warning(f"[LLM Filter] Could not parse response for '{title[:50]}': {raw_text}")
            result = {"relevant": "yes", "reason": f"parse_error: {raw_text[:100]}"}

        return result

    except Exception as e:
        log.warning(f"[LLM Filter] Groq error for '{title[:50]}': {e}")
        # On error — treat as relevant so we don't lose articles
        return {"relevant": "yes", "reason": f"groq_error: {str(e)[:100]}"}


# ─── SCRAPING ─────────────────────────────────────────────────────────────────

def scrape_full_text(url: str) -> str:
    """Scrape full article text using BeautifulSoup."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        paragraphs = soup.find_all("p")
        full_text = "\n\n".join([
            p.get_text().strip()
            for p in paragraphs
            if p.get_text().strip()
        ])
        return full_text if len(full_text) > 100 else ""
    except Exception as e:
        log.debug(f"[Scrape] Failed {url}: {e}")
        return ""


# ─── TEXT CLEANING ────────────────────────────────────────────────────────────

def clean_text_vader_safe(text: str) -> str:
    """
    Clean text while preserving casing and punctuation for accurate VADER scoring.
    VADER needs: capitalisation (GREAT vs great), punctuation (!!!) and negations (not good).
    """
    if not text:
        return ""
    text = re.sub(r"http\S+|www\.\S+", "", text)
    text = re.sub(r"\[\+\d+\s*chars\]", "", text)          # NewsAPI truncation
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)  # markdown links
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_english(text: str) -> bool:
    try:
        from langdetect import detect
        return detect(text) == "en"
    except Exception:
        return True


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def process_documents(run_id: str) -> dict:
    if not MONGO_URI:
        log.error("[DB] MONGO_URI missing.")
        return {"run_id": run_id, "cleaned_count": 0}

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    raw_docs = list(db[RAW_COLLECTION].find({"run_id": run_id}))
    if not raw_docs:
        log.error(f"[Process] No raw documents found for run_id: {run_id}")
        client.close()
        return {"run_id": run_id, "cleaned_count": 0}

    log.info(f"[Process] {len(raw_docs)} raw documents for run_id: {run_id}")

    processed_docs = []
    seen_texts = set()

    metrics = {
        "total_raw": len(raw_docs),
        "passed_keyword_filter": 0,
        "passed_llm_filter": 0,
        "scraped": 0,
        "skipped_keyword": 0,
        "skipped_llm": 0,
        "skipped_short": 0,
        "skipped_lang": 0,
        "skipped_dupe": 0,
        "groq_calls": 0
    }

    for doc in raw_docs:
        title = doc.get("title", "") or ""
        original_text = doc.get("text", "") or ""
        description = doc.get("description", "") or ""
        city = doc.get("city", "Unknown")
        source = doc.get("source", "")

        # ── Stage 1: keyword pre-filter ───────────────────────────────────────
        # Reddit posts skip LLM filter — already travel-relevant by search query
        if source == "reddit":
            llm_relevant = True
            llm_reason = "reddit — skipped LLM filter"
            metrics["passed_keyword_filter"] += 1
            metrics["passed_llm_filter"] += 1

        else:
            # News articles go through both filters
            if not keyword_pre_filter(title, original_text, city):
                metrics["skipped_keyword"] += 1
                log.debug(f"[Filter] KEYWORD DROP: {title[:60]}")
                continue

            metrics["passed_keyword_filter"] += 1

            # ── Stage 2: LLM relevance filter ─────────────────────────────────
            # Use title + description for LLM (cleaner than full raw text)
            desc_for_llm = description if description else original_text[:300]
            classification = llm_classify(title, desc_for_llm, city)
            metrics["groq_calls"] += 1

            llm_relevant = classification.get("relevant", "yes") == "yes"
            llm_reason = classification.get("reason", "")

            if not llm_relevant:
                metrics["skipped_llm"] += 1
                log.info(f"[Filter] LLM DROP [{city}]: {title[:60]} — {llm_reason}")
                continue

            metrics["passed_llm_filter"] += 1
            log.info(f"[Filter] LLM KEEP [{city}]: {title[:60]}")

            # Rate limit — 0.3s between Groq calls (free tier)
            time.sleep(0.3)

        # ── Scrape full text (news only) ──────────────────────────────────────
        full_text = ""
        was_scraped = False
        if source == "news":
            full_text = scrape_full_text(doc.get("url", ""))
            if full_text:
                metrics["scraped"] += 1
                was_scraped = True

        raw_final_text = full_text if full_text else original_text

        # ── Clean text ────────────────────────────────────────────────────────
        clean = clean_text_vader_safe(f"{title}. {raw_final_text}")

        # ── Length filter ─────────────────────────────────────────────────────
        if len(clean) < MIN_TEXT_LENGTH:
            metrics["skipped_short"] += 1
            continue

        # ── Language filter ───────────────────────────────────────────────────
        if not is_english(clean):
            metrics["skipped_lang"] += 1
            continue

        # ── Deduplication ─────────────────────────────────────────────────────
        text_key = f"{city}:{clean[:120]}"
        if text_key in seen_texts:
            metrics["skipped_dupe"] += 1
            continue
        seen_texts.add(text_key)

        # ── Build processed document ──────────────────────────────────────────
        processed_doc = doc.copy()
        processed_doc.pop("_id", None)
        processed_doc.update({
            "text": clean,
            "full_text_scraped": was_scraped,
            "text_length": len(clean),
            "llm_relevant": llm_relevant,
            "llm_reason": llm_reason,          # stored for traceability
            "processed_time": datetime.now(timezone.utc).isoformat()
        })
        processed_docs.append(processed_doc)

    # ── Summary log ───────────────────────────────────────────────────────────
    log.info(
        f"[Process] Kept {len(processed_docs)} / {metrics['total_raw']} | "
        f"Keyword dropped: {metrics['skipped_keyword']} | "
        f"LLM dropped: {metrics['skipped_llm']} | "
        f"Scraped: {metrics['scraped']} | "
        f"Groq calls: {metrics['groq_calls']}"
    )

    # ── Save to MongoDB ───────────────────────────────────────────────────────
    if processed_docs:
        try:
            # Save artifact snapshot
            db[ARTIFACTS_COLLECTION].insert_one({
                "run_id": run_id,
                "artifact_type": "processed_scraped_docs",
                "timestamp": datetime.now(timezone.utc),
                "document_count": len(processed_docs),
                "metrics": metrics,
                "payload": processed_docs
            })

            # Upsert into processed_documents
            operations = [
                UpdateOne({"doc_id": d["doc_id"]}, {"$set": d}, upsert=True)
                for d in processed_docs
            ]
            result = db[PROCESSED_COLLECTION].bulk_write(operations)
            log.info(
                f"[DB] Upserted {result.upserted_count + result.modified_count} "
                f"processed documents into '{PROCESSED_COLLECTION}'"
            )

        except Exception as e:
            log.error(f"[DB] Failed to save processed data: {e}")

    client.close()
    return {"run_id": run_id, "cleaned_count": len(processed_docs), "metrics": metrics}


if __name__ == "__main__":
    test_run_id = input("Enter the run_id to process: ")
    if test_run_id.strip():
        result = process_documents(test_run_id.strip())
        print(f"\nProcessed {result['cleaned_count']} documents")
        print(f"Metrics: {result['metrics']}")