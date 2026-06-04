"""
delete_collection.py
A utility script to delete all documents from a specified MongoDB collection.
"""

import os
import logging
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# Configuration & Setup
# ==========================================
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
COLLECTION_TO_CLEAR = "reddit_comments_relevant"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("clear_collection")

def main():
    log.warning("=" * 60)
    log.warning(f"WARNING: CLEARING ALL DATA FROM '{COLLECTION_TO_CLEAR}'")
    log.warning("=" * 60)

    if not MONGO_URI:
        log.error("MONGO_URI environment variable is not set.")
        return

    try:
        # Connect to MongoDB
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()  # Validate connection
        db = client[DB_NAME]
    except Exception as e:
        log.error(f"MongoDB connection failed: {e}")
        return

    # Count documents before deletion
    initial_count = db[COLLECTION_TO_CLEAR].count_documents({})
    
    if initial_count == 0:
        log.info(f"The collection '{COLLECTION_TO_CLEAR}' is already empty.")
        return

    # Execute the deletion
    # delete_many({}) matches all documents and removes them
    result = db[COLLECTION_TO_CLEAR].delete_many({})
    
    log.info(f"Successfully deleted {result.deleted_count} documents.")
    log.info(f"Collection '{COLLECTION_TO_CLEAR}' is now empty.")

if __name__ == "__main__":
    # Optional: You can add an input() prompt here if you want an extra safety check
    # confirm = input(f"Are you sure you want to delete all data in {COLLECTION_TO_CLEAR}? (yes/no): ")
    # if confirm.lower() == 'yes':
    #     main()
    # else:
    #     print("Aborted.")
    main()