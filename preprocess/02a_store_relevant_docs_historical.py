"""
02a_store_relevant_docs_historical.py — Historical Silver Layer Processor.

Reads from raw_documents_historical and applies:
1) keyword pre-filter
2) LLM relevance classification (Groq first, Gemini fallback)
3) full text scraping
4) cleaning / language / dedupe
5) MongoDB upsert

Usage:
  python preprocess/02a_store_relevant_docs_historical.py --start-date 2026-03-11 --end-date 2026-03-17
"""

import os
import re
import json
import time
import logging
import argparse
import csv
from datetime import datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

load_dotenv()

MONGO_URI      = os.getenv("MONGO_URI")
DB_NAME        = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"

RAW_COLLECTION       = "raw_documents_historical"
PROCESSED_COLLECTION = "processed_documents"

MIN_TEXT_LENGTH        = 40
BATCH_SIZE             = int(os.getenv("BATCH_SIZE", "100"))
SKIP_ALREADY_PROCESSED = os.getenv("SKIP_ALREADY_PROCESSED", "true").lower() == "true"
BOTH_RATE_LIMITED_WAIT = 60

GROQ_RPM          = int(os.getenv("GROQ_RPM", "30"))
GROQ_MIN_INTERVAL = 60.0 / GROQ_RPM
_last_groq_call_time = 0.0

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("store_relevant_docs_historical")


# ─── STAGE 1: KEYWORD PRE-FILTER ─────────────────────────────────────────────

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
    combined = f"{title} {snippet}".lower()
    has_relevant   = any(p in combined for p in RELEVANT_PATTERNS)
    has_irrelevant = any(p in combined for p in IRRELEVANT_PATTERNS)
    has_city       = city.lower() in combined if city else False

    if has_relevant:
        return True
    if has_irrelevant and not has_city:
        return False
    if has_city:
        return True
    return False


# ─── STAGE 2: LLM RELEVANCE FILTER ───────────────────────────────────────────

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


def _parse_llm_response(raw_text: str, title: str) -> Optional[dict]:
    raw_text = (raw_text or "").strip()
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        log.warning(f"[LLM] Could not parse response for '{title[:50]}': {raw_text[:150]}")
        return None


def _respect_groq_rate_limit():
    global _last_groq_call_time
    now     = time.time()
    elapsed = now - _last_groq_call_time
    wait    = GROQ_MIN_INTERVAL - elapsed
    if wait > 0:
        time.sleep(wait)
    _last_groq_call_time = time.time()


def _classify_groq(title: str, description: str, city: str) -> Optional[dict]:
    if not GROQ_API_KEY:
        return None

    _respect_groq_rate_limit()

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
            {"role": "user",   "content": f"Title: {title}\nDescription: {description}"},
        ],
        "response_format": {"type": "json_object"}
    }

    response = requests.post(GROQ_URL, headers=headers, json=body, timeout=20)

    if response.status_code == 429:
        log.warning("[Groq] 429 rate limit hit.")
        return None

    response.raise_for_status()
    return _parse_llm_response(response.json()["choices"][0]["message"]["content"], title)


