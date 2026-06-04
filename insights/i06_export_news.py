import os
import json
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
COLLECTION_NAME = "raw_documents_historical"

def export_random_sample(sample_size=10):
    if not MONGO_URI:
        print("Error: MONGO_URI is missing from your .env file.")
        return

    try:
        # Connect to MongoDB
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]

        print(f"Fetching a random sample of {sample_size} documents from '{COLLECTION_NAME}'...")
        
        # Use $sample to get random documents
        pipeline = [{"$sample": {"size": sample_size}}]
        sample_docs = list(collection.aggregate(pipeline))

        if not sample_docs:
            print(f"No documents found in the '{COLLECTION_NAME}' collection.")
            return

        # Save the results to a local JSON file
        # default=str handles datetimes and ObjectIds seamlessly
        output_file = "sample_raw_documents.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(sample_docs, f, indent=4, ensure_ascii=False, default=str)

        print(f"✅ Successfully exported {len(sample_docs)} documents to '{output_file}'.")

    except Exception as e:
        print(f"❌ An error occurred connecting to MongoDB: {e}")
    finally:
        if 'client' in locals():
            client.close()

if __name__ == "__main__":
    export_random_sample(sample_size=10)