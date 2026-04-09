import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from pymongo import MongoClient
from datetime import datetime

load_dotenv()

st.set_page_config(
    page_title="LLMOps: Tourist Sentiment Monitor",
    layout="wide"
)

st.title("🏙️ Travel Pipeline Monitoring")
st.caption("Tracking data lineage, run executions, and content freshness")

# -----------------------------
# MongoDB connection
# -----------------------------
@st.cache_resource
def get_db():
    mongo_uri = os.getenv("MONGO_URI")
    db_name = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

    if not mongo_uri:
        st.error("MONGO_URI not found in .env")
        st.stop()

    client = MongoClient(mongo_uri)
    return client[db_name]

db = get_db()

# -----------------------------
# Data Retrieval Helpers
# -----------------------------
def get_docs_by_run(db):
    """Aggregates document counts grouped by their pipeline run_id."""
    col = db["raw_documents"]
    pipeline = [
        {"$group": {"_id": "$run_id", "count": {"$sum": 1}}},
        {"$sort": {"_id": -1}}
    ]
    cursor = col.aggregate(pipeline)
    df = pd.DataFrame(list(cursor))
    if not df.empty:
        df.columns = ["run_id", "document_count"]
    return df

def get_article_publication_timeline(db):
    """Extracts the 'published_at' field to show when the news was actually written."""
    col = db["raw_documents"]
    # Fetching only the published_at field to save memory
    docs = list(col.find({}, {"published_at": 1, "_id": 0}))
    
    if not docs:
        return pd.DataFrame()

    dates = []
    for doc in docs:
        p_at = doc.get("published_at")
        if p_at:
            try:
                # NewsAPI format is usually '2023-10-27T14:00:00Z'
                dt = pd.to_datetime(p_at).date()
                dates.append(dt)
            except:
                continue
    
    df = pd.DataFrame({"date": dates})
    daily = df.groupby("date").size().reset_index(name="article_count")
    return daily.sort_values("date")

# -----------------------------
# Summary Metrics
# -----------------------------
st.subheader("System Overview")
raw_col = db["raw_documents"]
art_col = db["pipeline_artifacts"]

m1, m2, m3 = st.columns(3)
m1.metric("Total Raw Articles", raw_col.count_documents({}))
m2.metric("Pipeline Runs", len(raw_col.distinct("run_id")))
m3.metric("Artifact Snapshots", art_col.count_documents({}))

# -----------------------------
# NEW SECTION: Documents by Run ID
# -----------------------------
st.divider()
st.subheader("🚀 Ingestion Lineage (Documents per Run)")
run_df = get_docs_by_run(db)

if not run_df.empty:
    # We use a bar chart to show how much data each run injected
    st.bar_chart(run_df.set_index("run_id"))
    with st.expander("View Run Details"):
        st.table(run_df)
else:
    st.info("No run_id data found. Ensure your ingestion script is tagging documents.")

# -----------------------------
# NEW SECTION: Article Freshness
# -----------------------------
st.divider()
st.subheader("📅 Content Freshness (Publication Dates)")
st.info("This shows when the collected articles were published, helping monitor the 'relevance' of our data pool.")

pub_df = get_article_publication_timeline(db)

if not pub_df.empty:
    st.line_chart(pub_df.set_index("date"))
else:
    st.warning("No 'published_at' timestamps found in raw_documents.")

# -----------------------------
# Latest records (Enhanced for LLMOps)
# -----------------------------
st.divider()
st.subheader("🔍 Raw Data Inspector")
selected_run = st.selectbox("Filter by Run ID", ["All"] + sorted(raw_col.distinct("run_id"), reverse=True))

query = {} if selected_run == "All" else {"run_id": selected_run}
latest_docs = list(raw_col.find(query).sort("_id", -1).limit(10))

if latest_docs:
    # Clean up for display
    display_df = pd.DataFrame(latest_docs).drop(columns=["_id"], errors="ignore")
    st.dataframe(display_df, use_container_width=True)
else:
    st.info("No records match the selection.")