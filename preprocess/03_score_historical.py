"""
03_score_historical.py — VADER sentiment scoring for historical processed documents.

Reads from processed_documents where processed_by = "02a_historical",
scores with VADER, and stores results into scored_documents.

Usage:
  python preprocess/03_score_historical.py
  python preprocess/03_score_historical.py --start-date 2026-03-11 --end-date 2026-04-06
"""

import os
import argparse
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME   = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

PROCESSED_COLLECTION = "processed_documents"
SCORED_COLLECTION    = "scored_documents"

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("score_historical")


def get_label(compound: float) -> str:
    if compound >= 0.05:
        return "positive"
    elif compound <= -0.05:
        return "negative"
    return "neutral"


def run(start_date: str = None, end_date: str = None) -> dict:
    log.info(f"=== HISTORICAL VADER SCORING ===")

    if not MONGO_URI:
        log.error("[DB] MONGO_URI missing.")
        return {"scored_count": 0}

    client = MongoClient(MONGO_URI)
    db     = client[DB_NAME]

    # ── Build query — only historical processed docs ──────────────────────────
    query: dict = {"processed_by": "02a_historical"}

    if start_date and end_date:
        query["fetch_date"] = {"$gte": start_date, "$lte": end_date}
        log.info(f"[Score] Filtering by fetch_date: {start_date} → {end_date}")

    # ── Skip already scored docs ──────────────────────────────────────────────
    already_scored = set(db[SCORED_COLLECTION].distinct("doc_id"))
    if already_scored:
        query["doc_id"] = {"$nin": list(already_scored)}
        log.info(f"[Skip] {len(already_scored)} docs already scored — skipping.")

    docs = list(db[PROCESSED_COLLECTION].find(query))

    if not docs:
        log.info("[Score] No unscored historical documents found.")
        client.close()
        return {"scored_count": 0}

    log.info(f"[Score] Scoring {len(docs)} documents with VADER...")

    analyzer   = SentimentIntensityAnalyzer()
    scored_at  = datetime.now(timezone.utc).isoformat()
    results    = []

    for doc in docs:
        text     = doc.get("text", "")
        scores   = analyzer.polarity_scores(text)
        compound = scores["compound"]

        results.append({
            "doc_id":          doc.get("doc_id"),
            "city":            doc.get("city"),
            "source":          doc.get("source"),
            "title":           doc.get("title", ""),
            "fetch_date":      doc.get("fetch_date", ""),
            "published_at":    doc.get("published_at", ""),
            "sentiment_label": get_label(compound),
            "sentiment_score": round(compound, 4),
            "vader_breakdown": {
                "pos": scores["pos"],
                "neu": scores["neu"],
                "neg": scores["neg"],
            },
            "scored_at":       scored_at,
            "scored_by":       "03_score_historical",
        })

    # ── Save to scored_documents ──────────────────────────────────────────────
    try:
        ops = [
            UpdateOne({"doc_id": r["doc_id"]}, {"$set": r}, upsert=True)
            for r in results
        ]
        result = db[SCORED_COLLECTION].bulk_write(ops)
        log.info(
            f"[DB] Upserted {result.upserted_count + result.modified_count} "
            f"scored documents into '{SCORED_COLLECTION}'"
        )
    except Exception as e:
        log.error(f"[DB] Failed to save scored data: {e}")
    finally:
        client.close()

    pos = sum(1 for r in results if r["sentiment_label"] == "positive")
    neg = sum(1 for r in results if r["sentiment_label"] == "negative")
    neu = sum(1 for r in results if r["sentiment_label"] == "neutral")

    log.info(
        f"[Done] Scored {len(results)} docs | "
        f"Positive: {pos} | Negative: {neg} | Neutral: {neu}"
    )

    return {"scored_count": len(results), "positive": pos, "negative": neg, "neutral": neu}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VADER scoring for historical documents.")
    parser.add_argument("--start-date", type=str, default=None, help="Start fetch_date YYYY-MM-DD")
    parser.add_argument("--end-date",   type=str, default=None, help="End fetch_date YYYY-MM-DD")
    args = parser.parse_args()

    result = run(start_date=args.start_date, end_date=args.end_date)
    print(f"\nScored {result['scored_count']} historical documents")
    print(f"Positive: {result.get('positive', 0)} | Negative: {result.get('negative', 0)} | Neutral: {result.get('neutral', 0)}")