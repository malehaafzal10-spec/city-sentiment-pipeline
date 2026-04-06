"""
aggregate.py — Step 8: Aggregate document scores into city-week metrics.
"""

import os
import csv
import logging
from datetime import datetime, date, timedelta, timezone
from collections import defaultdict

from db import get_connection

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("aggregate")

ARTIFACTS_DIR = os.getenv("PIPELINE_ARTIFACTS_DIR", "artifacts")


def get_week_start() -> str:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


def run(run_id: str, verdicts: dict = None) -> dict:
    log.info(f"=== STEP 8: AGGREGATE | run_id={run_id} ===")

    verdicts = verdicts or {}
    week_start = get_week_start()
    conn = get_connection()

    rows = conn.execute("""
        SELECT sd.city, sd.sentiment_label, sd.sentiment_score, cd.source
        FROM scored_documents sd
        JOIN cleaned_documents cd ON sd.doc_id = cd.doc_id
        WHERE sd.run_id = ?
    """, (run_id,)).fetchall()

    log.info(f"[Aggregate] Processing {len(rows)} scored documents")

    city_data = defaultdict(lambda: {"scores": [], "labels": [], "sources": []})
    for row in rows:
        city = row["city"]
        city_data[city]["scores"].append(row["sentiment_score"])
        city_data[city]["labels"].append(row["sentiment_label"])
        city_data[city]["sources"].append(row["source"])

    # Load keyword features if available
    features_dir = os.path.join(ARTIFACTS_DIR, "features")
    week_str = week_start.replace("-", "")
    feature_path = os.path.join(features_dir, f"city_features_week_{week_str}.csv")
    city_kf = {}
    if os.path.exists(feature_path):
        with open(feature_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                city_kf[row["city"]] = row

    city_metrics = []
    computed_at = datetime.now(timezone.utc).isoformat()

    for city, data in city_data.items():
        scores = data["scores"]
        labels = data["labels"]
        n = len(scores)

        kf = city_kf.get(city, {})
        metrics = {
            "city": city,
            "week_start": week_start,
            "mention_count": n,
            "avg_sentiment": round(sum(scores) / n, 4) if n else 0.0,
            "positive_ratio": round(labels.count("positive") / n, 3) if n else 0.0,
            "negative_ratio": round(labels.count("negative") / n, 3) if n else 0.0,
            "neutral_ratio": round(labels.count("neutral") / n, 3) if n else 0.0,
            "crowding_score": float(kf.get("crowding_score", 0)),
            "cost_score": float(kf.get("cost_score", 0)),
            "safety_score": float(kf.get("safety_score", 0)),
            "llm_verdict": verdicts.get(city, ""),
            "run_id": run_id,
            "computed_at": computed_at
        }
        city_metrics.append(metrics)
        log.info(
            f"[Aggregate] {city}: mentions={n}, "
            f"avg_sentiment={metrics['avg_sentiment']:+.3f}, "
            f"pos={metrics['positive_ratio']:.0%}, neg={metrics['negative_ratio']:.0%}"
        )

    for m in city_metrics:
        conn.execute("""
            INSERT OR REPLACE INTO city_weekly_metrics
            (city, week_start, mention_count, avg_sentiment,
             positive_ratio, negative_ratio, neutral_ratio,
             crowding_score, cost_score, safety_score,
             llm_verdict, run_id, computed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            m["city"], m["week_start"], m["mention_count"],
            m["avg_sentiment"], m["positive_ratio"], m["negative_ratio"],
            m["neutral_ratio"], m["crowding_score"], m["cost_score"],
            m["safety_score"], m["llm_verdict"], m["run_id"], m["computed_at"]
        ))
    conn.commit()
    conn.close()

    weekly_dir = os.path.join(ARTIFACTS_DIR, "weekly")
    os.makedirs(weekly_dir, exist_ok=True)
    csv_path = os.path.join(weekly_dir, f"city_metrics_{week_str}.csv")
    if city_metrics:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=city_metrics[0].keys())
            writer.writeheader()
            writer.writerows(city_metrics)
        log.info(f"[Artifacts] Saved weekly metrics → {csv_path}")

    return {"run_id": run_id, "city_metrics": city_metrics}


if __name__ == "__main__":
    import sys
    rid = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    result = run(rid)
    for m in result["city_metrics"]:
        print(f"{m['city']:15} sentiment={m['avg_sentiment']:+.3f}  mentions={m['mention_count']}")
