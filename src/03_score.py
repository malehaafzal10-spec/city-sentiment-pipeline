"""
03_score.py — Step 3: VADER sentiment scoring on processed documents.
Reads from MongoDB, calculates sentiment, and stores results & artifacts back to MongoDB.
"""

import os
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

PROCESSED_COLLECTION = "processed_documents"
SCORED_COLLECTION = "scored_documents"
ARTIFACTS_COLLECTION = "pipeline_artifacts"

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("score")


def get_label(compound: float) -> str:
    if compound >= 0.05:
        return "positive"
    elif compound <= -0.05:
        return "negative"
    return "neutral"


def run(run_id: str) -> dict:
    log.info(f"=== STEP 3: SCORE | run_id={run_id} ===")

    if not MONGO_URI:
        log.error("[DB] MONGO_URI is missing. Cannot connect to MongoDB.")
        return {"run_id": run_id, "scored_count": 0}

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    # 1. Fetch already scored doc_ids for this run to avoid duplicate processing
    already_scored_cursor = db[SCORED_COLLECTION].find({"run_id": run_id}, {"doc_id": 1})
    already_scored_ids = {doc["doc_id"] for doc in already_scored_cursor}

    # 2. Fetch processed documents for this run
    processed_docs = list(db[PROCESSED_COLLECTION].find({"run_id": run_id}))
    
    # Filter out docs that have already been scored
    docs_to_score = [d for d in processed_docs if d.get("doc_id") not in already_scored_ids]
    
    log.info(f"[Score] Found {len(processed_docs)} total processed docs. Scoring {len(docs_to_score)} new documents with VADER.")

    if not docs_to_score:
        client.close()
        return {"run_id": run_id, "scored_count": 0}

    # 3. Analyze Sentiment
    analyzer = SentimentIntensityAnalyzer()
    scored_results = []
    scored_at = datetime.now(timezone.utc).isoformat()

    for doc in docs_to_score:
        # Use the scraped/processed text, fallback to empty string if missing
        text_to_score = doc.get("text", "")
        
        scores = analyzer.polarity_scores(text_to_score)
        compound = scores["compound"]
        
        scored_results.append({
            "doc_id": doc.get("doc_id"),
            "city": doc.get("city"),
            "source": doc.get("source"),
            "sentiment_label": get_label(compound),
            "sentiment_score": round(compound, 4),
            "vader_breakdown": {
                "pos": scores["pos"],
                "neu": scores["neu"],
                "neg": scores["neg"]
            },
            "scored_at": scored_at,
            "run_id": run_id
        })

    # 4. Save Scores to Database
    try:
        operations = [
            UpdateOne(
                {"doc_id": doc["doc_id"]},
                {"$set": doc},
                upsert=True
            )
            for doc in scored_results
        ]
        
        result = db[SCORED_COLLECTION].bulk_write(operations)
        log.info(f"[DB] Upserted {result.upserted_count + result.modified_count} scored documents.")
        
        # 5. Save Artifact to Database (Replacing the local CSV file)
        pos = sum(1 for s in scored_results if s["sentiment_label"] == "positive")
        neg = sum(1 for s in scored_results if s["sentiment_label"] == "negative")
        neu = sum(1 for s in scored_results if s["sentiment_label"] == "neutral")
        
        db[ARTIFACTS_COLLECTION].insert_one({
            "run_id": run_id,
            "artifact_type": "sentiment_scores",
            "timestamp": datetime.now(timezone.utc),
            "document_count": len(scored_results),
            "metrics": {
                "positive": pos,
                "negative": neg,
                "neutral": neu
            },
            "payload": scored_results
        })
        log.info(f"[Artifacts] Saved scoring artifact snapshot to MongoDB. (Pos: {pos}, Neg: {neg}, Neu: {neu})")

    except Exception as e:
        log.error(f"[DB] Failed to save scored data: {e}")
    finally:
        client.close()

    return {"run_id": run_id, "scored_count": len(scored_results)}


if __name__ == "__main__":
    # Prompting for run_id to link this step to the previous ingestion/processing steps
    test_run_id = input("Enter the run_id to score: ")
    if test_run_id.strip():
        run(test_run_id.strip())
    else:
        print("No run_id provided. Exiting.")