def _classify_gemini(title: str, description: str, city: str) -> Optional[dict]:
    if not GEMINI_API_KEY:
        return None

    payload = {
        "systemInstruction": {"parts": [{"text": build_system_prompt(city)}]},
        "contents": [{"role": "user", "parts": [{"text": f"Title: {title}\nDescription: {description}"}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0}
    }

    response = requests.post(f"{GEMINI_URL}?key={GEMINI_API_KEY}", json=payload, timeout=20)

    if response.status_code == 429:
        log.warning("[Gemini] 429 rate limit hit.")
        return None

    response.raise_for_status()

    raw_text = (
        response.json()
        .get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    return _parse_llm_response(raw_text, title)


def llm_classify(title: str, description: str, city: str, max_retries: int = 5) -> dict:
    for attempt in range(1, max_retries + 1):
        try:
            result = _classify_groq(title, description, city)
            if result is not None:
                return result
        except Exception as e:
            log.warning(f"[Groq] Error for '{title[:50]}': {e} — trying Gemini")

        try:
            result = _classify_gemini(title, description, city)
            if result is not None:
                return result
        except Exception as e:
            log.warning(f"[Gemini] Error for '{title[:50]}': {e}")

        log.warning(
            f"[LLM] Both providers failed on attempt {attempt}/{max_retries}. "
            f"Waiting {BOTH_RATE_LIMITED_WAIT}s before retrying..."
        )
        time.sleep(BOTH_RATE_LIMITED_WAIT)

    return {"relevant": "no", "reason": "LLM classification failed after retries"}


# ─── SCRAPING ─────────────────────────────────────────────────────────────────

def scrape_full_text(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        paragraphs = soup.find_all("p")
        full_text = "\n\n".join(p.get_text().strip() for p in paragraphs if p.get_text().strip())
        return full_text if len(full_text) > 100 else ""
    except Exception as e:
        log.debug(f"[Scrape] Failed {url}: {e}")
        return ""


# ─── TEXT CLEANING ────────────────────────────────────────────────────────────

def clean_text_vader_safe(text: str) -> str:
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


# ─── DB FLUSH ─────────────────────────────────────────────────────────────────

def _flush(db, docs: list) -> None:
    if not docs:
        return
    try:
        ops = [UpdateOne({"doc_id": d["doc_id"]}, {"$set": d}, upsert=True) for d in docs]
        result = db[PROCESSED_COLLECTION].bulk_write(ops)
        log.info(
            f"[DB] Flushed {len(docs)} docs — "
            f"upserted: {result.upserted_count}, modified: {result.modified_count}"
        )
    except Exception as e:
        log.error(f"[DB] Batch flush failed: {e}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def process_historical_documents(start_date: str = None, end_date: str = None) -> dict:
    if not MONGO_URI:
        log.error("[DB] MONGO_URI missing.")
        return {"cleaned_count": 0}

    if not GEMINI_API_KEY and not GROQ_API_KEY:
        log.error("[LLM] Neither GEMINI_API_KEY nor GROQ_API_KEY is set — aborting.")
        return {"cleaned_count": 0}

    client = MongoClient(MONGO_URI)
    db     = client[DB_NAME]

    query: dict = {}

    if start_date and end_date:
        query["fetch_date"] = {"$gte": start_date, "$lte": end_date}
        log.info(f"[Process] Filtering historical docs between {start_date} and {end_date}")

    if SKIP_ALREADY_PROCESSED:
        already_done = set(db[PROCESSED_COLLECTION].distinct("doc_id"))
        if already_done:
            query["doc_id"] = {"$nin": list(already_done)}
            log.info(f"[Skip] {len(already_done)} doc_ids already in processed_documents — skipping.")

    raw_docs = list(db[RAW_COLLECTION].find(query))

    if not raw_docs:
        log.info("[Process] No unprocessed historical documents found for this date range.")
        client.close()
        return {"cleaned_count": 0}

    log.info(f"[Process] {len(raw_docs)} historical docs to process.")

    processed_docs_batch: list = []
    seen_texts: set            = set()

    metrics = {
        "total_raw":             len(raw_docs),
        "passed_keyword_filter": 0,
        "passed_llm_filter":     0,
        "final_kept":            0,
        "scraped":               0,
        "skipped_keyword":       0,
        "skipped_llm":           0,
        "skipped_short":         0,
        "skipped_lang":          0,
        "skipped_dupe":          0,
        "llm_calls":             0,
    }

    for i, doc in enumerate(raw_docs, 1):
        title       = doc.get("title", "")       or ""
        description = doc.get("description", "") or ""
        city        = doc.get("city", "Unknown")

        log.debug(f"[{i}/{metrics['total_raw']}] {title[:70]}")

        # ── Stage 1: keyword pre-filter ───────────────────────────────────────
        if not keyword_pre_filter(title, description, city):
            metrics["skipped_keyword"] += 1
            continue

        metrics["passed_keyword_filter"] += 1

        # ── Stage 2: LLM relevance filter ─────────────────────────────────────
        classification = llm_classify(title, description, city)
        metrics["llm_calls"] += 1

        llm_relevant = str(classification.get("relevant", "no")).strip().lower() == "yes"
        llm_reason   = classification.get("reason", "")

        if not llm_relevant:
            metrics["skipped_llm"] += 1
            log.info(f"[Filter] LLM DROP [{city}]: {title[:60]} — {llm_reason}")
            continue

        metrics["passed_llm_filter"] += 1
        log.info(f"[Filter] LLM KEEP [{city}]: {title[:60]}")

        # ── Scrape full text ──────────────────────────────────────────────────
        full_text   = ""
        was_scraped = False
        url         = doc.get("url", "")
        if url:
            full_text = scrape_full_text(url)
            if full_text:
                metrics["scraped"] += 1
                was_scraped = True

        raw_final_text = full_text if full_text else description
        clean = clean_text_vader_safe(f"{title}. {raw_final_text}")

        if len(clean) < MIN_TEXT_LENGTH:
            metrics["skipped_short"] += 1
            continue

        if not is_english(clean):
            metrics["skipped_lang"] += 1
            continue

        text_key = f"{city}:{clean[:120]}"
        if text_key in seen_texts:
            metrics["skipped_dupe"] += 1
            continue
        seen_texts.add(text_key)

        processed_doc = doc.copy()
        processed_doc.pop("_id", None)
        processed_doc.update({
            "text":              clean,
            "full_text_scraped": was_scraped,
            "text_length":       len(clean),
            "llm_relevant":      llm_relevant,
            "llm_reason":        llm_reason,
            "processed_time":    datetime.now(timezone.utc).isoformat(),
            "processed_by":      "02a_historical",
        })

        processed_docs_batch.append(processed_doc)
        metrics["final_kept"] += 1

        if len(processed_docs_batch) >= BATCH_SIZE:
            _flush(db, processed_docs_batch)
            processed_docs_batch = []

    if processed_docs_batch:
        _flush(db, processed_docs_batch)

    log.info(
        f"[Done] Kept {metrics['final_kept']} / {metrics['total_raw']} | "
        f"Keyword dropped: {metrics['skipped_keyword']} | "
        f"LLM dropped: {metrics['skipped_llm']} | "
        f"Scraped: {metrics['scraped']} | "
        f"Short: {metrics['skipped_short']} | "
        f"Dupes: {metrics['skipped_dupe']} | "
        f"LLM calls: {metrics['llm_calls']}"
    )

    client.close()
    return {"cleaned_count": metrics["final_kept"], "metrics": metrics}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process historical travel documents.")
    parser.add_argument("--start-date", type=str, help="Start date in YYYY-MM-DD format", default=None)
    parser.add_argument("--end-date",   type=str, help="End date in YYYY-MM-DD format",   default=None)
    args = parser.parse_args()

    result = process_historical_documents(start_date=args.start_date, end_date=args.end_date)
    print(f"\nProcessed {result['cleaned_count']} historical documents")
    if "metrics" in result:
        print(f"Metrics: {json.dumps(result['metrics'], indent=2)}")