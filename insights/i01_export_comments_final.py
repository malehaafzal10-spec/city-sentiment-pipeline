import os
import sys
import json
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==========================================
# Configuration
# ==========================================
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
SOURCE_COLLECTION = "reddit_comments_final"
OUTPUT_FILE = "reddit_comments_final_export.json"

def main():
    print("=" * 60)
    print(f"MONGO EXPORT: {SOURCE_COLLECTION}")
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
    collection = db[SOURCE_COLLECTION]
    
    print(f"[INFO] Fetching documents from '{SOURCE_COLLECTION}'...")
    posts = list(collection.find())
    total_posts = len(posts)

    if total_posts == 0:
        print(f"[INFO] No posts found in '{SOURCE_COLLECTION}'. Exiting.")
        sys.exit(0)

    # ── 3. Save to JSON ────────────────────────────────────────────────
    # default=str is crucial here to prevent crashes when JSON tries to 
    # serialize MongoDB ObjectIds or Datetime objects.
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(posts, f, indent=2, default=str)
        print(f"\n[SUCCESS] Successfully saved {total_posts} records to '{OUTPUT_FILE}'")
    except Exception as e:
        print(f"[ERROR] Failed to save JSON file: {e}")

    # ── 4. Print Summary ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("EXTRACTION SUMMARY")
    print("=" * 60)
    print(f"Collection:      {SOURCE_COLLECTION}")
    print(f"Total Extracted: {total_posts} documents")
    print(f"Output File:     {OUTPUT_FILE}")
    print("=" * 60)

if __name__ == "__main__":
    main()