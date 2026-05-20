"""
inspect_reddit_urls_flat.py
A flat script to analyze documents labeled as source='reddit'.
It groups the data by month and checks how many URLs actually point to 
reddit.com versus external domains.
"""

import os
import sys
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv
from urllib.parse import urlparse
from tabulate import tabulate

# 1. Initialization and Config
load_dotenv()
print("--- 🚀 INITIALIZING REDDIT URL SOURCE ANALYSIS ---")

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
COLLECTION_NAME = "processed_documents"

if not MONGO_URI:
    print("❌ Error: MONGO_URI not found in environment.")
    sys.exit(1)

# 2. Database Connection & Query
print(f"🔌 Connecting to MongoDB: {DB_NAME}.{COLLECTION_NAME}...")
client = MongoClient(MONGO_URI)
collection = client[DB_NAME][COLLECTION_NAME]

# Fetch only documents where the pipeline assigned source="reddit"
query = {"source": "reddit"}
cursor = collection.find(query, {"doc_id": 1, "url": 1, "published_at": 1, "processed_time": 1, "title": 1})
data = list(cursor)

if not data:
    print("⚠️ No Reddit data found in the collection.")
    client.close()
    sys.exit(0)

print(f"✅ Fetched {len(data)} documents labeled as 'reddit'. Analyzing URLs...\n")

# 3. Data Processing with Pandas
df = pd.DataFrame(data)

# Handle mixed date formats (strings vs datetime objects)
# Coerce errors to NaT (Not a Time), and use UTC to align everything
df['parsed_date'] = pd.to_datetime(df['published_at'], errors='coerce', utc=True)

# If 'published_at' failed to parse, fall back to 'processed_time'
df['parsed_date'] = df['parsed_date'].fillna(pd.to_datetime(df['processed_time'], errors='coerce', utc=True))

# Create a 'Period' column (Year-Month) for grouping
df['period'] = df['parsed_date'].dt.strftime('%Y-%m').fillna("Unknown")

# Parse the URLs to extract the domain (netloc)
# Use a lambda inside apply to keep it flat (no def needed)
df['domain'] = df['url'].astype(str).apply(lambda x: urlparse(x).netloc.lower())
df['domain'] = df['domain'].str.replace('www.', '') # Clean up for easier reading

# Determine if it's an actual reddit URL
df['is_reddit_url'] = df['domain'].str.contains('reddit.com', na=False)

# 4. Aggregation: Count by Period and URL Match
# Pivot the data to see True/False counts per month
summary = df.groupby(['period', 'is_reddit_url']).size().unstack(fill_value=0)

# Rename columns for clarity
if True in summary.columns and False in summary.columns:
    summary = summary.rename(columns={True: "Reddit URLs", False: "External URLs"})
elif True in summary.columns:
    summary = summary.rename(columns={True: "Reddit URLs"})
    summary["External URLs"] = 0
elif False in summary.columns:
    summary = summary.rename(columns={False: "External URLs"})
    summary["Reddit URLs"] = 0

# Add a total column and sort by period
summary['Total'] = summary.sum(axis=1)
summary = summary.sort_index(ascending=False)

# 5. Output Results
print("--- 📅 URL BREAKDOWN BY PERIOD ---")
print(tabulate(summary, headers='keys', tablefmt='psql'))

# 6. Show examples of external domains to see where Reddit is linking
print("\n--- 🔗 TOP EXTERNAL DOMAINS FOUND IN REDDIT POSTS ---")
external_df = df[df['is_reddit_url'] == False]

if not external_df.empty:
    top_domains = external_df['domain'].value_counts().head(10).reset_index()
    top_domains.columns = ['Domain', 'Count']
    print(tabulate(top_domains, headers='keys', tablefmt='psql', showindex=False))
    
    print("\n--- 📝 EXAMPLES OF EXTERNAL URLS ---")
    examples = external_df[['domain', 'title', 'url']].head(3)
    # Truncate strings for terminal readability
    examples['title'] = examples['title'].str[:50] + "..."
    examples['url'] = examples['url'].str[:60] + "..."
    print(tabulate(examples, headers='keys', tablefmt='grid', showindex=False))
else:
    print("No external domains found! All URLs point to Reddit.")

# 7. Cleanup
client.close()
print("\n--- ✅ SCRIPT COMPLETE ---")