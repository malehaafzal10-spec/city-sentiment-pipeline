"""
10_inspect_features.py — Gold Aggregations Inspector
Previews the city-level weekly aggregated features generated in Step 4.
"""

import os
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
CITY_FEATURES_COLLECTION = "city_weekly_features"

def inspect_features(target_run_id=None):
    if not MONGO_URI:
        print("❌ Error: MONGO_URI is missing. Cannot connect to MongoDB.")
        return

    print(f"🔌 Connecting to MongoDB: {DB_NAME}...\n")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    # 1. Determine which run_id to look for
    if not target_run_id:
        latest_doc = db[CITY_FEATURES_COLLECTION].find_one(sort=[("aggregated_at", -1)])
        if not latest_doc:
            print("❌ No features found in the database. Step 4 might not have run yet.")
            client.close()
            return
        target_run_id = latest_doc.get("run_id")
        print(f"No run_id provided. Defaulting to the latest run: {target_run_id}")

    # 2. Check total count for this specific run_id
    total_count = db[CITY_FEATURES_COLLECTION].count_documents({"run_id": target_run_id})
    
    if total_count == 0:
        print(f"❌ No features found for run_id: '{target_run_id}'.")
        client.close()
        return

    print("="*100)
    print(f"📊 INSPECTING CITY AGGREGATES FOR RUN: {target_run_id}")
    print(f"Showing {total_count} cities aggregated in this run.")
    print("="*100)

    # 3. Fetch the aggregated documents for this run_id
    features = list(
        db[CITY_FEATURES_COLLECTION]
        .find({"run_id": target_run_id})
        .sort("mention_count", -1)  # Sort by most mentioned city descending
    )

    # 4. Print a formatted table of the aggregates
    print(f"{'City':<15} | {'Mentions':<9} | {'Avg Sent':<9} | {'% Pos':<6} | {'Crowd':<6} | {'Cost':<6} | {'Safety':<6}")
    print("-" * 100)
    
    for doc in features:
        city = doc.get("city", "Unknown")
        mentions = doc.get("mention_count", 0)
        
        # Format metrics for clean alignment
        avg_sent = f"{doc.get('avg_sentiment', 0.0):.3f}"
        pos_ratio = f"{doc.get('positive_ratio', 0.0) * 100:.0f}%"
        
        crowd = f"{doc.get('crowding_score', 0.0):.3f}"
        cost = f"{doc.get('cost_score', 0.0):.3f}"
        safety = f"{doc.get('safety_score', 0.0):.3f}"
        
        print(f"{city:<15} | {mentions:<9} | {avg_sent:<9} | {pos_ratio:<6} | {crowd:<6} | {cost:<6} | {safety:<6}")

    print("\n" + "="*100)
    print("💡 MLOps Tip:")
    print("This table represents the final data layer for your dashboard.")
    print("The 'Crowd', 'Cost', and 'Safety' scores represent the average number of times")
    print("keywords belonging to those dimensions were mentioned per article.")

    client.close()

if __name__ == "__main__":
    print("Travel Pipeline - City Features Inspector")
    print("Leave blank and press Enter to fetch the most recent run.")
    
    user_input = input("Enter the run_id you want to inspect (e.g., run_13042026): ").strip()
    
    inspect_features(user_input if user_input else None)