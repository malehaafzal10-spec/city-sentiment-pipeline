"""
clear_scored_docs.py — Utility to truncate the Gold layer.
Safely deletes all documents in the 'scored_documents' collection ONLY.
"""

import os
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
SCORED_COLLECTION = "document_features"

def clear_scored_collection():
    if not MONGO_URI:
        print("❌ Error: MONGO_URI is missing. Cannot connect to MongoDB.")
        return

    print(f"🔌 Connecting to MongoDB: {DB_NAME}...")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    # 1. Check how many documents exist
    count = db[SCORED_COLLECTION].count_documents({})
    
    if count == 0:
        print(f"\n✅ The collection '{SCORED_COLLECTION}' is already empty. Nothing to do.")
        client.close()
        return

    print("="*60)
    print(f"⚠️  WARNING: You are about to delete all {count} documents from '{SCORED_COLLECTION}'.")
    print("This will NOT affect raw_documents, processed_documents, or artifacts.")
    print("="*60)

    # 2. Ask for confirmation
    confirm = input("Type 'yes' to confirm deletion: ")

    if confirm.strip().lower() != 'yes':
        print("\nAborted. No data was changed.")
        client.close()
        return

    # 3. Execute deletion
    print("\nExecuting deletion...")
    result = db[SCORED_COLLECTION].delete_many({})
    
    print(f"🗑️  Successfully deleted {result.deleted_count} documents from '{SCORED_COLLECTION}'.")

    client.close()

if __name__ == "__main__":
    clear_scored_collection()