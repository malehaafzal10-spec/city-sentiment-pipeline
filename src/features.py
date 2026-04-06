"""
features.py — Step 5: Extract structured features from cleaned text.
"""

import os
import csv
import json
import logging
from datetime import datetime, date, timedelta, timezone
from collections import defaultdict

from db import get_connection

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("features")

ARTIFACTS_DIR = os.getenv("PIPELINE_ARTIFACTS_DIR", "artifacts")

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


def count_keywords(text: str, keywords: list) -> int:
    return sum(text.count(kw) for kw in keywords)


def get_week_start() -> str:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


def run(run_id: str) -> dict:
    log.info(f"=== STEP 5: FEATURES | run_id={run_id} ===")

    conn = get_connection()
    rows = conn.execute("""
        SELECT doc_id, city, source, clean_text, text_length
        FROM cleaned_documents WHERE run_id = ?
    """, (run_id,)).fetchall()
    conn.close()

    log.info(f"[Features] Processing {len(rows)} documents")
    week_start = get_week_start()
    doc_features = []

    for row in rows:
        text = row["clean_text"]
        feature = {
            "doc_id": row["doc_id"],
            "city": row["city"],
            "source": row["source"],
            "text_length": row["text_length"],
            "week_start": week_start,
            "run_id": run_id
        }
        for dim, keywords in KEYWORD_DIMENSIONS.items():
            feature[f"kw_{dim}"] = count_keywords(text, keywords)
        doc_features.append(feature)

    # City-week aggregation
    city_agg = defaultdict(lambda: {
        "mention_count": 0,
        "kw_crowding": 0, "kw_cost": 0, "kw_safety": 0
    })
    for f in doc_features:
        city = f["city"]
        city_agg[city]["mention_count"] += 1
        for dim in KEYWORD_DIMENSIONS:
            city_agg[city][f"kw_{dim}"] += f[f"kw_{dim}"]

    agg_features = []
    for city, agg in city_agg.items():
        n = agg["mention_count"]
        agg_features.append({
            "city": city,
            "week_start": week_start,
            "mention_count": n,
            "crowding_score": round(agg["kw_crowding"] / n, 3) if n else 0,
            "cost_score": round(agg["kw_cost"] / n, 3) if n else 0,
            "safety_score": round(agg["kw_safety"] / n, 3) if n else 0,
            "run_id": run_id
        })

    # Save artifacts
    features_dir = os.path.join(ARTIFACTS_DIR, "features")
    os.makedirs(features_dir, exist_ok=True)
    week_str = week_start.replace("-", "")

    if agg_features:
        agg_path = os.path.join(features_dir, f"city_features_week_{week_str}.csv")
        with open(agg_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=agg_features[0].keys())
            writer.writeheader()
            writer.writerows(agg_features)
        log.info(f"[Artifacts] Saved city features → {agg_path}")

    return {
        "run_id": run_id,
        "doc_features_count": len(doc_features),
        "city_aggregates": agg_features
    }


if __name__ == "__main__":
    import sys
    rid = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    result = run(rid)
    print(json.dumps(result["city_aggregates"], indent=2))
