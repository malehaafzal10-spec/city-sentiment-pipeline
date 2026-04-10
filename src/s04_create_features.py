"""
04_create_features.py — Step 4: Extract structured features & aggregates.
Reads text and sentiment from MongoDB, calculates keyword dimensions, 
calculates sentiment ratios, and stores aggregations back to MongoDB.
"""

import os
import logging
from datetime import datetime, date, timedelta, timezone
from collections import defaultdict

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

# Collections
PROCESSED_COLLECTION = "processed_documents"
SCORED_COLLECTION = "scored_documents"
DOC_FEATURES_COLLECTION = "document_features"
CITY_FEATURES_COLLECTION = "city_weekly_features"
ARTIFACTS_COLLECTION = "pipeline_artifacts"

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("features")

KEYWORD_DIMENSIONS = {
    "crowding": [
        "crowded", "crowd", "tourist trap", "overrun", "packed", "busy",
        "overwhelming", "too many people", "overtourism", "queues", "lines"
    ],
    "cost": [
        "expensive", "overpriced", "pricey", "cheap", "affordable",
        "great value", "rip off", "ripoff", "costly", "budget"
    ],
    "safety": [
        "safe", "unsafe", "dangerous", "crime", "pickpocket", "scam",
        "sketchy", "secure", "felt safe", "robbery"
    ],
}

# ─── HELPER FUNCTIONS ─────────────────────────────────────────────────────────

def get_label(compound: float) -> str:
    """Translates a numerical VADER compound score into a string label."""
    if compound >= 0.05:
        return "positive"
    elif compound <= -0.05:
        return "negative"
    return "neutral"


def count_keywords(text: str, keywords: list) -> int:
    """Counts keywords safely by lowercasing the text first."""
    text_lower = text.lower()
    return sum(text_lower.count(kw) for kw in keywords)


def get_week_start() -> str:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


# ─── MAIN PIPELINE ────────────────────────────────────────────────────────────

def run(run_id: str) -> dict:
    log.info(f"=== STEP 4: FEATURES | run_id={run_id} ===")

    if not MONGO_URI:
        log.error("[DB] MONGO_URI is missing. Cannot connect to MongoDB.")
        return {"run_id": run_id, "processed_count": 0}

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    # 1. Fetch text data and sentiment data for this run
    processed_docs = list(db[PROCESSED_COLLECTION].find({"run_id": run_id}))
    scored_docs = {doc["doc_id"]: doc for doc in db[SCORED_COLLECTION].find({"run_id": run_id})}

    log.info(f"[Features] Processing {len(processed_docs)} documents.")

    if not processed_docs:
        client.close()
        return {"run_id": run_id, "processed_count": 0}

    week_start = get_week_start()
    doc_features = []

    # 2. Calculate Document-Level Features
    for doc in processed_docs:
        doc_id = doc.get("doc_id")
        text = doc.get("text", "")
        
        # Look up sentiment from step 03
        sentiment_data = scored_docs.get(doc_id, {})
        sentiment_score = sentiment_data.get("sentiment_score", 0.0)

        feature = {
            "doc_id": doc_id,
            "city": doc.get("city"),
            "source": doc.get("source"),
            "text_length": doc.get("text_length", len(text)),
            "sentiment_score": sentiment_score,
            "week_start": week_start,
            "run_id": run_id,
            "extracted_at": datetime.now(timezone.utc).isoformat()
        }
        
        for dim, keywords in KEYWORD_DIMENSIONS.items():
            feature[f"kw_{dim}"] = count_keywords(text, keywords)
            
        doc_features.append(feature)

    # 3. Calculate City-Week Aggregations
    city_agg = defaultdict(lambda: {
        "mention_count": 0,
        "sentiment_total": 0.0,
        "pos_count": 0, "neg_count": 0, "neu_count": 0,
        "kw_crowding": 0, "kw_cost": 0, "kw_safety": 0
    })

    for f in doc_features:
        city = f["city"]
        city_agg[city]["mention_count"] += 1
        city_agg[city]["sentiment_total"] += f["sentiment_score"]
        
        # Track sentiment labels for dashboard ratios
        label = get_label(f["sentiment_score"]) 
        if label == "positive": 
            city_agg[city]["pos_count"] += 1
        elif label == "negative": 
            city_agg[city]["neg_count"] += 1
        else: 
            city_agg[city]["neu_count"] += 1
            
        for dim in KEYWORD_DIMENSIONS:
            city_agg[city][f"kw_{dim}"] += f[f"kw_{dim}"]

    agg_features = []
    for city, agg in city_agg.items():
        n = agg["mention_count"]
        agg_features.append({
            "city": city,
            "week_start": week_start,
            "mention_count": n,
            "avg_sentiment": round(agg["sentiment_total"] / n, 4) if n else 0,
            "positive_ratio": round(agg["pos_count"] / n, 3) if n else 0,
            "negative_ratio": round(agg["neg_count"] / n, 3) if n else 0,
            "neutral_ratio": round(agg["neu_count"] / n, 3) if n else 0,
            "crowding_score": round(agg["kw_crowding"] / n, 3) if n else 0,
            "cost_score": round(agg["kw_cost"] / n, 3) if n else 0,
            "safety_score": round(agg["kw_safety"] / n, 3) if n else 0,
            "run_id": run_id,
            "aggregated_at": datetime.now(timezone.utc).isoformat()
        })

    # 4. Save to MongoDB
    try:
        # A. Save document-level features
        doc_ops = [UpdateOne({"doc_id": f["doc_id"]}, {"$set": f}, upsert=True) for f in doc_features]
        db[DOC_FEATURES_COLLECTION].bulk_write(doc_ops)
        
        # B. Save city-level weekly aggregates (upserting based on city AND week_start)
        city_ops = [
            UpdateOne({"city": a["city"], "week_start": a["week_start"]}, {"$set": a}, upsert=True) 
            for a in agg_features
        ]
        db[CITY_FEATURES_COLLECTION].bulk_write(city_ops)
        log.info(f"[DB] Upserted {len(doc_features)} doc features and {len(agg_features)} city weekly aggregates.")

        # C. Save Artifact Snapshot
        db[ARTIFACTS_COLLECTION].insert_one({
            "run_id": run_id,
            "artifact_type": "feature_aggregates",
            "timestamp": datetime.now(timezone.utc),
            "week_start": week_start,
            "metrics": {"total_cities_aggregated": len(agg_features)},
            "payload": agg_features
        })
        log.info(f"[Artifacts] Saved feature aggregation artifact to MongoDB.")

    except Exception as e:
        log.error(f"[DB] Failed to save features: {e}")
    finally:
        client.close()

    return {
        "run_id": run_id,
        "doc_features_count": len(doc_features),
        "city_aggregates": agg_features
    }

if __name__ == "__main__":
    # Generate the run_id automatically to match the daily pipeline format
    current_run_id = f"run_{datetime.now(timezone.utc).strftime('%d%m%Y')}"
    print(f"Starting feature creation with run_id: {current_run_id}")
    
    # Trigger the feature extraction
    result = run(current_run_id)
    
    print(f"\nPipeline Step 4 Finished! Extracted features for {result.get('doc_features_count', 0)} documents.")
    print("\n=== CITY AGGREGATES SUMMARY ===")
    import json
    print(json.dumps(result.get("city_aggregates", []), indent=2))