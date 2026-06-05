"""
r01_backfill_run_ids.py — One-time script.

Reads all existing posts from reddit_posts_final, assigns run_id based on
published_at date, and copies them to r01_reddit_posts_raw_final.

Run ID logic:
    published_at <= 2026-06-01  →  run_YYYYMMDD_local
    published_at >  2026-06-01  →  run-YYYYMMDD-AUTO

Usage:
    python src/r01_backfill_run_ids.py
"""

import os
import logging
from datetime import datetime, timezone
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv

load_dotenv()

MONGO_URI  = os.getenv("MONGO_URI")
DB_NAME    = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
SOURCE     = "reddit_posts_final"
DEST       = "r01_reddit_posts_raw_final"
CUTOFF_STR = "2026-06-01"  # on or before this = local, after = AUTO

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("r01_backfill")


def assign_run_id(published_at: str) -> str:
    """Derive run_id from published_at date string."""
    try:
        date_str = published_at[:10]  # YYYY-MM-DD
        compact  = date_str.replace("-", "")  # YYYYMMDD
        if date_str <= CUTOFF_STR:
            return f"run_{compact}_local"
        else:
            return f"run-{compact}-AUTO"
    except Exception:
        return "run_UNKNOWN_local"


def main():
    log.info("=" * 60)
    log.info("R01 BACKFILL — Assigning run IDs to existing posts")
    log.info(f"Source:  {SOURCE}")
    log.info(f"Dest:    {DEST}")
    log.info(f"Cutoff:  on/before {CUTOFF_STR} → run_YYYYMMDD_local")
    log.info(f"         after {CUTOFF_STR}      → run-YYYYMMDD-AUTO")
    log.info("=" * 60)

    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.server_info()
    log.info("MongoDB connection OK ✓")
    db = client[DB_NAME]

    posts = list(db[SOURCE].find({}))
    log.info(f"Found {len(posts)} posts in '{SOURCE}'")

    if not posts:
        log.warning("Nothing to backfill")
        return

    operations  = []
    local_count = 0
    auto_count  = 0

    for post in posts:
        post.pop("_id", None)
        run_id       = assign_run_id(post.get("published_at", ""))
        post["run_id"] = run_id

        if "local" in run_id:
            local_count += 1
        else:
            auto_count += 1

        operations.append(
            UpdateOne(
                {"doc_id": post["doc_id"]},
                {"$setOnInsert": post},
                upsert=True
            )
        )

        if len(operations) >= 200:
            db[DEST].bulk_write(operations)
            operations = []

    if operations:
        db[DEST].bulk_write(operations)

    client.close()

    log.info("=" * 60)
    log.info("BACKFILL COMPLETE")
    log.info(f"Total processed: {len(posts)}")
    log.info(f"LOCAL run IDs:   {local_count}  (run_YYYYMMDD_local)")
    log.info(f"AUTO run IDs:    {auto_count}   (run-YYYYMMDD-AUTO)")
    log.info(f"Destination:     {DEST}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()