import os
from pymongo import MongoClient
from dotenv import load_dotenv
from collections import Counter

load_dotenv()
client = MongoClient(os.getenv("MONGO_URI"))
db = client[os.getenv("MONGO_DB_NAME", "travel_pipeline_db")]

print("=" * 70)
print("PIPELINE DATA QUALITY CHECK")
print("=" * 70)

collections = {
    "r01_reddit_posts_raw_final": "doc_id",
    "reddit_relevant": "doc_id",
    "reddit_comments_final": "doc_id",
    "reddit_comments_relevant": "doc_id",
    "reddit_aggregated": None,  # no single unique key
}

for coll_name, unique_key in collections.items():
    coll = db[coll_name]
    total = coll.count_documents({})
    
    if unique_key:
        # Check for duplicate doc_ids
        pipeline = [
            {"$group": {"_id": f"${unique_key}", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
            {"$count": "duplicate_count"}
        ]
        result = list(coll.aggregate(pipeline))
        dupes = result[0]["duplicate_count"] if result else 0
    else:
        dupes = "N/A"

    # Check run_ids present
    run_ids = coll.distinct("run_id")
    run_ids.sort()

    print(f"\n--- {coll_name} ---")
    print(f"  Total docs:       {total}")
    print(f"  Duplicate doc_ids: {dupes}")
    print(f"  Run IDs ({len(run_ids)}):    {run_ids}")

# Check for mismatched run_ids across collections
print("\n" + "=" * 70)
print("RUN ID CONSISTENCY CHECK")
print("=" * 70)
r01_ids = set(db["r01_reddit_posts_raw_final"].distinct("run_id"))
r02_ids = set(db["reddit_relevant"].distinct("run_id"))
r03_ids = set(db["reddit_comments_final"].distinct("run_id"))
r04_ids = set(db["reddit_comments_relevant"].distinct("run_id"))
r05_ids = set(db["reddit_aggregated"].distinct("run_id"))

print(f"\nIn R01 but not R02: {r01_ids - r02_ids}")
print(f"In R02 but not R03: {r02_ids - r03_ids}")
print(f"In R03 but not R04: {r03_ids - r04_ids}")
print(f"In R04 but not R05: {r04_ids - r05_ids}")
print(f"All consistent R01→R05: {r01_ids == r02_ids == r03_ids == r04_ids == r05_ids}")

print("\n" + "=" * 70)
print("DONE")
print("=" * 70)