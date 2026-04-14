"""
08_inspect_processed_docs.py — Silver Layer Inspector
Previews the 20 most recent documents that passed the Step 2 LLM filters and were successfully scraped.
"""

import os
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
PROCESSED_COLLECTION = "processed_documents"

def inspect_processed_data(target_run_id=None):
    if not MONGO_URI:
        print("❌ Error: MONGO_URI is missing. Cannot connect to MongoDB.")
        return

    print(f"🔌 Connecting to MongoDB: {DB_NAME}...\n")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    # 1. Determine which run_id to look for
    if not target_run_id:
        latest_doc = db[PROCESSED_COLLECTION].find_one(sort=[("processed_time", -1)])
        if not latest_doc:
            print("❌ No processed documents found in the database. Step 2 might not have kept any articles.")
            client.close()
            return
        target_run_id = latest_doc.get("run_id")
        print(f"No run_id provided. Defaulting to the latest run: {target_run_id}")

    # 2. Check total count for this specific run_id
    total_count = db[PROCESSED_COLLECTION].count_documents({"run_id": target_run_id})
    
    if total_count == 0:
        print(f"❌ No processed documents found for run_id: '{target_run_id}'.")
        client.close()
        return

    print("="*120)
    print(f"✨ INSPECTING SILVER DATA (PROCESSED) FOR RUN: {target_run_id}")
    print(f"Showing 20 of {total_count} total articles that passed the filters.")
    print("="*120)

    # 3. Fetch only the 20 most recently processed documents for this run_id
    processed_docs = list(
        db[PROCESSED_COLLECTION]
        .find({"run_id": target_run_id})
        .sort("processed_time", -1)  # Sort newest to oldest
        .limit(20)                   # Cap at 20 results
    )

    # 4. Print a formatted table of the articles
    print(f"{'City':<14} | {'Model':<8} | {'Scraped?':<8} | {'Article Title'}")
    print("-" * 120)
    
    for doc in processed_docs:
        city = doc.get("city", "Unknown")
        model = doc.get("model_used", "none")
        
        # Format the boolean flag nicely
        scraped_flag = "Yes" if doc.get("full_text_scraped") else "No"
        
        # Clean up the title and allow it to take up most of the screen width
        title = doc.get("title", "No Title").replace("\n", " ").replace("\r", "")
        display_title = (title[:82] + "...") if len(title) > 85 else title
        
        print(f"{city:<14} | {model:<8} | {scraped_flag:<8} | {display_title}")

    print("\n" + "="*120)
    print("💡 MLOps Tip:")
    print("If 'Scraped?' is 'No', the web scraper was blocked by the news site and the pipeline safely")
    print("fell back to using the original summary description from Step 1!")

    client.close()

if __name__ == "__main__":
    print("Travel Pipeline - Silver Data Inspector")
    print("Leave blank and press Enter to fetch the most recent run.")
    
    user_input = input("Enter the run_id you want to inspect (e.g., run_13042026): ").strip()
    
    inspect_processed_data(user_input if user_input else None)