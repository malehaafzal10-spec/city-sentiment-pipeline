"""
inspect_reddit_silver_flat.py — Data Quality Audit (with text wrapping)
A sequential (flat) script that checks the 'processed_documents' collection, 
summarizes the data, and exports wrapped, readable text of each sample.
"""

import os
import sys
import pandas as pd
import textwrap
from pymongo import MongoClient
from dotenv import load_dotenv
from tabulate import tabulate

# 1. Load environment variables
load_dotenv()

print("--- 🚀 INITIALIZING REDDIT SILVER LAYER AUDIT ---")

# 2. Configuration & Variables
SAMPLE_LIMIT = 25
TEXT_WRAP_WIDTH = 80 # Width in characters for the exported .txt files
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
COLLECTION_NAME = "processed_documents"

if not MONGO_URI:
    print("❌ Error: MONGO_URI not found in environment (.env file).")
    sys.exit(1)

# 3. Connect to Database
print(f"🔌 Connecting to MongoDB: {DB_NAME}.{COLLECTION_NAME}...")
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

# 4. Query for Reddit Data specifically
query = {"source": "reddit"}
total_reddit = collection.count_documents(query)

print(f"\n--- 📊 REDDIT SILVER LAYER SUMMARY ---")
print(f"Total Reddit docs in Silver Layer: {total_reddit}")

if total_reddit == 0:
    print("⚠️ No Reddit data found. Ensure 01b_ingest_reddit.py and s02 have run.")
    client.close()
    sys.exit(0)

# 5. Fetch the latest samples
cursor = collection.find(query).sort("processed_time", -1).limit(SAMPLE_LIMIT)
samples = list(cursor)

# 6. MLOps Data Quality Guard (Inline Validation)
print("\n--- 🛡️ SCHEMA VALIDATION (Latest Samples) ---")
required_fields = ["text", "city", "doc_id", "url", "run_id"]
failed_docs = 0

for doc in samples:
    issues = []
    for field in required_fields:
        if not doc.get(field):
            issues.append(f"Missing '{field}'")
    
    text_length = len(doc.get("text", ""))
    if text_length < 40:
        issues.append(f"Text too short ({text_length} chars)")
        
    if issues:
        print(f"⚠️ Document [{doc.get('doc_id', 'Unknown')}] failed validation: {', '.join(issues)}")
        failed_docs += 1

if failed_docs == 0:
    print("✅ All recent samples passed data quality checks!")

# 7. Format Data for Analysis & Export Wrapped Text Files
df = pd.DataFrame(samples)

# --- EXPORT TEXT TO FOLDER WITH WORD WRAPPING ---
output_dir = "reddit_text"
os.makedirs(output_dir, exist_ok=True)
print(f"\n--- 📁 EXPORTING FORMATTED TEXT FILES TO '{output_dir}/' ---")

saved_count = 0
for index, row in df.iterrows():
    doc_id = row.get('doc_id', str(row.get('_id', f'unknown_{index}')))
    text_content = row.get('text', '')
    
    if text_content:
        file_path = os.path.join(output_dir, f"{doc_id}.txt")
        try:
            # Wrap the text so it doesn't print as one continuous line
            wrapped_text = textwrap.fill(text_content, width=TEXT_WRAP_WIDTH)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(wrapped_text)
            saved_count += 1
        except Exception as e:
            print(f"⚠️ Failed to save {doc_id}.txt: {e}")

print(f"✅ Saved {saved_count} text files. (Wrapped at {TEXT_WRAP_WIDTH} characters)")
# ------------------------------------------------

# Create a truncated preview for the terminal and calculate text lengths
if 'text' in df.columns:
    df['text_preview'] = df['text'].astype(str).str[:100] + "..." 
    df['char_count'] = df['text'].apply(len)
    avg_len = df['char_count'].mean()
else:
    df['text_preview'] = "N/A"
    avg_len = 0

# Select only the columns we want to print
display_cols = [c for c in ["doc_id", "city", "text_preview", "run_id"] if c in df.columns]

# 8. Display Results
print("\n--- 🔍 LATEST PROCESSED SAMPLES ---")
print(tabulate(df[display_cols].head(), headers='keys', tablefmt='psql'))

print(f"\n--- ✨ QUALITY METRICS ---")
print(f"Average Cleaned Text Length: {avg_len:.2f} characters")

# 9. Clean up connection
client.close()
print("\n--- ✅ AUDIT COMPLETE ---")