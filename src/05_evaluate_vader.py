"""
05_evaluate_vader.py — Step 5: Model quality evaluation for VADER.

Calculates accuracy, precision, recall, and F1 score from human-labelled
articles in the 'validation_samples' MongoDB collection.

Human labels are collected via the dashboard human review queue.
Minimum 5 human labels needed to calculate anything meaningful.
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

VALIDATION_COLLECTION = "validation_samples"
ARTIFACTS_COLLECTION = "pipeline_artifacts"

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("evaluate")

LABELS = ["positive", "negative", "neutral"]
MIN_SAMPLES = 5


def calculate_metrics(rows: list) -> dict:
    """
    Calculate precision, recall and F1 for each sentiment label.
    Also calculates overall accuracy and macro-averaged F1.
    """
    if len(rows) < MIN_SAMPLES:
        return {
            "error": f"Not enough human labels — need at least {MIN_SAMPLES}, have {len(rows)}",
            "total_samples": len(rows)
        }

    per_label = {}

    for label in LABELS:
        # True positive: VADER said label, human agrees
        tp = sum(1 for vader, human in rows if vader == label and human == label)
        # False positive: VADER said label, human disagrees
        fp = sum(1 for vader, human in rows if vader == label and human != label)
        # False negative: VADER said something else, human says label
        fn = sum(1 for vader, human in rows if vader != label and human == label)
        # True negative: VADER said something else, human agrees it's not label
        tn = sum(1 for vader, human in rows if vader != label and human != label)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0 else 0.0
        )

        support = sum(1 for _, human in rows if human == label)

        per_label[label] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "support": support,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn
        }

    # Overall accuracy
    correct = sum(1 for vader, human in rows if vader == human)
    accuracy = correct / len(rows)

    # Macro F1 — simple average of F1 across all labels
    macro_f1 = sum(per_label[l]["f1"] for l in LABELS) / len(LABELS)

    # Weighted F1 — weighted by support (number of actual instances per label)
    total_support = len(rows)
    weighted_f1 = (
        sum(per_label[l]["f1"] * per_label[l]["support"] for l in LABELS) / total_support
        if total_support > 0 else 0.0
    )

    return {
        "accuracy": round(accuracy, 3),
        "macro_f1": round(macro_f1, 3),
        "weighted_f1": round(weighted_f1, 3),
        "total_samples": len(rows),
        "correct": correct,
        "per_label": per_label
    }


def run(run_id: str) -> dict:
    log.info(f"=== STEP 5: EVALUATE | run_id={run_id} ===")

    if not MONGO_URI:
        log.error("[DB] MONGO_URI is missing. Cannot connect to MongoDB.")
        return {"run_id": run_id, "error": "Database connection missing."}

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    # Fetch all human-labelled samples
    samples_cursor = db[VALIDATION_COLLECTION].find({
        "human_label": {"$in": ["positive", "negative", "neutral"]}
    })
    
    labelled_rows = [(doc.get("vader_label"), doc.get("human_label")) for doc in samples_cursor]
    log.info(f"[Evaluate] {len(labelled_rows)} human-labelled samples found in '{VALIDATION_COLLECTION}'.")

    if len(labelled_rows) < MIN_SAMPLES:
        log.warning(
            f"[Evaluate] Not enough labels yet — need {MIN_SAMPLES}, "
            f"have {len(labelled_rows)}. Label articles in the dashboard first."
        )
        client.close()
        return {
            "run_id": run_id,
            "error": f"Need at least {MIN_SAMPLES} human labels",
            "total_samples": len(labelled_rows)
        }

    # Calculate metrics
    metrics = calculate_metrics(labelled_rows)
    metrics["run_id"] = run_id
    metrics["evaluated_at"] = datetime.now(timezone.utc).isoformat()

    # Log results
    log.info(f"[Evaluate] Overall accuracy: {metrics['accuracy']:.0%}")
    log.info(f"[Evaluate] Macro F1: {metrics['macro_f1']:.0%}")
    log.info(f"[Evaluate] Weighted F1: {metrics['weighted_f1']:.0%}")

    for label in LABELS:
        m = metrics["per_label"][label]
        log.info(
            f"[Evaluate] {label:8} — "
            f"precision={m['precision']:.0%} "
            f"recall={m['recall']:.0%} "
            f"f1={m['f1']:.0%} "
            f"support={m['support']}"
        )

    # Save to MongoDB Artifacts
    try:
        db[ARTIFACTS_COLLECTION].insert_one({
            "run_id": run_id,
            "artifact_type": "vader_evaluation",
            "timestamp": datetime.now(timezone.utc),
            "total_samples": metrics["total_samples"],
            "payload": metrics
        })
        log.info(f"[Artifacts] Saved evaluation metrics artifact to MongoDB.")
    except Exception as e:
        log.error(f"[Artifacts] Failed to save evaluation artifact: {e}")
    finally:
        client.close()

    return metrics


if __name__ == "__main__":
    # Typically this is just the date/time of the evaluation run
    current_run_id = f"eval_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    result = run(current_run_id)

    if "error" in result:
        print(f"\n⚠️ Cannot calculate metrics: {result['error']}")
        print(f"   Please add labels to the '{VALIDATION_COLLECTION}' collection in MongoDB.")
    else:
        print(f"\n{'='*40}")
        print(f"VADER Evaluation Results")
        print(f"{'='*40}")
        print(f"Total samples:  {result['total_samples']}")
        print(f"Accuracy:       {result['accuracy']:.0%}")
        print(f"Macro F1:       {result['macro_f1']:.0%}")
        print(f"Weighted F1:    {result['weighted_f1']:.0%}")
        print(f"\nPer-label breakdown:")
        print(f"{'Label':<12} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Support':>10}")
        print(f"{'-'*52}")
        for label in LABELS:
            m = result["per_label"][label]
            print(
                f"{label:<12} {m['precision']:>10.0%} {m['recall']:>10.0%} "
                f"{m['f1']:>10.0%} {m['support']:>10}"
            )