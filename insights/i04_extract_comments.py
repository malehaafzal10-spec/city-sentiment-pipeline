"""
r05_export_sample.py — Script to fetch a random sample of analyzed Reddit comments
from MongoDB and save them locally as a JSON file.

Requirements:
    - MONGO_URI in .env
    - MONGO_DB_NAME in .env

Usage:
    python r05_export_sample.py --size 50 --out my_sample.json
"""

import os
import json
import logging
import argparse
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(override=True)

# ==========================================
# Configuration & Setup
# ==========================================

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
TARGET_COLLECTION = "reddit_comments_relevant"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("export_mongo_sample")

if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable is not set.")

# ==========================================
# Core Processing Logic
# ==========================================

def export_sample(sample_size, output_file):
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()  # Force connection check
        db = client[DB_NAME]
        
        log.info(f"Connected to Database: {DB_NAME}")
        log.info(f"Target Collection:     {TARGET_COLLECTION}")
        log.info(f"Requested Sample Size: {sample_size}")
        
        # Use the $sample aggregation pipeline for a true random subset
        pipeline = [{"$sample": {"size": sample_size}}]
        cursor = db[TARGET_COLLECTION].aggregate(pipeline)
        
        sample_docs = []
        for doc in cursor:
            # MongoDB's ObjectId is not naturally JSON serializable, so we remove it
            doc.pop('_id', None)
            sample_docs.append(doc)
        
        if not sample_docs:
            log.warning("No documents found in the collection to sample.")
            return

        # Save to local JSON file
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(sample_docs, f, indent=2, ensure_ascii=False)
            
        log.info(f"✅ Successfully exported {len(sample_docs)} documents to '{output_file}'.")

    except Exception as e:
        log.error(f"Database or execution error: {e}")

def main():
    log.info("=" * 60)
    log.info("EXPORT MONGODB SAMPLE")
    
    parser = argparse.ArgumentParser(description="Export a random sample from MongoDB.")
    parser.add_argument(
        "--size", 
        type=int, 
        default=100, 
        help="Number of documents to extract (default: 100)"
    )
    parser.add_argument(
        "--out", 
        type=str, 
        default="sample_reddit_relevant.json", 
        help="Output JSON file name (default: sample_reddit_relevant.json)"
    )
    args = parser.parse_args()
    
    log.info("=" * 60)
    export_sample(args.size, args.out)
    log.info("=" * 60)

if __name__ == "__main__":
    main()