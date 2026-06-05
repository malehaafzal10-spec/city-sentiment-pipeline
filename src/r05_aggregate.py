import os
import sys
import re
import argparse
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==========================================
# MongoDB Configuration
# ==========================================
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

# Source and Target collections
POSTS_COLLECTION = "reddit_relevant"
COMMENTS_COLLECTION = "reddit_comments_relevant"
TARGET_COLLECTION = "reddit_aggregated"

def extract_aspects(cursor, doc_type, forced_run_id):
    rows = []
    for doc in cursor:
        id_ = str(doc.get("_id", ""))
        doc_id = doc.get("doc_id", "")
        post_id = doc.get("post_id", "")
        fetched_at = doc.get("fetched_at", doc.get("published_at", None))
        locations = doc.get("locations") or {}
        doc_cities = locations.get("cities") or []
        doc_countries = locations.get("countries") or []
        analysis = doc.get("analysis") or {}
        aspects = analysis.get("aspects") or []
        for aspect_data in aspects:
            aspect = aspect_data.get("aspect")
            sentiment_score = aspect_data.get("sentiment_score")
            city = aspect_data.get("city")
            country = aspect_data.get("country")
            if not city and not country:
                if doc_cities:
                    city = doc_cities[0]
                elif doc_countries:
                    country = doc_countries[0]
            rows.append({
                "aspect": aspect,
                "sentiment_score": sentiment_score,
                "city": city,
                "country": country,
                "id_": id_,
                "doc_id": doc_id,
                "post_id": post_id,
                "fetched_at": fetched_at,
                "run_id": forced_run_id,
                "type": doc_type
            })
    return rows

def get_unprocessed_run_ids(db) -> list:
    post_run_ids      = set(db[POSTS_COLLECTION].distinct("run_id"))
    comment_run_ids   = set(db[COMMENTS_COLLECTION].distinct("run_id"))
    all_run_ids       = post_run_ids | comment_run_ids
    processed_run_ids = set(db[TARGET_COLLECTION].distinct("run_id"))
    unprocessed = [r for r in all_run_ids if r not in processed_run_ids]
    unprocessed.sort()
    return unprocessed


def process_run_id(db, run_id: str):
    print("=" * 60)
    print(f"R05 — Aggregating run_id: {run_id}")
    print("=" * 60)

    posts_query    = {"run_id": run_id, "analysis.text_type": "review"}
    comments_query = {"run_id": run_id}

    print("Fetching POSTS (reviews only)...")
    posts_data = extract_aspects(db[POSTS_COLLECTION].find(posts_query), "post", run_id)

    print("Fetching COMMENTS...")
    comments_data = extract_aspects(db[COMMENTS_COLLECTION].find(comments_query), "comment", run_id)

    all_data = posts_data + comments_data

    if not all_data:
        print(f"No data found for run_id '{run_id}'.")
        return

    df = pd.DataFrame(all_data)
    expected_columns = [
        "aspect", "sentiment_score", "city", "country",
        "id_", "doc_id", "post_id", "fetched_at", "run_id", "type"
    ]
    df = df.reindex(columns=expected_columns)
    print(f"Merge complete! Generated {len(df)} aspect-level records.")

    target_coll    = db[TARGET_COLLECTION]
    deleted_result = target_coll.delete_many({"run_id": run_id})
    if deleted_result.deleted_count > 0:
        print(f"Cleared {deleted_result.deleted_count} old records for {run_id}.")

    records_to_insert = df.to_dict(orient="records")
    print(f"Inserting {len(records_to_insert)} records into '{TARGET_COLLECTION}'...")
    insert_result = target_coll.insert_many(records_to_insert)
    print(f"Inserted {len(insert_result.inserted_ids)} records.")

    print("=" * 60)
    print(f"SUCCESS — {run_id}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Aggregate sentiment data — auto-detects unprocessed run_ids.")
    parser.add_argument("--date", required=False, default=None,
                        help="Optional: force a specific date YYYYMMDD instead of auto-detecting")
    args = parser.parse_args()

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    if args.date:
        if not re.match(r"^[0-9]{8}$", args.date):
            print("Error: Invalid date format. Use YYYYMMDD.")
            sys.exit(1)
        cutoff = "20260601"
        run_ids_to_process = [
            f"run_{args.date}_local" if args.date <= cutoff else f"run-{args.date}-AUTO"
        ]
        print(f"Manual override: processing {run_ids_to_process[0]}")
    else:
        run_ids_to_process = get_unprocessed_run_ids(db)
        if not run_ids_to_process:
            print("✅ All run_ids already aggregated. Nothing to do.")
            return
        print(f"Found {len(run_ids_to_process)} unprocessed run_id(s): {run_ids_to_process}")

    for run_id in run_ids_to_process:
        process_run_id(db, run_id)

    print("ALL DONE")


if __name__ == "__main__":
    main()