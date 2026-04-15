"""
export_hitl_samples.py — Export balanced HITL samples for News + Reddit.

Creates TWO files:
  - outputs/news_hitl_sample.csv
  - outputs/reddit_hitl_sample.csv

Each file contains:
  - 25 relevant (predicted_label = 1)
  - 25 dropped (predicted_label = 0)

Also includes:
  - human_label column (empty, for manual annotation)

Usage:
  python preprocess/export_hitl_samples.py
  python preprocess/export_hitl_samples.py --run-id run_13042026
"""

import os
import csv
import random
import argparse
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

RAW_COLLECTION = "raw_documents_historical"
PROCESSED_COLLECTION = "processed_documents"
OUTPUT_DIR = "outputs"


def sample_docs(docs, n):
    if len(docs) <= n:
        return docs
    return random.sample(docs, n)


def get_latest_run_id(db):
    latest = db[RAW_COLLECTION].find_one(sort=[("ingestion_time", -1)])
    if not latest:
        raise ValueError("No data found in raw_documents_historical.")
    return latest.get("run_id")


def build_rows(docs, label):
    rows = []
    for doc in docs:
        rows.append({
            "doc_id": doc.get("doc_id"),
            "source": doc.get("source"),
            "city": doc.get("city"),
            "published_at": doc.get("published_at"),
            "title": doc.get("title"),
            "description": doc.get("description"),
            "text": doc.get("text"),
            "url": doc.get("url"),
            "predicted_label": label,   # 1 = relevant, 0 = dropped
            "human_label": "",          # for YOU to fill
            "review_notes": ""
        })
    return rows


def run(target_run_id=None, limit=25):
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not target_run_id:
        target_run_id = get_latest_run_id(db)

    print(f"Using run_id: {target_run_id}")

    for source in ["news", "reddit"]:

        print(f"\nProcessing source: {source}")

        raw_docs = list(db[RAW_COLLECTION].find({
            "source": source
        }))

        processed_docs = list(db[PROCESSED_COLLECTION].find({
            "source": source
        }))

        processed_ids = {
            doc.get("doc_id")
            for doc in processed_docs
            if doc.get("doc_id")
        }

        dropped_docs = [
            doc for doc in raw_docs
            if doc.get("doc_id") not in processed_ids
        ]

        print(f"Total relevant: {len(processed_docs)}")
        print(f"Total dropped: {len(dropped_docs)}")

        relevant_sample = sample_docs(processed_docs, limit)
        dropped_sample = sample_docs(dropped_docs, limit)

        rows = []
        rows += build_rows(relevant_sample, label=1)
        rows += build_rows(dropped_sample, label=0)

        random.shuffle(rows)

        output_path = os.path.join(OUTPUT_DIR, f"{source}_hitl_sample.csv")

        fieldnames = [
            "doc_id",
            "source",
            "city",
            "published_at",
            "title",
            "description",
            "text",
            "url",
            "predicted_label",
            "human_label",
            "review_notes"
        ]

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        print(f"Saved: {output_path} ({len(rows)} rows)")

    client.close()
    print("\n✅ Done — ready for HITL labeling!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    run(target_run_id=args.run_id, limit=args.limit)