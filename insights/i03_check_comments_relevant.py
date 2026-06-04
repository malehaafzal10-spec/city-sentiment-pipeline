import os
import sys
import json
from collections import defaultdict
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==========================================
# Configuration
# ==========================================
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
TARGET_COLLECTION = "reddit_comments_relevant"
OUTPUT_FILE = "i03_check.json"

def main():
    print("=" * 60)
    print("MONGO EXPORT AND STATISTICS SCRIPT")
    print("=" * 60)

    if not MONGO_URI:
        print("[ERROR] MONGO_URI environment variable is not set.")
        sys.exit(1)

    # ── 1. Connect to MongoDB ──────────────────────────────────────────
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()  # Test connection
        db = client[DB_NAME]
        print(f"[INFO] Successfully connected to database: '{DB_NAME}'")
    except Exception as e:
        print(f"[ERROR] MongoDB connection failed: {e}")
        sys.exit(1)

    # ── 2. Fetch all documents ─────────────────────────────────────────
    collection = db[TARGET_COLLECTION]
    posts = list(collection.find())
    total_posts = len(posts)

    if total_posts == 0:
        print(f"[INFO] No posts found in '{TARGET_COLLECTION}'. Exiting.")
        sys.exit(0)

    # ── 3. Calculate Statistics ────────────────────────────────────────
    run_id_counts = defaultdict(int)
    aspect_counts = defaultdict(int)
    aspect_sentiment_sum = defaultdict(float)

    for post in posts:
        # Count by run_id
        run_id = post.get("run_id", "unknown_run")
        run_id_counts[run_id] += 1

        # Process aspects and sentiment
        analysis = post.get("analysis", {})
        aspects = analysis.get("aspects", [])
        
        for asp in aspects:
            aspect_name = asp.get("aspect", "unknown_aspect").lower()
            score = asp.get("sentiment_score")
            
            if score is not None:
                aspect_counts[aspect_name] += 1
                aspect_sentiment_sum[aspect_name] += score

    # Calculate average sentiment per aspect
    aspect_stats = {}
    for aspect, count in aspect_counts.items():
        avg_sentiment = aspect_sentiment_sum[aspect] / count
        aspect_stats[aspect] = {
            "occurrences": count,
            "average_sentiment": round(avg_sentiment, 2)
        }

    # Sort aspects by most occurrences
    sorted_aspect_stats = dict(
        sorted(aspect_stats.items(), key=lambda item: item[1]["occurrences"], reverse=True)
    )

    # ── 4. Save to JSON ────────────────────────────────────────────────
    # We use default=str in json.dump to safely serialize MongoDB ObjectIds and Datetimes
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(posts, f, indent=2, default=str)
        print(f"\n[SUCCESS] Successfully saved {total_posts} records to '{OUTPUT_FILE}'")
    except Exception as e:
        print(f"[ERROR] Failed to save JSON file: {e}")

    # ── 5. Print Statistics Summary ────────────────────────────────────
    print("\n" + "=" * 60)
    print("DATA STATISTICS SUMMARY")
    print("=" * 60)
    print(f"Total Relevant Posts Saved:  {total_posts}")
    
    print("\n--- Posts per Run ID ---")
    for r_id, count in run_id_counts.items():
        print(f"  {r_id}: {count}")

    print("\n--- Top Travel Aspects Detected ---")
    if not sorted_aspect_stats:
        print("  No aspects found.")
    else:
        for aspect, stats in list(sorted_aspect_stats.items())[:10]: # Print top 10
            print(f"  - {aspect.capitalize()}: {stats['occurrences']} mentions (Avg Sentiment: {stats['average_sentiment']}/5)")
    print("=" * 60)

if __name__ == "__main__":
    main()