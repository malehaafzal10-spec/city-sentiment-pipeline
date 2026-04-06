"""
monitor.py — Step 9: Drift detection and alert generation.
"""

import os
import json
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from db import get_connection

load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("monitor")

ARTIFACTS_DIR = os.getenv("PIPELINE_ARTIFACTS_DIR", "artifacts")
SENTIMENT_DROP_THRESHOLD = float(os.getenv("MONITOR_SENTIMENT_DROP_THRESHOLD", "0.20"))
MIN_MENTIONS = int(os.getenv("MONITOR_MIN_MENTIONS", "5"))
SOURCE_IMBALANCE = float(os.getenv("MONITOR_SOURCE_IMBALANCE_THRESHOLD", "0.85"))
ROLLING_WEEKS = 4
ROLLING_DEVIATION = 0.25


def get_previous(conn, city: str, current_week: str):
    row = conn.execute("""
        SELECT avg_sentiment, mention_count FROM city_weekly_metrics
        WHERE city = ? AND week_start < ?
        ORDER BY week_start DESC LIMIT 1
    """, (city, current_week)).fetchone()
    return dict(row) if row else None


def get_rolling_avg(conn, city: str) -> float | None:
    rows = conn.execute("""
        SELECT avg_sentiment FROM city_weekly_metrics
        WHERE city = ? ORDER BY week_start DESC LIMIT ?
    """, (city, ROLLING_WEEKS)).fetchall()
    if not rows:
        return None
    return sum(r["avg_sentiment"] for r in rows) / len(rows)


def run(run_id: str, city_metrics: list) -> dict:
    log.info(f"=== STEP 9: MONITOR | run_id={run_id} ===")

    conn = get_connection()
    all_alerts = []
    triggered_at = datetime.now(timezone.utc).isoformat()

    for m in city_metrics:
        city = m["city"]
        week_start = m["week_start"]
        alerts = []

        previous = get_previous(conn, city, week_start)
        rolling = get_rolling_avg(conn, city)

        # Rule 1: sentiment drop vs last week
        if previous:
            drop = previous["avg_sentiment"] - m["avg_sentiment"]
            if drop > SENTIMENT_DROP_THRESHOLD:
                alerts.append({
                    "city": city, "week_start": week_start, "run_id": run_id,
                    "alert_type": "sentiment_drop",
                    "alert_message": f"Sentiment dropped {drop:.2f} ({previous['avg_sentiment']:+.2f} → {m['avg_sentiment']:+.2f})",
                    "severity": "high" if drop > 0.40 else "medium",
                    "triggered_at": triggered_at
                })

        # Rule 2: low mention volume
        if m["mention_count"] < MIN_MENTIONS:
            alerts.append({
                "city": city, "week_start": week_start, "run_id": run_id,
                "alert_type": "low_volume",
                "alert_message": f"Only {m['mention_count']} mentions this week (min: {MIN_MENTIONS})",
                "severity": "low",
                "triggered_at": triggered_at
            })

        # Rule 3: rolling average deviation
        if rolling is not None:
            dev = abs(m["avg_sentiment"] - rolling)
            if dev > ROLLING_DEVIATION:
                alerts.append({
                    "city": city, "week_start": week_start, "run_id": run_id,
                    "alert_type": "rolling_deviation",
                    "alert_message": f"Sentiment deviates {dev:.2f} from {ROLLING_WEEKS}-week average ({rolling:+.2f})",
                    "severity": "medium",
                    "triggered_at": triggered_at
                })

        for alert in alerts:
            log.warning(f"[Monitor] {city} [{alert['alert_type']}]: {alert['alert_message']}")
            conn.execute("""
                INSERT INTO monitoring_alerts
                (city, week_start, alert_type, alert_message, severity, triggered_at, run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                alert["city"], alert["week_start"], alert["alert_type"],
                alert["alert_message"], alert["severity"],
                alert["triggered_at"], alert["run_id"]
            ))

        if not alerts:
            log.info(f"[Monitor] {city}: No alerts")

        all_alerts.extend(alerts)

    conn.commit()
    conn.close()

    monitoring_dir = os.path.join(ARTIFACTS_DIR, "monitoring")
    os.makedirs(monitoring_dir, exist_ok=True)
    week_str = city_metrics[0]["week_start"].replace("-", "") if city_metrics else "unknown"
    alert_path = os.path.join(monitoring_dir, f"alerts_{week_str}.json")
    with open(alert_path, "w") as f:
        json.dump(all_alerts, f, indent=2)

    log.info(f"[Monitor] {len(all_alerts)} alerts saved → {alert_path}")
    return {"run_id": run_id, "total_alerts": len(all_alerts), "alerts": all_alerts}
