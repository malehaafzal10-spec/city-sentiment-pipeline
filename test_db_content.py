"""
test_db_contents.py — Utility to inspect the processed_documents collection.
"""

import os
import json
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
COLLECTION_NAME = "processed_documents"

def inspect_database():
    if not MONGO_URI:
        print("❌ Error: MONGO_URI is not set in your .env file.")
        return

    print(f"🔌 Connecting to MongoDB database: '{DB_NAME}'...")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    # 1. Total Count
    total_docs = collection.count_documents({})
    print("\n" + "="*50)
    print(f"📊 DATABASE SUMMARY: '{COLLECTION_NAME}'")
    print("="*50)
    print(f"Total Documents: {total_docs}")

    if total_docs == 0:
        print("The collection is empty! Run your processing pipeline first.")
        client.close()
        return

    # 2. Breakdown by City
    print("\n🏙️  Documents per City:")
    pipeline_city = [{"$group": {"_id": "$city", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
    for city_stat in collection.aggregate(pipeline_city):
        print(f"  - {city_stat['_id']}: {city_stat['count']} articles")

    # 3. Breakdown by LLM Relevance
    print("\n🤖 LLM Relevance Breakdown:")
    pipeline_llm = [{"$group": {"_id": "$llm_relevant", "count": {"$sum": 1}}}]
    for llm_stat in collection.aggregate(pipeline_llm):
        status = "Relevant (Yes)" if llm_stat['_id'] else "Not Relevant (No)"
        print(f"  - {status}: {llm_stat['count']} articles")

    # 4. Show a Sample Document
    print("\n" + "="*50)
    print("📄 SAMPLE DOCUMENT (Most Recent)")
    print("="*50)
    
    # Fetch the most recently processed document
    sample_doc = collection.find_one({}, sort=[("processed_time", -1)])
    
    if sample_doc:
        # Print a shortened version of the text so it doesn't flood the terminal
        full_text = sample_doc.get("text", "")
        preview_length = 300
        text_preview = full_text[:preview_length] + "..." if len(full_text) > preview_length else full_text

        # Create a clean dictionary to display
        display_doc = {
            "doc_id": sample_doc.get("doc_id"),
            "city": sample_doc.get("city"),
            "title": sample_doc.get("title"),
            "source": sample_doc.get("source"),
            "llm_relevant": sample_doc.get("llm_relevant"),
            "llm_reason": sample_doc.get("llm_reason"),
            "full_text_scraped": sample_doc.get("full_text_scraped"),
            "text_length": sample_doc.get("text_length"),
            "processed_time": sample_doc.get("processed_time"),
            "text_preview": text_preview
        }

        # Print nicely formatted JSON
        print(json.dumps(display_doc, indent=4, ensure_ascii=False, default=str))

    client.close()
    print("\n✅ Inspection complete.")

if __name__ == "__main__":
    inspect_database()