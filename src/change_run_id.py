import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
client = MongoClient(os.getenv("MONGO_URI"))
db = client[os.getenv("MONGO_DB_NAME", "travel_pipeline_db")]

#collections:
# - reddit_comments_final
# - reddit_relevant
# - reddit_comments_relevant (R04)
# - reddit_aggregated

# Update the run_id in the source collection
result = db["reddit_comments_relevant"].update_many(
    {"run_id": "comments_run_20260603_100510"},
    {"$set": {"run_id": "run_20260526_local"}}
)

print(f"Successfully modified {result.modified_count} comments.")