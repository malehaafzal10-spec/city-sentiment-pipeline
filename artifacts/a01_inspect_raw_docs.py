"""
07_inspect_raw_docs.py — Bronze Layer Inspector
Previews the 20 most recent raw articles fetched for a specific run_id.
"""

import os
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
RAW_COLLECTION = "raw_documents_historical"

def inspect_raw_data(target_run_id=None):
    if not MONGO_URI:
        print("❌ Error: MONGO_URI is missing. Cannot connect to MongoDB.")
        return

    print(f"🔌 Connecting to MongoDB: {DB_NAME}...\n")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    # 1. Determine which run_id to look for
    if not target_run_id:
        latest_doc = db[RAW_COLLECTION].find_one(sort=[("ingestion_time", -1)])
        if not latest_doc:
            print("❌ No raw documents found in the database.")
            client.close()
            return
        target_run_id = latest_doc.get("run_id")
        print(f"No run_id provided. Defaulting to the latest run: {target_run_id}")

    # 2. Check total count for this specific run_id
    total_count = db[RAW_COLLECTION].count_documents({"run_id": target_run_id})
    
    if total_count == 0:
        print(f"❌ No documents found for run_id: '{target_run_id}'. Please check the spelling.")
        client.close()
        return

    print("="*115)
    print(f"📰 INSPECTING RAW DATA FOR RUN: {target_run_id}")
    print(f"Showing 20 of {total_count} total articles fetched.")
    print("="*115)

    # 3. Fetch only the 20 most recently published documents for this run_id
    raw_docs = list(
        db[RAW_COLLECTION]
        .find({"run_id": target_run_id})
        .sort("published_at", -1)  # Sort newest to oldest
        .limit(40)                 # Cap at 20 results
    )

    # 4. Print a formatted table of the articles
    print(f"{'Run ID':<15} | {'City':<15} | {'Title Fragment':<50} ")
    print("-" * 115)
    
    for doc in raw_docs:
        run_id = doc.get("run_id", "Unknown")
        city = doc.get("city", "Unknown")
        
        # Clean up and truncate the title
        title = doc.get("title", "No Title").replace("\n", " ").replace("\r", "")
        short_title = (title[:37] + "...") if len(title) > 37 else title
        
        # Clean up and truncate the text
        text = doc.get("text", "").replace("\n", " ").replace("\r", "")
        short_text = (text[:37] + "...") if len(text) > 37 else text
        
        print(f"{run_id:<15} | {city:<15} | {short_title:<40} ")

    print("\n" + "="*115)

    client.close()

if __name__ == "__main__":
    print("Travel Pipeline - Raw Data Inspector")
    print("Leave blank and press Enter to fetch the most recent run.")
    
    user_input = input("Enter the run_id you want to inspect (e.g., run_13042026): ").strip()
    
    inspect_raw_data(user_input if user_input else None)