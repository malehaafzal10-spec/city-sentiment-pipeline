"""
evaluate.py — Step: Model quality evaluation for VADER sentiment model.
 
Calculates accuracy, precision, recall and F1 score from human-labelled
articles in the validation_samples table.
 
Human labels are collected via the dashboard human review queue —
articles flagged by LLM Judge appear there for manual labelling.
 
The more articles labelled, the more reliable the metrics.
Minimum 5 human labels needed to calculate anything meaningful.
 
Run standalone: python src/evaluate.py
Or called automatically from run_pipeline.py after each run.
"""
 
import os
import json
import logging
from datetime import datetime, timezone
from db import get_connection
 
logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("evaluate")
 
ARTIFACTS_DIR = os.getenv("PIPELINE_ARTIFACTS_DIR", "artifacts")
LABELS = ["positive", "negative", "neutral"]
MIN_SAMPLES = 5
 
 
def calculate_metrics(rows: list) -> dict:
    """
    Calculate precision, recall and F1 for each sentiment label.
    Also calculates overall accuracy and macro-averaged F1.
 
    Args:
        rows: list of (vader_label, human_label) tuples
 
    Returns:
        dict with per-label and overall metrics
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
    """
    Calculate evaluation metrics from all human-labelled samples.
 
    Reads from validation_samples table where human_label is not null.
    Saves results to artifacts/evaluation/ as JSON.
    """
    log.info(f"=== EVALUATE | run_id={run_id} ===")
 
    conn = get_connection()
 
    # Fetch all human-labelled samples
    rows = conn.execute("""
        SELECT vader_label, human_label
        FROM validation_samples
        WHERE human_label IS NOT NULL
        AND human_label IN ('positive', 'negative', 'neutral')
    """).fetchall()
 
    conn.close()
 
    labelled_rows = [(r["vader_label"], r["human_label"]) for r in rows]
    log.info(f"[Evaluate] {len(labelled_rows)} human-labelled samples found")
 
    if len(labelled_rows) < MIN_SAMPLES:
        log.info(
            f"[Evaluate] Not enough labels yet — need {MIN_SAMPLES}, "
            f"have {len(labelled_rows)}. "
            f"Label articles in the dashboard human review queue."
        )
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
 
    # Save to artifacts
    eval_dir = os.path.join(ARTIFACTS_DIR, "evaluation")
    os.makedirs(eval_dir, exist_ok=True)
 
    date_str = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    eval_path = os.path.join(eval_dir, f"evaluation_{date_str}.json")
 
    with open(eval_path, "w") as f:
        json.dump(metrics, f, indent=2)
 
    log.info(f"[Artifacts] Saved evaluation metrics → {eval_path}")
 
    # Also save a running history file
    history_path = os.path.join(eval_dir, "evaluation_history.json")
    history = []
    if os.path.exists(history_path):
        try:
            with open(history_path) as f:
                history = json.load(f)
        except Exception:
            history = []
 
    history.append({
        "date": date_str,
        "run_id": run_id,
        "accuracy": metrics["accuracy"],
        "macro_f1": metrics["macro_f1"],
        "weighted_f1": metrics["weighted_f1"],
        "total_samples": metrics["total_samples"]
    })
 
    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)
 
    log.info(f"[Artifacts] Updated evaluation history → {history_path}")
 
    return metrics
 
 
if __name__ == "__main__":
    import sys
    rid = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    result = run(rid)
 
    if "error" in result:
        print(f"\nCannot calculate metrics: {result['error']}")
        print(f"Label articles in the Streamlit dashboard to enable evaluation.")
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