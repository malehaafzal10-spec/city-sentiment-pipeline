"""
04_create_features_historical.py — Step 4: Extract features for historical documents.

Reads from processed_documents (processed_by = "02a_historical") and
scored_documents (scored_by = "03_score_historical"), calculates keyword
dimensions, sentiment aggregations per city per week, and stores results
into document_features and city_weekly_features.

Usage:
  python preprocess/04_create_features_historical.py
  python preprocess/04_create_features_historical.py --start-date 2026-03-11 --end-date 2026-04-06
"""

import os
import json
import argparse
import logging
from datetime import datetime, timezone
from collections import defaultdict

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME   = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

PROCESSED_COLLECTION    = "processed_documents"
SCORED_COLLECTION       = "scored_documents"
DOC_FEATURES_COLLECTION = "document_features"
CITY_FEATURES_COLLECTION = "city_weekly_features"

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("features_historical")

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


def get_label(compound: float) -> str:
    if compound >= 0.05:
        return "positive"
    elif compound <= -0.05:
        return "negative"
    return "neutral"


def count_keywords(text: str, keywords: list) -> int:
    text_lower = text.lower()
    return sum(text_lower.count(kw) for kw in keywords)


def fetch_date_to_week_start(fetch_date: str) -> str:
    """Convert a YYYY-MM-DD fetch_date string to the Monday of that week."""
    from datetime import date
    d = date.fromisoformat(fetch_date)
    monday = d - __import__("datetime").timedelta(days=d.weekday())
    return monday.isoformat()


