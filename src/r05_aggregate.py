import os
import sys
import re
import argparse
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==========================================
# MongoDB Configuration
# ==========================================
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

# Source and Target collections
POSTS_COLLECTION = "reddit_relevant"
COMMENTS_COLLECTION = "reddit_comments_relevant"
TARGET_COLLECTION = "reddit_aggregated"

def extract_aspects(cursor, doc_type, forced_run_id):
    """
    Iterates through MongoDB documents and extracts aspect-level data.
    If an aspect lacks both city and country, it falls back to the 
    document-level locations block. The run_id is standardized.
    """
    rows = []
    for doc in cursor:
        # 1. Extract document-level metadata
        id_ = str(doc.get("_id", ""))
        doc_id = doc.get("doc_id", "")
        post_id = doc.get("post_id", "")
        fetched_at = doc.get("fetched_at", doc.get("published_at", None))
        
        # 2. Extract document-level locations for fallback
        locations = doc.get("locations") or {}
        doc_cities = locations.get("cities") or []
        doc_countries = locations.get("countries") or []
        
        # 3. Access the nested analysis object
        analysis = doc.get("analysis") or {}
        aspects = analysis.get("aspects") or []
        
        # 4. Extract data directly from each aspect
        for aspect_data in aspects:
            aspect = aspect_data.get("aspect")
            sentiment_score = aspect_data.get("sentiment_score")
            
            # Extract city and country directly from the aspect dictionary
            city = aspect_data.get("city")
            country = aspect_data.get("country")
            
            # ----------------------------------------------------
            # FALLBACK LOGIC: 
            # If both city and country are missing in the aspect,
            # pull from the document-level locations structure.
            # ----------------------------------------------------
            if not city and not country:
                if doc_cities:
                    city = doc_cities[0]  # Take the first city if available
                elif doc_countries:
                    country = doc_countries[0]  # Take the first country if no cities exist
            
            rows.append({
                "aspect": aspect,
                "sentiment_score": sentiment_score,
                "city": city,
                "country": country,
                "id_": id_,
                "doc_id": doc_id,
                "post_id": post_id,
                "fetched_at": fetched_at,
                "run_id": forced_run_id,  # Ensure uniform run_id formatting
                "type": doc_type
            })
            
    return rows

def main():
    parser = argparse.ArgumentParser(description="Merge and aggregate sentiment data.")
    parser.add_argument(
        "--date",
        type=str,
        required=True,
        help="Target date in YYYYMMDD format to match previous processes (e.g., 20260527)"
    )
    args = parser.parse_args()

    if not re.match(r"^\d{8}$", args.date):
        print("Error: Invalid date format. Please use YYYYMMDD (e.g., 20260527).")
        sys.exit(1)

    target_date = args.date
    output_run_id = f"run_{target_date}_local"

    print("=" * 60)
    print("MERGE AND AGGREGATE SENTIMENT DATA")
    print("=" * 60)
    print(f"Target Date:      {target_date}")
    print(f"Output Run ID:    {output_run_id}")
    print("=" * 60)

    # Connect to MongoDB
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    
    # ==========================================
    # Custom Queries per Collection
    # ==========================================
    # Filter POSTS to only include documents where text_type is "review" and matches date
    posts_query = {
        "run_id": {"$regex": f"^run_{target_date}"},
        "analysis.text_type": "review"
    }
    
    # Comments just need the matching run_id date prefix
    comments_query = {
        "run_id": {"$regex": f"^run_{target_date}"}
    }
    
    # Fetch and process posts
    print(f"Fetching POSTS (reviews only) for date {target_date}...")
    posts_cursor = db[POSTS_COLLECTION].find(posts_query)
    posts_data = extract_aspects(posts_cursor, "post", output_run_id)
    
    # Fetch and process comments
    print(f"Fetching COMMENTS for date {target_date}...")
    comments_cursor = db[COMMENTS_COLLECTION].find(comments_query)
    comments_data = extract_aspects(comments_cursor, "comment", output_run_id)
    
    # Combine the flattened lists
    all_data = posts_data + comments_data
    
    if not all_data:
        print(f"No data found matching date '{target_date}' in either collection.")
        return
    
    # Create the DataFrame to enforce schema/column order
    df = pd.DataFrame(all_data)
    expected_columns = [
        "aspect", "sentiment_score", "city", "country", 
        "id_", "doc_id", "post_id", "fetched_at", "run_id", "type"
    ]
    df = df.reindex(columns=expected_columns)
    
    print(f"Merge complete! Generated {len(df)} aspect-level records.")
    
    # ==========================================
    # Save to MongoDB
    # ==========================================
    target_coll = db[TARGET_COLLECTION]
    
    # Idempotency: Remove old documents for this specific output_run_id to avoid duplicates
    delete_query = {"run_id": output_run_id}
    deleted_result = target_coll.delete_many(delete_query)
    if deleted_result.deleted_count > 0:
        print(f"Cleared {deleted_result.deleted_count} old records from '{TARGET_COLLECTION}' for {output_run_id}.")
    
    # Convert DataFrame back to a list of dictionaries for MongoDB insertion
    records_to_insert = df.to_dict(orient="records")
    
    # Insert the new aggregated data
    print(f"Inserting {len(records_to_insert)} records into '{TARGET_COLLECTION}'...")
    insert_result = target_coll.insert_many(records_to_insert)
    
    print("=" * 60)
    print("SUCCESS")
    print(f"Inserted {len(insert_result.inserted_ids)} records.")
    print("=" * 60)

if __name__ == "__main__":
    main()