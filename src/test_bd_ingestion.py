"""
test_db_ingestion.py — Standalone test script to verify data in MongoDB.
Run this after executing 01_ingest.py to ensure data and artifacts are stored correctly.
"""

import os
from pprint import pprint
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables (ensure your .env has MONGO_URI)
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

def test_database_records():
    if not MONGO_URI:
        print("❌ Error: MONGO_URI is not set in your environment variables.")
        return

    print(f"🔄 Connecting to MongoDB: {DB_NAME}...")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    try:
        # 1. Show all the tables (collections) in the database
        collections = db.list_collection_names()
        print("\n" + "="*50)
        print("📁 COLLECTIONS (TABLES) IN DATABASE:")
        print("="*50)
        if collections:
            for col in collections:
                count = db[col].count_documents({})
                print(f" - {col} (Documents: {count})")
        else:
            print(" No collections found. The database is empty.")
            return

        # 2. Print data from the tables stored by 01_ingest.py
        collections_to_check = ["raw_documents", "pipeline_artifacts"]

        for col_name in collections_to_check:
            if col_name in collections:
                print("\n" + "="*50)
                print(f"📄 SAMPLE DATA FROM: '{col_name}'")
                print("="*50)
                
                # Fetch up to 2 recent documents to avoid exploding the terminal
                cursor = db[col_name].find().sort("_id", -1).limit(2)
                docs = list(cursor)
                
                if docs:
                    for i, doc in enumerate(docs, 1):
                        print(f"\n--- Document {i} ---")
                        
                        # If it's an artifact, truncate the payload list for readability
                        if col_name == "pipeline_artifacts" and "payload" in doc:
                            payload_len = len(doc["payload"])
                            doc["payload"] = f"[ ... List of {payload_len} documents omitted for brevity ... ]"
                            
                        # If it's a raw document, truncate the text slightly
                        if col_name == "raw_documents" and "text" in doc:
                            doc["text"] = doc["text"][:150] + " ... [TRUNCATED]"

                        pprint(doc, sort_dicts=False)
                else:
                    print(f" Collection '{col_name}' exists but is currently empty.")
            else:
                print(f"\n⚠️ Collection '{col_name}' does not exist yet. Did 01_ingest.py run successfully?")

    except Exception as e:
        print(f"❌ Database error: {e}")
    finally:
        client.close()
        print("\n🔌 Connection closed.")

if __name__ == "__main__":
    test_database_records()