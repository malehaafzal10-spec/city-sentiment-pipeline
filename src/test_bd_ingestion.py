"""
04_test_db_state.py — Database Audit & Monitoring Script
Provides a quick summary of the travel pipeline's health, data flow, and latest records.
"""

import os
import json
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

# Collections
RAW_COLLECTION = "raw_documents_historical"
PROCESSED_COLLECTION = "processed_documents"
SCORED_COLLECTION = "scored_documents"
ARTIFACTS_COLLECTION = "pipeline_artifacts"

def run_db_diagnostics():
    if not MONGO_URI:
        print("❌ Error: MONGO_URI is missing from environment variables.")
        return

    print(f"🔌 Connecting to MongoDB: {DB_NAME}...\n")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    print("="*60)
    print("📊 PIPELINE HEALTH & FUNNEL METRICS")
    print("="*60)
    
    # 4. OTHER RELEVANT INFO: Data Funnel Health
    # In MLOps, we always want to see the drop-off rate between pipeline stages.
    raw_count = db[RAW_COLLECTION].count_documents({})
    processed_count = db[PROCESSED_COLLECTION].count_documents({})
    scored_count = db[SCORED_COLLECTION].count_documents({})
    artifact_count = db[ARTIFACTS_COLLECTION].count_documents({})

    print(f"Bronze Layer (Raw):       {raw_count} documents")
    print(f"Silver Layer (Processed): {processed_count} documents")
    print(f"Gold Layer (Scored):      {scored_count} documents")
    print(f"Artifact Snapshots:       {artifact_count} artifacts saved\n")

    print("="*60)
    print("🗓️  DOCUMENTS SCORED BY RUN_ID (DATE)")
    print("="*60)
    
    # 1 & 3. Number of documents sorted by Date / Run ID and Total Unique Runs
    pipeline = [
        {"$group": {"_id": "$run_id", "count": {"$sum": 1}}},
        {"$sort": {"_id": -1}} # Sort descending (newest runs first)
    ]
    
    run_stats = list(db[SCORED_COLLECTION].aggregate(pipeline))
    
    print(f"Total Unique Pipeline Runs: {len(run_stats)}\n")
    print(f"{'Run ID':<20} | {'Documents Scored':<15}")
    print("-" * 40)
    for stat in run_stats:
        print(f"{stat['_id']:<20} | {stat['count']:<15}")
    print("\n")

    print("="*60)
    print("📈 SENTIMENT DISTRIBUTION (OVERALL)")
    print("="*60)
    
    # 4. OTHER RELEVANT INFO: Overall Sentiment Balance
    # Ensures the VADER model isn't skewing 100% positive or negative due to a bug.
    sentiment_pipeline = [
        {"$group": {"_id": "$sentiment_label", "count": {"$sum": 1}}}
    ]
    sentiments = list(db[SCORED_COLLECTION].aggregate(sentiment_pipeline))
    
    for s in sentiments:
        label = str(s['_id']).capitalize()
        print(f"{label:<10}: {s['count']}")
    print("\n")

    print("="*60)
    print("🆕 20 NEWEST ROWS IN THE GOLD TABLE (SCORED DOCUMENTS)")
    print("="*60)
    
    # 2. 20 newest rows of the table
    # Sorting by 'scored_at' descending to get the freshest data
    newest_docs = list(db[SCORED_COLLECTION].find(
        {}, 
        {"_id": 0, "city": 1, "sentiment_label": 1, "sentiment_score": 1, "scored_at": 1, "run_id": 1, "title": 1}
    ).sort("scored_at", -1).limit(20))

    if not newest_docs:
        print("No scored documents found.")
    else:
        # Print a formatted table header
        print(f"{'Date Scored':<22} | {'City':<15} | {'Label':<8} | {'Score':<6} | {'Title Fragment'}")
        print("-" * 100)
        
        for doc in newest_docs:
            date_scored = doc.get('scored_at', 'N/A')[:19] # Truncate microseconds
            city = doc.get('city', 'Unknown')
            label = doc.get('sentiment_label', 'N/A')
            score = str(doc.get('sentiment_score', 'N/A'))
            
            # Fetch title from the raw/processed layer if it exists, otherwise truncate text
            title = doc.get('title', 'No title available')
            short_title = (title[:45] + '...') if len(title) > 45 else title
            
            print(f"{date_scored:<22} | {city:<15} | {label:<8} | {score:<6} | {short_title}")

    client.close()
    print("\n✅ Diagnostics Complete.")

if __name__ == "__main__":
    run_db_diagnostics()