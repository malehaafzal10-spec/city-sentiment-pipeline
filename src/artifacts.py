"""
artifacts.py — Centralized artifact logging to Hugging Face Hub
for the city-sentiment-pipeline.

All pipeline scripts (R02, R03, and future scripts) call functions
from this module to push datasets, stats, prompts, and logs to HF.

Requirements:
    - HF_TOKEN in .env
    - HF_REPO_ID in .env  (e.g. "your-org/city-sentiment-artifacts")

Usage:
    from artifacts import log_filter_run, log_sentiment_run
"""

import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("artifacts")

# ==========================================
# Configuration
# ==========================================

HF_TOKEN   = os.getenv("HF_TOKEN")
HF_REPO_ID = os.getenv("HF_REPO_ID", "your-org/city-sentiment-artifacts")

# Every artifact lives under: {STAGE}/{run_id}/{file}
# e.g.  reddit_filter/run_20260527/stats.json
#        reddit_comments/run_20260527/prompt.txt

# ==========================================
# Internal helpers
# ==========================================

def _get_api():
    """Return an authenticated HfApi instance, or raise clearly."""
    try:
        from huggingface_hub import HfApi
    except ImportError:
        raise ImportError(
            "huggingface_hub is not installed. Run: pip install huggingface-hub"
        )
    if not HF_TOKEN:
        raise ValueError("HF_TOKEN environment variable is not set.")
    return HfApi(token=HF_TOKEN)


def _ensure_repo(api):
    """Create the dataset repo on HF Hub if it does not exist yet."""
    from huggingface_hub import create_repo
    create_repo(
        repo_id=HF_REPO_ID,
        repo_type="dataset",
        exist_ok=True,
        token=HF_TOKEN,
        private=True,
    )


def _upload(local_path: str, repo_path: str, api):
    """Upload a single local file to the HF Hub dataset repo."""
    api.upload_file(
        path_or_fileobj=local_path,
        path_in_repo=repo_path,
        repo_id=HF_REPO_ID,
        repo_type="dataset",
        token=HF_TOKEN,
        commit_message=f"artifact: {repo_path}",
    )
    log.info(f"  ✅ Uploaded → hf://{HF_REPO_ID}/{repo_path}")


def _write_tmp(data: dict | str | list, suffix: str) -> Path:
    """Write data to a temp file in /tmp and return its path."""
    tmp = Path("/tmp") / f"artifact_{suffix}"
    if isinstance(data, str):
        tmp.write_text(data, encoding="utf-8")
    else:
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return tmp


# ==========================================
# R02 — Reddit Post Filtering
# ==========================================

def log_filter_run(
    run_id: str,
    total_found: int,
    total_processed: int,
    total_relevant: int,
    total_excluded: int,
    stopped_early: bool,
    prompt_template: str,
    model: str,
    source_collection: str,
    target_collection: str,
    extra: dict | None = None,
):
    """
    Call this at the END of R02 (after the summary block).

    Pushes to HF Hub:
        reddit_filter/{run_id}/stats.json   — counts & rates
        reddit_filter/{run_id}/prompt.txt   — the exact prompt used
        reddit_filter/{run_id}/meta.json    — model, collections, timestamp

    Args:
        run_id:             e.g. "run_20260527"
        total_found:        posts found in MongoDB for the date
        total_processed:    posts actually sent to Groq
        total_relevant:     posts saved to TARGET_COLLECTION
        total_excluded:     total_processed - total_relevant
        stopped_early:      True if a GroqLimitError broke the loop
        prompt_template:    the PROMPT_TEMPLATE string from R02
        model:              GROQ_MODEL value
        source_collection:  MongoDB source collection name
        target_collection:  MongoDB target collection name
        extra:              any additional key/value pairs to include in stats
    """
    log.info(f"[artifacts] Logging R02 filter run: {run_id}")

    relevancy_rate = (
        round((total_relevant / total_processed) * 100, 2)
        if total_processed > 0 else 0.0
    )
    exclusion_rate = (
        round((total_excluded / total_processed) * 100, 2)
        if total_processed > 0 else 0.0
    )

    stats = {
        "run_id":            run_id,
        "stage":             "reddit_filter",
        "timestamp_utc":     datetime.now(timezone.utc).isoformat(),
        "source_collection": source_collection,
        "target_collection": target_collection,
        "model":             model,
        "stopped_early":     stopped_early,
        "counts": {
            "total_found":       total_found,
            "total_processed":   total_processed,
            "total_relevant":    total_relevant,
            "total_excluded":    total_excluded,
            "not_reached":       total_found - total_processed,
        },
        "rates": {
            "relevancy_pct":  relevancy_rate,
            "exclusion_pct":  exclusion_rate,
        },
    }
    if extra:
        stats["extra"] = extra

    try:
        api = _get_api()
        _ensure_repo(api)

        # 1. stats.json
        stats_path = _write_tmp(stats, f"{run_id}_r02_stats.json")
        _upload(str(stats_path), f"reddit_filter/{run_id}/stats.json", api)

        # 2. prompt.txt
        prompt_path = _write_tmp(prompt_template, f"{run_id}_r02_prompt.txt")
        _upload(str(prompt_path), f"reddit_filter/{run_id}/prompt.txt", api)

        # 3. meta.json (lightweight, quick-scannable)
        meta = {
            "run_id":  run_id,
            "stage":   "reddit_filter",
            "model":   model,
            "timestamp_utc": stats["timestamp_utc"],
        }
        meta_path = _write_tmp(meta, f"{run_id}_r02_meta.json")
        _upload(str(meta_path), f"reddit_filter/{run_id}/meta.json", api)

        log.info(f"[artifacts] R02 artifacts pushed for {run_id} ✅")

    except Exception as e:
        log.error(f"[artifacts] Failed to push R02 artifacts: {e}")
        log.warning("[artifacts] Pipeline continues — artifact logging is non-blocking.")


