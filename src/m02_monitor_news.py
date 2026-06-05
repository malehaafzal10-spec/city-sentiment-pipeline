import os
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

# List all the collections you want to monitor here
COLLECTIONS_TO_MONITOR = [
    "raw_documents_historical",
    "news_alert"
]

def monitor_collections():
    if not MONGO_URI:
        print("Error: MONGO_URI is missing from environment variables.")
        return

    try:
        # Initialize MongoDB Client
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]

        for collection_name in COLLECTIONS_TO_MONITOR:
            collection = db[collection_name]

            # Aggregation Pipeline: Group by run_id, sum them, and sort newest first
            pipeline = [
                {"$group": {"_id": "$run_id", "count": {"$sum": 1}}},
                {"$sort": {"_id": -1}} 
            ]

            results = list(collection.aggregate(pipeline))

            print(f"\n" + "="*50)
            print(f"📊 COLLECTION: {collection_name}")
            print("="*50)

            if not results:
                print(f"  No documents found in collection.\n")
                continue

            print(f"{'Run ID':<25} | {'Document Count'}")
            print("-" * 45)

            total_docs = 0
            for row in results:
                run_id = row["_id"] if row["_id"] else "UNKNOWN/NULL"
                count = row["count"]
                total_docs += count
                
                print(f"{run_id:<25} | {count}")

            print("-" * 45)
            print(f"{'TOTAL DOCUMENTS':<25} | {total_docs}\n")

    except Exception as e:
        print(f"An error occurred while connecting to MongoDB: {e}")
    finally:
        if 'client' in locals():
            client.close()

if __name__ == "__main__":
    monitor_collections()