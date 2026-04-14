"""
03_score_historical_reddit.py — VADER scoring for historical Reddit documents.

Reads from processed_documents where:
  - run_id = "historical_bulk_backfill"
  - source = "reddit"

Scores with VADER and stores results into scored_documents.

Usage:
  python preprocess/03_score_historical_reddit.py
"""

import os
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

PROCESSED_COLLECTION = "processed_documents"
SCORED_COLLECTION = "scored_documents"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("score_historical_reddit")


def get_label(compound: float) -> str:
    if compound >= 0.05:
        return "positive"
    elif compound <= -0.05:
        return "negative"
    return "neutral"


def test_mongodb_connection() -> bool:
    if not MONGO_URI:
        log.error("[MongoDB] MONGO_URI not set")
        return False
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        client.close()
        log.info("[MongoDB] Connection test passed ✓")
        return True
    except Exception as e:
        log.error(f"[MongoDB] Connection FAILED: {e}")
        log.error("[MongoDB] Make sure VPN is OFF")
        return False


def run() -> dict:
    log.info("=" * 60)
    log.info("HISTORICAL REDDIT VADER SCORING")
    log.info(f"Source collection:      {PROCESSED_COLLECTION}")
    log.info(f"Destination collection: {SCORED_COLLECTION}")
    log.info("=" * 60)

    # Pre-flight check
    if not test_mongodb_connection():
        return {"scored_count": 0}

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    # Find all historical Reddit docs in processed_documents
    query = {
        "run_id": "historical_bulk_backfill",
        "source": "reddit"
    }

    total_in_db = db[PROCESSED_COLLECTION].count_documents(query)
    log.info(f"\nFound {total_in_db} historical Reddit docs in '{PROCESSED_COLLECTION}'")

    if total_in_db == 0:
        log.error("No historical Reddit documents found.")
        log.error("Make sure historical_preprocess.py and refilter_groq.py ran successfully.")
        client.close()
        return {"scored_count": 0}

    # Skip already scored docs
    already_scored = set(db[SCORED_COLLECTION].distinct(
        "doc_id",
        {"run_id": "historical_bulk_backfill"}
    ))
    log.info(f"Already scored: {len(already_scored)} — skipping these")

    docs = [
        d for d in db[PROCESSED_COLLECTION].find(query)
        if d.get("doc_id") not in already_scored
    ]

    log.info(f"Documents to score: {len(docs)}")

    if not docs:
        log.info("All historical Reddit documents already scored — nothing to do")
        client.close()
        return {"scored_count": 0}

    # Score with VADER
    analyzer = SentimentIntensityAnalyzer()
    scored_at = datetime.now(timezone.utc).isoformat()
    results = []

    for doc in docs:
        text = doc.get("text", "") or ""
        scores = analyzer.polarity_scores(text)
        compound = scores["compound"]

        results.append({
            "doc_id": doc.get("doc_id"),
            "city": doc.get("city"),
            "source": "reddit",
            "title": doc.get("title", ""),
            "published_at": doc.get("published_at", ""),
            "sentiment_label": get_label(compound),
            "sentiment_score": round(compound, 4),
            "vader_breakdown": {
                "pos": scores["pos"],
                "neu": scores["neu"],
                "neg": scores["neg"],
            },
            "scored_at": scored_at,
            "run_id": "historical_bulk_backfill",
            "scored_by": "03_score_historical_reddit"
        })

    # Save to scored_documents
    try:
        operations = [
            UpdateOne(
                {"doc_id": r["doc_id"]},
                {"$set": r},
                upsert=True
            )
            for r in results
        ]
        result = db[SCORED_COLLECTION].bulk_write(operations)
        log.info(
            f"\n[MongoDB] Saved {result.upserted_count + result.modified_count} "
            f"scored documents to '{SCORED_COLLECTION}'"
        )

        # Save artifact
        pos = sum(1 for r in results if r["sentiment_label"] == "positive")
        neg = sum(1 for r in results if r["sentiment_label"] == "negative")
        neu = sum(1 for r in results if r["sentiment_label"] == "neutral")

        db["pipeline_artifacts"].insert_one({
            "run_id": "historical_bulk_backfill",
            "artifact_type": "historical_reddit_scores",
            "timestamp": datetime.now(timezone.utc),
            "document_count": len(results),
            "metrics": {"positive": pos, "negative": neg, "neutral": neu}
        })

    except Exception as e:
        log.error(f"[MongoDB] Failed to save: {e}")
        client.close()
        return {"scored_count": 0}
    finally:
        client.close()

    pos = sum(1 for r in results if r["sentiment_label"] == "positive")
    neg = sum(1 for r in results if r["sentiment_label"] == "negative")
    neu = sum(1 for r in results if r["sentiment_label"] == "neutral")

    log.info("\n" + "=" * 60)
    log.info("SCORING COMPLETE")
    log.info(f"Total scored:  {len(results)}")
    log.info(f"Positive:      {pos} ({pos/len(results)*100:.0f}%)")
    log.info(f"Negative:      {neg} ({neg/len(results)*100:.0f}%)")
    log.info(f"Neutral:       {neu} ({neu/len(results)*100:.0f}%)")
    log.info(f"Saved to:      {SCORED_COLLECTION}")
    log.info("=" * 60)

    return {"scored_count": len(results), "positive": pos, "negative": neg, "neutral": neu}


if __name__ == "__main__":
    result = run()
    print(f"\nScored {result['scored_count']} historical Reddit documents")
    print(f"Positive: {result.get('positive', 0)} | Negative: {result.get('negative', 0)} | Neutral: {result.get('neutral', 0)}")