# ==========================================
# R03 — Reddit Comments Sentiment
# ==========================================

def log_sentiment_run(
    run_id: str,
    total_found: int,
    total_processed: int,
    total_relevant: int,
    total_excluded: int,
    stopped_early: bool,
    prompt_template: str,
    model: str,
    source_collection: str,
    target_collection: str,
    extra: dict | None = None,
):
    """
    Call this at the END of R03 (after the summary block).

    Pushes to HF Hub:
        reddit_comments/{run_id}/stats.json
        reddit_comments/{run_id}/prompt.txt
        reddit_comments/{run_id}/meta.json

    Args:  (same as log_filter_run, but stage = reddit_comments)
    """
    log.info(f"[artifacts] Logging R03 sentiment run: {run_id}")

    relevancy_rate = (
        round((total_relevant / total_processed) * 100, 2)
        if total_processed > 0 else 0.0
    )
    exclusion_rate = (
        round((total_excluded / total_processed) * 100, 2)
        if total_processed > 0 else 0.0
    )

    stats = {
        "run_id":            run_id,
        "stage":             "reddit_comments",
        "timestamp_utc":     datetime.now(timezone.utc).isoformat(),
        "source_collection": source_collection,
        "target_collection": target_collection,
        "model":             model,
        "stopped_early":     stopped_early,
        "counts": {
            "total_found":       total_found,
            "total_processed":   total_processed,
            "total_relevant":    total_relevant,
            "total_excluded":    total_excluded,
            "not_reached":       total_found - total_processed,
        },
        "rates": {
            "relevancy_pct":  relevancy_rate,
            "exclusion_pct":  exclusion_rate,
        },
    }
    if extra:
        stats["extra"] = extra

    try:
        api = _get_api()
        _ensure_repo(api)

        # 1. stats.json
        stats_path = _write_tmp(stats, f"{run_id}_r03_stats.json")
        _upload(str(stats_path), f"reddit_comments/{run_id}/stats.json", api)

        # 2. prompt.txt
        prompt_path = _write_tmp(prompt_template, f"{run_id}_r03_prompt.txt")
        _upload(str(prompt_path), f"reddit_comments/{run_id}/prompt.txt", api)

        # 3. meta.json
        meta = {
            "run_id":        run_id,
            "stage":         "reddit_comments",
            "model":         model,
            "timestamp_utc": stats["timestamp_utc"],
        }
        meta_path = _write_tmp(meta, f"{run_id}_r03_meta.json")
        _upload(str(meta_path), f"reddit_comments/{run_id}/meta.json", api)

        log.info(f"[artifacts] R03 artifacts pushed for {run_id} ✅")

    except Exception as e:
        log.error(f"[artifacts] Failed to push R03 artifacts: {e}")
        log.warning("[artifacts] Pipeline continues — artifact logging is non-blocking.")


# ==========================================
# Generic: log any file directly
# ==========================================

def log_file(local_path: str, repo_path: str):
    """
    Push any arbitrary file to the HF Hub repo.
    Useful for confusion matrices, CSV exports, model cards, etc.

    Example:
        log_file("outputs/confusion_matrix.png", "evaluation/run_20260527/confusion_matrix.png")
    """
    try:
        api = _get_api()
        _ensure_repo(api)
        _upload(local_path, repo_path, api)
    except Exception as e:
        log.error(f"[artifacts] log_file failed for {local_path}: {e}")
        log.warning("[artifacts] Pipeline continues — artifact logging is non-blocking.")