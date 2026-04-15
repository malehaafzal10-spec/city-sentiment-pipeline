import os
import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

OUTPUT_DIR = "HITL_vader"
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "random_50_vader_scored_articles.csv")

os.makedirs(OUTPUT_DIR, exist_ok=True)

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

scored_collection = db["scored_documents"]
processed_collection = db["processed_documents"]

sample_docs = list(scored_collection.aggregate([
    {"$match": {"title": {"$ne": None}}},
    {"$sample": {"size": 50}}
]))

rows = []

for doc in sample_docs:
    doc_id = doc.get("doc_id")
    processed_doc = processed_collection.find_one({"doc_id": doc_id}) or {}

    rows.append({
        "doc_id": doc.get("doc_id"),
        "city": doc.get("city"),
        "source": doc.get("source"),
        "title": doc.get("title"),
        "url": processed_doc.get("url"),
        "vader_label": doc.get("sentiment_label"),
        "vader_score": doc.get("sentiment_score"),
        "scored_at": doc.get("scored_at"),
    })

df = pd.DataFrame(rows)
df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

print(f"Saved {len(df)} rows to {OUTPUT_CSV}")
print(df[["title", "url", "vader_label", "vader_score"]].head())

client.close()