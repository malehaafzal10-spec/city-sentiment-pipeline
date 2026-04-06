"""
preprocess.py — Step 4: Clean, filter, and deduplicate raw documents.

Includes a travel relevance filter that removes irrelevant articles
(airline seat upgrades, stock market news, sports results, etc.)
and keeps only content useful for city travel sentiment analysis.
"""

import os
import re
import csv
import logging
from datetime import datetime, timezone

from db import get_connection

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("preprocess")

ARTIFACTS_DIR = os.getenv("PIPELINE_ARTIFACTS_DIR", "artifacts")
MIN_TEXT_LENGTH = 40

# ─── RELEVANCE FILTER ─────────────────────────────────────────────────────────
# Articles matching any IRRELEVANT pattern are dropped immediately.
# Articles must also match at least one RELEVANT pattern to be kept.

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
    "restaurant opened", "new hotel opened",  # too generic — no sentiment
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


def is_travel_relevant(title: str, text: str, city: str) -> bool:
    """
    Return True only if the article is genuinely about travel
    sentiment for the given city.

    Two-stage filter:
      1. Drop if any irrelevant pattern matches
      2. Keep only if at least one relevant pattern matches
    """
    combined = f"{title} {text}".lower()

    # Stage 1: hard drop
    for pattern in IRRELEVANT_PATTERNS:
        if pattern in combined:
            return False

    # Stage 2: must have travel signal
    for pattern in RELEVANT_PATTERNS:
        if pattern in combined:
            return True

    return False


# ─── TEXT CLEANING ────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"http\S+|www\.\S+", "", text)           # remove URLs
    text = re.sub(r'\[\+\d+ chars\]', ", text)             # remove NewsAPI trunctuation markers 
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)           # remove bold
    text = re.sub(r"\*(.+?)\*", r"\1", text)               # remove italic
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\[.\]\(.*?\)", "", text)               # remove markdown links
    text = re.sub(r"[^\w\s.,!?'\"-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def is_english(text: str) -> bool:
    try:
        from langdetect import detect
        return detect(text) == "en"
    except Exception:
        return True  # keep if detection fails


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run(run_id: str) -> dict:
    log.info(f"=== STEP 4: PREPROCESS | run_id={run_id} ===")

    conn = get_connection()
    raw_rows = conn.execute("""
        SELECT doc_id, source, city, title, text
        FROM raw_documents
        WHERE doc_id NOT IN (SELECT doc_id FROM cleaned_documents)
    """).fetchall()

    log.info(f"[Preprocess] {len(raw_rows)} new raw documents to process")

    cleaned = []
    seen_texts = set()
    skipped_irrelevant = 0
    skipped_short = 0
    skipped_lang = 0
    skipped_dupe = 0
    processed_at = datetime.now(timezone.utc).isoformat()

    for row in raw_rows:
        title = row["title"] or ""
        text = row["text"] or ""
        city = row["city"]

        # Stage 1: relevance filter — drop non-travel articles
        if not is_travel_relevant(title, text, city):
            skipped_irrelevant += 1
            continue

        # Stage 2: clean the text
        combined = f"{title}. {text}".strip()
        clean = clean_text(combined)

        # Stage 3: length filter
        if len(clean) < MIN_TEXT_LENGTH:
            skipped_short += 1
            continue

        # Stage 4: language filter
        if not is_english(clean):
            skipped_lang += 1
            continue

        # Stage 5: deduplication — drop near-identical texts
        text_key = f"{city}:{clean[:120]}"
        if text_key in seen_texts:
            skipped_dupe += 1
            continue
        seen_texts.add(text_key)

        cleaned.append({
            "doc_id": row["doc_id"],
            "city": city,
            "source": row["source"],
            "clean_text": clean,
            "text_length": len(clean),
            "processed_at": processed_at,
            "run_id": run_id
        })

    log.info(
        f"[Preprocess] Kept {len(cleaned)} | "
        f"Dropped: irrelevant={skipped_irrelevant}, short={skipped_short}, "
        f"non-english={skipped_lang}, duplicates={skipped_dupe}"
    )

    # Write to SQLite
    for doc in cleaned:
        conn.execute("""
            INSERT OR IGNORE INTO cleaned_documents
            (doc_id, city, source, clean_text, text_length, processed_at, run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            doc["doc_id"], doc["city"], doc["source"],
            doc["clean_text"], doc["text_length"],
            doc["processed_at"], doc["run_id"]
        ))
    conn.commit()
    conn.close()

    # Save CSV artifact
    processed_dir = os.path.join(ARTIFACTS_DIR, "processed")
    os.makedirs(processed_dir, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    csv_path = os.path.join(processed_dir, f"cleaned_texts_{date_str}.csv")

    if cleaned:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=cleaned[0].keys())
            writer.writeheader()
            writer.writerows(cleaned)
        log.info(f"[Artifacts] Saved cleaned texts → {csv_path}")

    return {"run_id": run_id, "cleaned_count": len(cleaned)}


if __name__ == "__main__":
    import sys
    from datetime import datetime, timezone
    rid = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run(rid)
