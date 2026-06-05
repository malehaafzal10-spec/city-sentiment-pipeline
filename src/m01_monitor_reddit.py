"""
monitor_pipeline.py — Pipeline Dashboard Monitor

Scans all MongoDB collections in the pipeline and counts 
documents grouped by their run_id.

Usage:
    python monitor_pipeline.py
"""

import os
import logging
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(override=True)

# ==========================================
# Configuration
# ==========================================
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

# Define the collections you want to monitor and a short display name for the table
COLLECTIONS = {
    "r01_reddit_posts_raw_final": "Posts",
    "reddit_relevant": "Rel. Posts",
    "reddit_comments_final": "Comments",
    "reddit_comments_relevant": "Rel. Comms",
    "reddit_aggregated": "Aggregated"
}

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("monitor")

def main():
    if not MONGO_URI:
        log.error("❌ MONGO_URI not found in environment variables.")
        return

    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()  # Test connection
        db = client[DB_NAME]
    except Exception as e:
        log.error(f"❌ MongoDB connection failed: {e}")
        return

    # Data structure to hold counts: { run_id: { collection_name: count } }
    dashboard_data = {}
    all_run_ids = set()

    log.info("📊 Fetching pipeline statistics...\n")

    # Aggregate counts for each collection
    for coll_name in COLLECTIONS.keys():
        try:
            pipeline = [
                {"$group": {"_id": "$run_id", "count": {"$sum": 1}}}
            ]
            results = list(db[coll_name].aggregate(pipeline))
            
            for row in results:
                # Handle documents that might be missing a run_id
                run_id = row.get("_id") 
                if not run_id:
                    run_id = "[MISSING_RUN_ID]"
                
                count = row.get("count", 0)
                
                if run_id not in dashboard_data:
                    dashboard_data[run_id] = {c: 0 for c in COLLECTIONS.keys()}
                
                dashboard_data[run_id][coll_name] = count
                all_run_ids.add(run_id)
                
        except Exception as e:
            log.warning(f"⚠️ Could not read collection '{coll_name}': {e}")

    client.close()

    # ==========================================
    # Render the Table
    # ==========================================
    if not all_run_ids:
        log.info("No data found in any pipeline collections.")
        return

    # Sort run_ids alphabetically/chronologically
    sorted_run_ids = sorted(list(all_run_ids))

    # Calculate column widths
    max_run_id_len = max(len(r) for r in sorted_run_ids)
    run_id_width = max(max_run_id_len, 30)
    col_width = 12

    # Build Header
    header_str = f"{'RUN ID'.ljust(run_id_width)} | "
    header_str += " | ".join(name.center(col_width) for name in COLLECTIONS.values())
    
    separator = "-" * len(header_str)
    
    log.info("=" * len(header_str))
    log.info(" PIPELINE MONITORING DASHBOARD")
    log.info("=" * len(header_str))
    log.info(header_str)
    log.info(separator)

    # Build Rows
    for run_id in sorted_run_ids:
        row_str = f"{run_id.ljust(run_id_width)} | "
        counts = []
        for coll_name in COLLECTIONS.keys():
            val = dashboard_data[run_id][coll_name]
            # Print "-" if 0 for cleaner reading, otherwise print the number
            display_val = str(val) if val > 0 else "-"
            counts.append(display_val.rjust(col_width))
            
        row_str += " | ".join(counts)
        log.info(row_str)

    log.info("=" * len(header_str))
    
    # Calculate and print Grand Totals
    log.info(f"{'GRAND TOTALS'.ljust(run_id_width)} | " + " | ".join(
        str(sum(dashboard_data[r][c] for r in sorted_run_ids)).rjust(col_width) 
        for c in COLLECTIONS.keys()
    ))
    log.info("=" * len(header_str))

if __name__ == "__main__":
    main()