def run(start_date: str = None, end_date: str = None) -> dict:
    log.info("=== HISTORICAL FEATURE EXTRACTION ===")

    if not MONGO_URI:
        log.error("[DB] MONGO_URI missing.")
        return {"doc_features_count": 0}

    client = MongoClient(MONGO_URI)
    db     = client[DB_NAME]

    # ── Fetch processed docs ──────────────────────────────────────────────────
    proc_query: dict = {"run_id": {"$in": ["02a_historical", "historical_bulk_backfill"]}}
    if start_date and end_date:
        proc_query["fetch_date"] = {"$gte": start_date, "$lte": end_date}
        log.info(f"[Features] Filtering by fetch_date: {start_date} → {end_date}")

    # Skip already extracted doc_ids
    already_extracted = set(db[DOC_FEATURES_COLLECTION].distinct("doc_id"))
    if already_extracted:
        proc_query["doc_id"] = {"$nin": list(already_extracted)}
        log.info(f"[Skip] {len(already_extracted)} docs already have features — skipping.")

    processed_docs = list(db[PROCESSED_COLLECTION].find(proc_query))

    if not processed_docs:
        log.info("[Features] No new historical documents to extract features from.")
        client.close()
        return {"doc_features_count": 0}

    log.info(f"[Features] Processing {len(processed_docs)} documents.")

    # ── Fetch scored docs ─────────────────────────────────────────────────────
    doc_ids = [d["doc_id"] for d in processed_docs]
    scored_docs = {
        d["doc_id"]: d
        for d in db[SCORED_COLLECTION].find({"doc_id": {"$in": doc_ids}})
    }

    # ── Document-level features ───────────────────────────────────────────────
    doc_features = []
    for doc in processed_docs:
        doc_id     = doc.get("doc_id")
        text       = doc.get("text", "")
        fetch_date = doc.get("fetch_date", "")

        sentiment_data  = scored_docs.get(doc_id, {})
        sentiment_score = sentiment_data.get("sentiment_score", 0.0)

        # Use fetch_date to determine the week this article belongs to
        week_start = fetch_date_to_week_start(fetch_date) if fetch_date else ""

        feature = {
            "doc_id":          doc_id,
            "city":            doc.get("city"),
            "source":          doc.get("source"),
            "fetch_date":      fetch_date,
            "week_start":      week_start,
            "text_length":     doc.get("text_length", len(text)),
            "sentiment_score": sentiment_score,
            "extracted_at":    datetime.now(timezone.utc).isoformat(),
            "extracted_by":    "04_historical",
        }

        for dim, keywords in KEYWORD_DIMENSIONS.items():
            feature[f"kw_{dim}"] = count_keywords(text, keywords)

        doc_features.append(feature)

    # ── City-week aggregations ─────────────────────────────────────────────────
    # Group by (city, week_start) to match daily pipeline structure
    city_week_agg = defaultdict(lambda: {
        "mention_count": 0,
        "sentiment_total": 0.0,
        "pos_count": 0, "neg_count": 0, "neu_count": 0,
        "kw_crowding": 0, "kw_cost": 0, "kw_safety": 0,
    })

    for f in doc_features:
        key  = (f["city"], f["week_start"])
        city_week_agg[key]["mention_count"]    += 1
        city_week_agg[key]["sentiment_total"]  += f["sentiment_score"]

        label = get_label(f["sentiment_score"])
        if label == "positive":
            city_week_agg[key]["pos_count"] += 1
        elif label == "negative":
            city_week_agg[key]["neg_count"] += 1
        else:
            city_week_agg[key]["neu_count"] += 1

        for dim in KEYWORD_DIMENSIONS:
            city_week_agg[key][f"kw_{dim}"] += f[f"kw_{dim}"]

    agg_features = []
    for (city, week_start), agg in city_week_agg.items():
        n = agg["mention_count"]
        agg_features.append({
            "city":             city,
            "week_start":       week_start,
            "mention_count":    n,
            "avg_sentiment":    round(agg["sentiment_total"] / n, 4) if n else 0,
            "positive_ratio":   round(agg["pos_count"] / n, 3) if n else 0,
            "negative_ratio":   round(agg["neg_count"] / n, 3) if n else 0,
            "neutral_ratio":    round(agg["neu_count"] / n, 3) if n else 0,
            "crowding_score":   round(agg["kw_crowding"] / n, 3) if n else 0,
            "cost_score":       round(agg["kw_cost"] / n, 3) if n else 0,
            "safety_score":     round(agg["kw_safety"] / n, 3) if n else 0,
            "aggregated_at":    datetime.now(timezone.utc).isoformat(),
            "aggregated_by":    "04_historical",
        })

    # ── Save to MongoDB ───────────────────────────────────────────────────────
    try:
        # Document-level features
        doc_ops = [
            UpdateOne({"doc_id": f["doc_id"]}, {"$set": f}, upsert=True)
            for f in doc_features
        ]
        db[DOC_FEATURES_COLLECTION].bulk_write(doc_ops)
        log.info(f"[DB] Upserted {len(doc_features)} document features.")

        # City-week aggregates — upsert on city + week_start to match daily pipeline
        city_ops = [
            UpdateOne(
                {"city": a["city"], "week_start": a["week_start"]},
                {"$set": a},
                upsert=True
            )
            for a in agg_features
        ]
        db[CITY_FEATURES_COLLECTION].bulk_write(city_ops)
        log.info(f"[DB] Upserted {len(agg_features)} city weekly aggregates.")

    except Exception as e:
        log.error(f"[DB] Failed to save features: {e}")
    finally:
        client.close()

    log.info(f"[Done] Doc features: {len(doc_features)} | City-week aggregates: {len(agg_features)}")

    return {
        "doc_features_count": len(doc_features),
        "city_aggregates":    agg_features,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Feature extraction for historical documents.")
    parser.add_argument("--start-date", type=str, default=None, help="Start fetch_date YYYY-MM-DD")
    parser.add_argument("--end-date",   type=str, default=None, help="End fetch_date YYYY-MM-DD")
    args = parser.parse_args()

    result = run(start_date=args.start_date, end_date=args.end_date)

    print(f"\nExtracted features for {result['doc_features_count']} documents.")
    print("\n=== CITY-WEEK AGGREGATES SUMMARY ===")
    print(json.dumps(result.get("city_aggregates", []), indent=2))