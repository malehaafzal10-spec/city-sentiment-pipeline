"""
09_inspect_scored_docs.py — Gold Layer Inspector
Previews the 20 most recent documents that were scored by VADER in Step 3.
"""

import os
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
SCORED_COLLECTION = "scored_documents"

def inspect_scored_data(target_run_id=None):
    if not MONGO_URI:
        print("❌ Error: MONGO_URI is missing. Cannot connect to MongoDB.")
        return

    print(f"🔌 Connecting to MongoDB: {DB_NAME}...\n")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    # 1. Determine which run_id to look for
    if not target_run_id:
        latest_doc = db[SCORED_COLLECTION].find_one(sort=[("scored_at", -1)])
        if not latest_doc:
            print("❌ No scored documents found in the database. Step 3 might not have run yet.")
            client.close()
            return
        target_run_id = latest_doc.get("run_id")
        print(f"No run_id provided. Defaulting to the latest run: {target_run_id}")

    # 2. Check total count for this specific run_id
    total_count = db[SCORED_COLLECTION].count_documents({"run_id": target_run_id})
    
    if total_count == 0:
        print(f"❌ No scored documents found for run_id: '{target_run_id}'.")
        client.close()
        return

    print("="*120)
    print(f"🥇 INSPECTING GOLD DATA (SCORED) FOR RUN: {target_run_id}")
    print(f"Showing 20 of {total_count} total articles scored.")
    print("="*120)

    # 3. Fetch only the 20 most recently scored documents for this run_id
    scored_docs = list(
        db[SCORED_COLLECTION]
        .find({"run_id": target_run_id})
        .sort("scored_at", -1)  # Sort newest to oldest
        .limit(20)              # Cap at 20 results
    )

    # 4. Print a formatted table of the articles
    print(f"{'City':<14} | {'Sentiment':<10} | {'Score':<8} | {'Article Title'}")
    print("-" * 120)
    
    for doc in scored_docs:
        city = doc.get("city", "Unknown")
        label = doc.get("sentiment_label", "neutral").capitalize()
        
        # Format the score to 4 decimal places for clean alignment
        score = doc.get("sentiment_score", 0.0)
        score_str = f"{score:>.4f}"
        
        # Clean up the title and allow it to take up most of the screen width
        title = doc.get("title", "No Title").replace("\n", " ").replace("\r", "")
        display_title = (title[:80] + "...") if len(title) > 80 else title
        
        print(f"{city:<14} | {label:<10} | {score_str:<8} | {display_title}")

    print("\n" + "="*120)


    client.close()

if __name__ == "__main__":
    print("Travel Pipeline - Gold Data Inspector")
    print("Leave blank and press Enter to fetch the most recent run.")
    
    user_input = input("Enter the run_id you want to inspect (e.g., run_13042026): ").strip()
    
    inspect_scored_data(user_input if user_input else None)