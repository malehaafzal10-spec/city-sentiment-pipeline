import os
import sys
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
TARGET_COLLECTION = "reddit_aggregated"

def main():
    print("=" * 60)
    print("GENERATE EXECUTION STATISTICS")
    print("=" * 60)
    
    # Prompt the user for the run_id
    target_run_id = input("Enter the run_id to analyze (e.g., run_20260527): ").strip()
    
    if not target_run_id:
        print("Error: A run_id must be provided. Exiting.")
        sys.exit(1)
        
    # Connect to MongoDB
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    coll = db[TARGET_COLLECTION]
    
    print(f"Fetching data from '{TARGET_COLLECTION}' for run_id: '{target_run_id}'...")
    cursor = coll.find({"run_id": target_run_id})
    data = list(cursor)
    
    if not data:
        print(f"No data found for run_id '{target_run_id}'. Make sure r05 ran successfully.")
        sys.exit(0)
        
    # Load into Pandas DataFrame
    df = pd.DataFrame(data)
    
    # Drop the MongoDB '_id' object for cleaner Excel export
    if '_id' in df.columns:
        df = df.drop(columns=['_id'])

    print(f"Loaded {len(df)} records. Calculating statistics...\n")

    # ==========================================
    # 1. Summary Statistics
    # ==========================================
    summary_data = {
        "Metric": ["Total Aspect Records", "Unique Documents (doc_id)", "Unique Posts (post_id)", "Unique Aspects"],
        "Value": [
            len(df),
            df['doc_id'].nunique(),
            df['post_id'].nunique(),
            df['aspect'].nunique()
        ]
    }
    summary_stats = pd.DataFrame(summary_data)
    
    print("-" * 40)
    print("1. SUMMARY STATISTICS")
    print("-" * 40)
    print(summary_stats.to_string(index=False))
    print("\n")

    # ==========================================
    # 2. Aspect Statistics
    # ==========================================
    aspect_stats = df.groupby('aspect').agg(
        mention_count=('aspect', 'count'),
        avg_sentiment=('sentiment_score', 'mean')
    ).reset_index().sort_values(by='mention_count', ascending=False)
    
    # Round sentiment to 2 decimal places for readability
    aspect_stats['avg_sentiment'] = aspect_stats['avg_sentiment'].round(2)

    print("-" * 40)
    print("2. ASPECT STATISTICS (Top 10)")
    print("-" * 40)
    print(aspect_stats.head(10).to_string(index=False))
    print("\n")

    # ==========================================
    # 3. Location Statistics (Handling nulls)
    # ==========================================
    location_stats = df.groupby(['country', 'city'], dropna=False).agg(
        mention_count=('aspect', 'count'),
        avg_sentiment=('sentiment_score', 'mean')
    ).reset_index().sort_values(by='mention_count', ascending=False)
    
    location_stats['avg_sentiment'] = location_stats['avg_sentiment'].round(2)

    print("-" * 40)
    print("3. LOCATION STATISTICS (Top 10)")
    print("-" * 40)
    print(location_stats.head(10).to_string(index=False))
    print("\n")

    # ==========================================
    # 4. Source Type Statistics (Posts vs Comments)
    # ==========================================
    source_stats = df.groupby('type').agg(
        record_count=('type', 'count')
    ).reset_index()

    print("-" * 40)
    print("4. SOURCE TYPE STATISTICS")
    print("-" * 40)
    print(source_stats.to_string(index=False))
    print("\n")

    # ==========================================
    # Export to Excel
    # ==========================================
    output_file = f"execution_stats_{target_run_id}.xlsx"
    print(f"Exporting full data and statistics to {output_file}...")
    
    # Write to different sheets in the same workbook
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        summary_stats.to_excel(writer, sheet_name='Summary', index=False)
        aspect_stats.to_excel(writer, sheet_name='By Aspect', index=False)
        location_stats.to_excel(writer, sheet_name='By Location', index=False)
        source_stats.to_excel(writer, sheet_name='By Source Type', index=False)
        df.to_excel(writer, sheet_name='Raw Data', index=False)
        
    print("=" * 60)
    print(f"SUCCESS: Analysis saved locally as '{output_file}'")
    print("=" * 60)

if __name__ == "__main__":
    main()