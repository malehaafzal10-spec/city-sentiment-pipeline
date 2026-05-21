"""
analyze_reddit_sources_flat.py — MLOps Data Insight Generator
Analyzes the 'processed_documents' collection to track the volume and 
true URL sources of Reddit ingestion runs over time. 
Exports analytical plots to the 'insights' directory.
"""

import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pymongo import MongoClient
from dotenv import load_dotenv
from urllib.parse import urlparse

# 1. Configuration & Initialization
load_dotenv()
print("--- 🚀 INITIALIZING REDDIT SOURCE ANALYSIS ---")

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
COLLECTION_NAME = "processed_documents" # Target collection

if not MONGO_URI:
    print("❌ Error: MONGO_URI not found in environment (.env file).")
    sys.exit(1)

# Ensure the insights directory exists
INSIGHTS_DIR = "insights"
os.makedirs(INSIGHTS_DIR, exist_ok=True)
print(f"📁 Plots will be saved to '{INSIGHTS_DIR}/'")

# 2. Connect to Database & Fetch Data
print(f"🔌 Connecting to MongoDB: {DB_NAME}.{COLLECTION_NAME}...")
client = MongoClient(MONGO_URI)
collection = client[DB_NAME][COLLECTION_NAME]

# Fetch only the documents where the ingestion pipeline assigned source="reddit"[cite: 4]
query = {"source": "reddit"}
cursor = collection.find(query, {"run_id": 1, "url": 1, "published_at": 1, "processed_time": 1})
data = list(cursor)

if not data:
    print("⚠️ No Reddit data found in the collection.")
    client.close()
    sys.exit(0)

print(f"✅ Fetched {len(data)} documents. Processing features...\n")

# 3. Data Engineering
df = pd.DataFrame(data)

# Parse Dates (Fallback to processed_time if published_at is missing)
df['parsed_date'] = pd.to_datetime(df['published_at'], errors='coerce', utc=True)
df['parsed_date'] = df['parsed_date'].fillna(pd.to_datetime(df['processed_time'], errors='coerce', utc=True))
df['pub_date_only'] = df['parsed_date'].dt.date

# Parse URLs to determine if they actually point to Reddit
df['domain'] = df['url'].astype(str).apply(lambda x: urlparse(x).netloc.lower().replace('www.', ''))
df['is_actual_reddit'] = df['domain'].str.contains('reddit.com', na=False)

# ---------------------------------------------------------
# PLOT 1: Amount of Documents per Run ID
# ---------------------------------------------------------
print("📊 Generating Plot 1: Documents per Run ID...")
run_counts = df.groupby('run_id').size()
# Treat 0 as NaN to improve clarity of automated plots
run_counts = run_counts.replace(0, np.nan).dropna()

plt.figure(figsize=(10, 6))
run_counts.plot(kind='bar', color='#1f77b4', edgecolor='black')
plt.title('Total Documents Processed per Run ID', fontsize=14, fontweight='bold')
plt.xlabel('Run ID', fontsize=12)
plt.ylabel('Document Count', fontsize=12)
plt.xticks(rotation=45, ha='right')
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
plt.savefig(os.path.join(INSIGHTS_DIR, '01_docs_per_run_id.png'), dpi=300)
plt.close()

# ---------------------------------------------------------
# PLOT 2: Percentage of Actual Reddit URLs per Run ID
# ---------------------------------------------------------
print("📊 Generating Plot 2: % Actual Reddit URLs per Run ID...")
# Calculate percentage (mean of boolean * 100)
run_pct = df.groupby('run_id')['is_actual_reddit'].mean() * 100
run_pct = run_pct.replace(0, np.nan).dropna()

plt.figure(figsize=(10, 6))
run_pct.plot(kind='bar', color='#ff7f0e', edgecolor='black')
plt.title('Percentage of Actual Reddit URLs per Run ID', fontsize=14, fontweight='bold')
plt.xlabel('Run ID', fontsize=12)
plt.ylabel('Percentage (%)', fontsize=12)
plt.ylim(0, 105) # Keep scale to 100%
plt.xticks(rotation=45, ha='right')
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
plt.savefig(os.path.join(INSIGHTS_DIR, '02_reddit_url_pct_per_run_id.png'), dpi=300)
plt.close()

# ---------------------------------------------------------
# PLOT 3: Amount of Documents per Publication Date
# ---------------------------------------------------------
print("📊 Generating Plot 3: Documents per Publication Date...")
date_counts = df.groupby('pub_date_only').size().sort_index()
date_counts = date_counts.replace(0, np.nan).dropna()

plt.figure(figsize=(12, 6))
# Using a line plot with markers for time-series data
plt.plot(date_counts.index, date_counts.values, marker='o', linestyle='-', color='#2ca02c', linewidth=2)
plt.title('Total Documents Processed per Publication Date', fontsize=14, fontweight='bold')
plt.xlabel('Publication Date', fontsize=12)
plt.ylabel('Document Count', fontsize=12)
plt.xticks(rotation=45)
plt.grid(True, linestyle='--', alpha=0.7)
plt.tight_layout()
plt.savefig(os.path.join(INSIGHTS_DIR, '03_docs_per_pub_date.png'), dpi=300)
plt.close()

# ---------------------------------------------------------
# PLOT 4: Percentage of Actual Reddit URLs per Pub Date
# ---------------------------------------------------------
print("📊 Generating Plot 4: % Actual Reddit URLs per Publication Date...")
date_pct = df.groupby('pub_date_only')['is_actual_reddit'].mean().sort_index() * 100
date_pct = date_pct.replace(0, np.nan).dropna()

plt.figure(figsize=(12, 6))
plt.plot(date_pct.index, date_pct.values, marker='s', linestyle='-', color='#d62728', linewidth=2)
plt.title('Percentage of Actual Reddit URLs per Publication Date', fontsize=14, fontweight='bold')
plt.xlabel('Publication Date', fontsize=12)
plt.ylabel('Percentage (%)', fontsize=12)
plt.ylim(0, 105)
plt.xticks(rotation=45)
plt.grid(True, linestyle='--', alpha=0.7)
plt.tight_layout()
plt.savefig(os.path.join(INSIGHTS_DIR, '04_reddit_url_pct_per_pub_date.png'), dpi=300)
plt.close()

# 4. Clean up
client.close()
print("\n--- ✅ ANALYSIS COMPLETE. Check the 'insights' folder. ---")