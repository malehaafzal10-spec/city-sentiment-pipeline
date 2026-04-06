"""
score.py — Step 6: VADER sentiment scoring on cleaned documents.
"""

import os
import csv
import logging
from datetime import datetime, timezone

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from db import get_connection

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("score")

ARTIFACTS_DIR = os.getenv("PIPELINE_ARTIFACTS_DIR", "artifacts")


def get_label(compound: float) -> str:
    if compound >= 0.05:
        return "positive"
    elif compound <= -0.05:
        return "negative"
    return "neutral"


def run(run_id: str) -> dict:
    log.info(f"=== STEP 6: SCORE | run_id={run_id} ===")

    conn = get_connection()
    rows = conn.execute("""
        SELECT cd.doc_id, cd.city, cd.clean_text, cd.run_id
        FROM cleaned_documents cd
        LEFT JOIN scored_documents sd ON cd.doc_id = sd.doc_id
        WHERE cd.run_id = ? AND sd.doc_id IS NULL
    """, (run_id,)).fetchall()

    docs = [dict(row) for row in rows]
    log.info(f"[Score] Scoring {len(docs)} documents with VADER")

    if not docs:
        conn.close()
        return {"run_id": run_id, "scored_count": 0}

    analyzer = SentimentIntensityAnalyzer()
    scored = []
    scored_at = datetime.now(timezone.utc).isoformat()

    for doc in docs:
        scores = analyzer.polarity_scores(doc["clean_text"])
        compound = scores["compound"]
        scored.append({
            "doc_id": doc["doc_id"],
            "city": doc["city"],
            "sentiment_label": get_label(compound),
            "sentiment_score": round(compound, 4),
            "scored_at": scored_at,
            "run_id": run_id
        })

    for doc in scored:
        conn.execute("""
            INSERT OR IGNORE INTO scored_documents
            (doc_id, city, sentiment_label, sentiment_score, scored_at, run_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            doc["doc_id"], doc["city"], doc["sentiment_label"],
            doc["sentiment_score"], doc["scored_at"], doc["run_id"]
        ))
    conn.commit()
    conn.close()

    # Save artifact
    outputs_dir = os.path.join(ARTIFACTS_DIR, "model_outputs")
    os.makedirs(outputs_dir, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    csv_path = os.path.join(outputs_dir, f"sentiment_scores_{date_str}.csv")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=scored[0].keys())
        writer.writeheader()
        writer.writerows(scored)
    log.info(f"[Artifacts] Saved scores → {csv_path}")

    pos = sum(1 for s in scored if s["sentiment_label"] == "positive")
    neg = sum(1 for s in scored if s["sentiment_label"] == "negative")
    neu = sum(1 for s in scored if s["sentiment_label"] == "neutral")
    log.info(f"[Score] positive={pos}, negative={neg}, neutral={neu}")

    return {"run_id": run_id, "scored_count": len(scored)}


if __name__ == "__main__":
    import sys
    rid = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run(rid)
