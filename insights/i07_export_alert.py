import os
import json
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
COLLECTION_NAME = "news_alert"

def export_alerts():
    if not MONGO_URI:
        print("Error: MONGO_URI is missing from your .env file.")
        return

    try:
        # Connect to MongoDB
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]

        print(f"Fetching documents from the '{COLLECTION_NAME}' collection...")
        
        # Fetch all alerts, sorting them by 'processed_at' in descending order (-1)
        # so your most recent alerts appear at the top of the JSON file
        alerts = list(collection.find({}).sort("processed_at", -1))

        if not alerts:
            print(f"No documents found in the '{COLLECTION_NAME}' collection.")
            return

        # Save the results to a local JSON file
        # default=str cleanly handles MongoDB ObjectIds and Python datetimes
        output_file = "news_alert_export.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(alerts, f, indent=4, ensure_ascii=False, default=str)

        print(f"✅ Successfully exported {len(alerts)} alerts to '{output_file}'.")

    except Exception as e:
        print(f"❌ An error occurred connecting to MongoDB: {e}")
    finally:
        if 'client' in locals():
            client.close()

if __name__ == "__main__":
    export_alerts()