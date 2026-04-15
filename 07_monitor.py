"""
07_monitor.py — Step 7: Drift detection and alert generation.
Compares the latest city metrics against historical data in MongoDB to detect 
sentiment drops, low data volume, or deviations from rolling averages.
"""

import os
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

# Collections
CITY_FEATURES_COLLECTION = "city_weekly_features"
ALERTS_COLLECTION = "monitoring_alerts"
ARTIFACTS_COLLECTION = "pipeline_artifacts"

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("monitor")

# Thresholds
SENTIMENT_DROP_THRESHOLD = float(os.getenv("MONITOR_SENTIMENT_DROP_THRESHOLD", "0.20"))
MIN_MENTIONS = int(os.getenv("MONITOR_MIN_MENTIONS", "5"))
ROLLING_WEEKS = 4
ROLLING_DEVIATION = 0.25


def get_previous(db, city: str, current_week: str) -> dict | None:
    """Fetches the most recent weekly metric for a city prior to the current week."""
    # Find docs for this city where week_start is less than current_week, sort descending by week
    doc = db[CITY_FEATURES_COLLECTION].find_one(
        {"city": city, "week_start": {"$lt": current_week}},
        sort=[("week_start", -1)]
    )
    return doc


def get_rolling_avg(db, city: str, current_week: str) -> float | None:
    """Calculates the average sentiment over the previous N weeks."""
    cursor = db[CITY_FEATURES_COLLECTION].find(
        {"city": city, "week_start": {"$lt": current_week}},
        sort=[("week_start", -1)]
    ).limit(ROLLING_WEEKS)
    
    rows = list(cursor)
    if not rows:
        return None
    return sum(r.get("avg_sentiment", 0) for r in rows) / len(rows)


def run(run_id: str) -> dict:
    log.info(f"=== STEP 7: MONITOR | run_id={run_id} ===")

    if not MONGO_URI:
        log.error("[DB] MONGO_URI missing. Cannot connect to MongoDB.")
        return {"run_id": run_id, "error": "Database connection missing."}

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    # Fetch the newly aggregated metrics for this specific run
    current_metrics = list(db[CITY_FEATURES_COLLECTION].find({"run_id": run_id}))
    
    if not current_metrics:
        log.warning(f"[Monitor] No aggregated metrics found for run_id: {run_id}. Did Step 4 complete?")
        client.close()
        return {"run_id": run_id, "total_alerts": 0}

    all_alerts = []
    triggered_at = datetime.now(timezone.utc).isoformat()

    for m in current_metrics:
        city = m.get("city")
        week_start = m.get("week_start")
        current_sentiment = m.get("avg_sentiment", 0.0)
        mention_count = m.get("mention_count", 0)
        
        alerts = []

        previous = get_previous(db, city, week_start)
        rolling = get_rolling_avg(db, city, week_start)

        # Rule 1: Sentiment drop vs last recorded week
        if previous:
            prev_sentiment = previous.get("avg_sentiment", 0.0)
            drop = prev_sentiment - current_sentiment
            if drop > SENTIMENT_DROP_THRESHOLD:
                alerts.append({
                    "city": city, "week_start": week_start, "run_id": run_id,
                    "alert_type": "sentiment_drop",
                    "alert_message": f"Sentiment dropped {drop:.2f} ({prev_sentiment:+.2f} → {current_sentiment:+.2f})",
                    "severity": "high" if drop > 0.40 else "medium",
                    "triggered_at": triggered_at
                })

        # Rule 2: Low mention volume
        if mention_count < MIN_MENTIONS:
            alerts.append({
                "city": city, "week_start": week_start, "run_id": run_id,
                "alert_type": "low_volume",
                "alert_message": f"Only {mention_count} mentions this week (min: {MIN_MENTIONS})",
                "severity": "low",
                "triggered_at": triggered_at
            })

        # Rule 3: Rolling average deviation
        if rolling is not None:
            dev = abs(current_sentiment - rolling)
            if dev > ROLLING_DEVIATION:
                alerts.append({
                    "city": city, "week_start": week_start, "run_id": run_id,
                    "alert_type": "rolling_deviation",
                    "alert_message": f"Sentiment deviates {dev:.2f} from {ROLLING_WEEKS}-week average ({rolling:+.2f})",
                    "severity": "medium",
                    "triggered_at": triggered_at
                })

        # Log alerts and prepare for DB insertion
        for alert in alerts:
            log.warning(f"[Monitor Alert] {city} [{alert['alert_type']}]: {alert['alert_message']}")
        
        if not alerts:
            log.info(f"[Monitor] {city}: No alerts triggered. System stable.")

        all_alerts.extend(alerts)

    # Save to MongoDB
    try:
        if all_alerts:
            # 1. Save actionable alerts to alerts collection
            db[ALERTS_COLLECTION].insert_many(all_alerts)
            
        # 2. Always save a monitoring artifact (even if empty, to prove the check ran)
        db[ARTIFACTS_COLLECTION].insert_one({
            "run_id": run_id,
            "artifact_type": "monitoring_report",
            "timestamp": datetime.now(timezone.utc),
            "metrics": {"total_alerts_triggered": len(all_alerts)},
            "payload": all_alerts
        })
        log.info(f"[Artifacts] Saved monitoring report to MongoDB with {len(all_alerts)} alerts.")

    except Exception as e:
        log.error(f"[DB] Failed to save monitoring alerts: {e}")
    finally:
        client.close()

    return {"run_id": run_id, "total_alerts": len(all_alerts)}


if __name__ == "__main__":
    test_run_id = input("Enter the run_id to monitor: ")
    if test_run_id.strip():
        run(test_run_id.strip())