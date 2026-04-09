"""
02a_store_relevant_docs.py — Step 2: Silver Layer Processor.

Two-stage relevance filtering:
  Stage 1 — Keyword pre-filter (fast, free)
             Drops obvious irrelevant articles before calling the LLM.

  Stage 2 — LLM relevance filter (Gemini -> Groq Fallback)
             Attempts classification with Gemini 2.5 Flash. If rate limited,
             falls back to Groq. If both are limited, waits and retries.
             Avoids false positives by defaulting to "no" on complete failure.
"""

import os
import re
import json
import time
import logging
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

# LLM Configurations
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

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
    for pattern in IRRELEVANT_PATTERNS:
        if pattern in combined:
            return False
    for pattern in RELEVANT_PATTERNS:
        if pattern in combined:
            return True
    if city.lower() in combined:
        return True
    return False

# ─── STAGE 2: LLM RELEVANCE FILTER (GEMINI -> GROQ FALLBACK) ─────────────────

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
    # 1. Prepare Gemini Request
    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    gemini_body = {
        "systemInstruction": {"parts": [{"text": build_system_prompt(city)}]},
        "contents": [{"role": "user", "parts": [{"text": f"Title: {title}\nDescription: {description}"}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0}
    }

    # 2. Prepare Groq Request
    groq_headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    groq_body = {
        "model": GROQ_MODEL,
        "temperature": 0,
        "max_tokens": 100,
        "messages": [
            {"role": "system", "content": build_system_prompt(city)},
            {"role": "user", "content": f"Title: {title}\nDescription: {description}"},
        ],
        "response_format": {"type": "json_object"}
    }

    max_attempts = 4
    base_wait = 10

    for attempt in range(max_attempts):
        # ── Try Gemini ──
        if GEMINI_API_KEY:
            try:
                resp = requests.post(gemini_url, headers={"Content-Type": "application/json"}, json=gemini_body, timeout=15)
                if resp.status_code == 429:
                    log.warning(f"[LLM Filter] Gemini Rate Limit (429). Falling back to Groq...")
                elif not resp.ok:
                    log.error(f"[LLM Filter] Gemini API Error {resp.status_code}: {resp.text}")
                else:
                    raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    result = json.loads(raw_text)
                    result["model_used"] = "gemini"
                    return result
            except Exception as e:
                log.warning(f"[LLM Filter] Gemini request failed: {e}")

        # ── Try Groq (Fallback) ──
        if GROQ_API_KEY:
            try:
                resp = requests.post(GROQ_URL, headers=groq_headers, json=groq_body, timeout=15)
                if resp.status_code == 429:
                    log.warning(f"[LLM Filter] Groq Rate Limit (429). Both models exhausted.")
                elif not resp.ok:
                    log.error(f"[LLM Filter] Groq API Error {resp.status_code}: {resp.text}")
                else:
                    raw_text = resp.json()["choices"][0]["message"]["content"].strip()
                    result = json.loads(raw_text)
                    result["model_used"] = "groq"
                    return result
            except Exception as e:
                log.warning(f"[LLM Filter] Groq request failed: {e}")

        # ── Both Failed (Wait and Retry) ──
        sleep_time = base_wait * (2 ** attempt)
        log.info(f"[LLM Filter] APIs limited/failed. Waiting {sleep_time}s before retry (Attempt {attempt+1}/{max_attempts})...")
        time.sleep(sleep_time)

    # ── Complete Failure (Fix: Now defaults to NO) ──
    log.error(f"[LLM Filter] Max retries exceeded for '{title[:30]}'. Defaulting to NOT RELEVANT.")
    return {"relevant": "no", "reason": "api_limits_exceeded", "model_used": "none"}

# ─── SCRAPING & CLEANING ──────────────────────────────────────────────────────

def scrape_full_text(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        paragraphs = soup.find_all("p")
        full_text = "\n\n".join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
        return full_text if len(full_text) > 100 else ""
    except Exception as e:
        log.debug(f"[Scrape] Failed {url}: {e}")
        return ""

def clean_text_vader_safe(text: str) -> str:
    if not text: return ""
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
    debug_records = []

    metrics = {
        "total_raw": len(raw_docs),
        "passed_keyword_filter": 0,
        "passed_llm_filter": 0,
        "scraped": 0,
        "skipped_keyword": 0,
        "skipped_llm": 0,
        "gemini_successes": 0,
        "groq_successes": 0
    }

    for doc in raw_docs:
        title = doc.get("title", "") or ""
        original_text = doc.get("text", "") or ""
        description = doc.get("description", "") or ""
        city = doc.get("city", "Unknown")
        source = doc.get("source", "")
        url = doc.get("url", "")

        keyword_passed = False
        llm_passed = False
        llm_reason = ""
        model_used = "none"

        # ── Stage 1 & 2 Filtering ──
        if source == "reddit":
            keyword_passed = True
            llm_passed = True
            llm_reason = "reddit — skipped LLM filter"
            metrics["passed_keyword_filter"] += 1
            metrics["passed_llm_filter"] += 1
        else:
            keyword_passed = keyword_pre_filter(title, original_text, city)
            
            if not keyword_passed:
                metrics["skipped_keyword"] += 1
                log.debug(f"[Filter] KEYWORD DROP: {title[:60]}")
            else:
                metrics["passed_keyword_filter"] += 1
                
                desc_for_llm = description if description else original_text[:300]
                classification = llm_classify(title, desc_for_llm, city)
                
                # Update model metrics
                model_used = classification.get("model_used", "none")
                if model_used == "gemini": metrics["gemini_successes"] += 1
                elif model_used == "groq": metrics["groq_successes"] += 1

                llm_passed = classification.get("relevant", "no") == "yes"
                llm_reason = classification.get("reason", "")

                if not llm_passed:
                    metrics["skipped_llm"] += 1
                    log.info(f"[Filter] LLM DROP ({model_used}) [{city}]: {title[:50]} — {llm_reason}")
                else:
                    metrics["passed_llm_filter"] += 1
                    log.info(f"[Filter] LLM KEEP ({model_used}) [{city}]: {title[:50]}")

                # Tiny polite sleep to prevent overwhelming connections
                time.sleep(0.5)

        debug_records.append({
            "city": city,
            "title": title,
            "keyword_passed": keyword_passed,
            "llm_passed": llm_passed,
            "model_used": model_used,
            "llm_reason": llm_reason
        })

        if not keyword_passed or not llm_passed:
            continue

        # ── Scrape & Clean ──
        full_text = ""
        was_scraped = False
        if source == "news":
            full_text = scrape_full_text(doc.get("url", ""))
            if full_text:
                metrics["scraped"] += 1
                was_scraped = True

        raw_final_text = full_text if full_text else original_text
        clean = clean_text_vader_safe(f"{title}. {raw_final_text}")

        if len(clean) < MIN_TEXT_LENGTH or not is_english(clean):
            continue

        text_key = f"{city}:{clean[:120]}"
        if text_key in seen_texts:
            continue
        seen_texts.add(text_key)

        processed_doc = doc.copy()
        processed_doc.pop("_id", None)
        processed_doc.update({
            "text": clean,
            "full_text_scraped": was_scraped,
            "llm_relevant": llm_passed,
            "model_used": model_used,
            "processed_time": datetime.now(timezone.utc).isoformat()
        })
        processed_docs.append(processed_doc)

    # ── Summary & DB Save ──
    log.info(
        f"[Process] Kept {len(processed_docs)}/{metrics['total_raw']} | "
        f"Scraped: {metrics['scraped']} | "
        f"Gemini: {metrics['gemini_successes']} | Groq: {metrics['groq_successes']}"
    )
    
    debug_filename = f"filter_evaluation_{run_id}.json"
    try:
        with open(debug_filename, "w", encoding="utf-8") as f:
            json.dump(debug_records, f, indent=4, ensure_ascii=False)
    except Exception as e:
        log.error(f"Failed to save debug file: {e}")

    if processed_docs:
        try:
            db[ARTIFACTS_COLLECTION].insert_one({
                "run_id": run_id, "artifact_type": "processed_scraped_docs",
                "timestamp": datetime.now(timezone.utc), "document_count": len(processed_docs),
                "metrics": metrics, "payload": processed_docs
            })
            operations = [UpdateOne({"doc_id": d["doc_id"]}, {"$set": d}, upsert=True) for d in processed_docs]
            db[PROCESSED_COLLECTION].bulk_write(operations)
        except Exception as e:
            log.error(f"[DB] Save failed: {e}")

    client.close()
    return {"run_id": run_id, "cleaned_count": len(processed_docs), "metrics": metrics}

if __name__ == "__main__":
    current_run_id = f"run_{datetime.now(timezone.utc).strftime('%d%m%Y')}"
    print(f"Starting processor with run_id: {current_run_id}")
    result = process_documents(current_run_id)
    print(f"\nPipeline Finished! Processed {result['cleaned_count']} documents.")
    print(f"Metrics: {json.dumps(result['metrics'], indent=2)}")