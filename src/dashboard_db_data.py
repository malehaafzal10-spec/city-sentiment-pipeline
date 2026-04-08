import os
from collections import defaultdict

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

st.set_page_config(
    page_title="MongoDB Data Monitor",
    layout="wide"
)

st.title("Daily Data Collection Dashboard")
st.caption("Live view of data entering MongoDB collections")

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
# Helpers
# -----------------------------
def get_doc_added_datetime(doc):
    """
    Prefer explicit created_at / timestamp fields if they exist,
    otherwise fall back to MongoDB ObjectId generation time.
    """
    for field in ["created_at", "timestamp", "published_at", "date"]:
        if field in doc and doc[field]:
            try:
                return pd.to_datetime(doc[field], errors="coerce")
            except Exception:
                pass

    try:
        return pd.to_datetime(doc["_id"].generation_time)
    except Exception:
        return pd.NaT


def collection_summary(db):
    rows = []

    for collection_name in db.list_collection_names():
        col = db[collection_name]
        count = col.count_documents({})

        first_doc = col.find_one(sort=[("_id", 1)])
        last_doc = col.find_one(sort=[("_id", -1)])

        first_added = None
        last_added = None

        if first_doc:
            dt = get_doc_added_datetime(first_doc)
            if pd.notna(dt):
                first_added = dt

        if last_doc:
            dt = get_doc_added_datetime(last_doc)
            if pd.notna(dt):
                last_added = dt

        rows.append({
            "collection": collection_name,
            "document_count": count,
            "first_added": first_added,
            "last_added": last_added
        })

    return pd.DataFrame(rows)


def docs_per_day(db, collection_name):
    col = db[collection_name]
    docs = list(col.find())

    if not docs:
        return pd.DataFrame(columns=["date", "count"])

    dates = []
    for doc in docs:
        dt = get_doc_added_datetime(doc)
        if pd.notna(dt):
            dates.append(dt.date())

    if not dates:
        return pd.DataFrame(columns=["date", "count"])

    df = pd.DataFrame({"date": dates})
    daily = df.groupby("date").size().reset_index(name="count")
    daily = daily.sort_values("date")
    return daily


def all_collections_daily(db):
    frames = []

    for collection_name in db.list_collection_names():
        daily = docs_per_day(db, collection_name)
        if not daily.empty:
            daily["collection"] = collection_name
            frames.append(daily)

    if not frames:
        return pd.DataFrame(columns=["date", "count", "collection"])

    return pd.concat(frames, ignore_index=True)


def latest_docs(db, collection_name, limit=10):
    col = db[collection_name]
    docs = list(col.find().sort("_id", -1).limit(limit))

    cleaned = []
    for doc in docs:
        flat = {}
        for k, v in doc.items():
            if k == "_id":
                flat["_id"] = str(v)
                flat["added_at"] = str(get_doc_added_datetime(doc))
            else:
                flat[k] = str(v)[:300] if v is not None else ""
        cleaned.append(flat)

    return pd.DataFrame(cleaned)


def source_breakdown(db, collection_name):
    col = db[collection_name]
    docs = list(col.find({}, {"source": 1}))

    sources = []
    for doc in docs:
        source = doc.get("source")
        if source:
            sources.append(source)

    if not sources:
        return pd.DataFrame(columns=["source", "count"])

    df = pd.DataFrame({"source": sources})
    result = df.groupby("source").size().reset_index(name="count")
    result = result.sort_values("count", ascending=False)
    return result


# -----------------------------
# Summary section
# -----------------------------
summary_df = collection_summary(db)

st.subheader("Collections Overview")

if summary_df.empty:
    st.warning("No collections found in the database.")
    st.stop()

col1, col2 = st.columns(2)
with col1:
    st.metric("Number of Collections", len(summary_df))
with col2:
    st.metric("Total Documents", int(summary_df["document_count"].sum()))

st.dataframe(summary_df, use_container_width=True)

# -----------------------------
# Chart 1: total docs by collection
# -----------------------------
st.subheader("Documents by Collection")
chart_df = summary_df[["collection", "document_count"]].set_index("collection")
st.bar_chart(chart_df)

# -----------------------------
# Chart 2: all collections by day
# -----------------------------
st.subheader("Daily Documents Added Across All Collections")
daily_all_df = all_collections_daily(db)

if daily_all_df.empty:
    st.info("No timestamped records found.")
else:
    pivot_df = daily_all_df.pivot(index="date", columns="collection", values="count").fillna(0)
    st.line_chart(pivot_df)

# -----------------------------
# Collection explorer
# -----------------------------
st.subheader("Collection Explorer")

collection_names = sorted(db.list_collection_names())
selected_collection = st.selectbox("Choose a collection", collection_names)

daily_df = docs_per_day(db, selected_collection)

left, right = st.columns(2)

with left:
    st.markdown(f"### Daily Additions: `{selected_collection}`")
    if daily_df.empty:
        st.info("No date information found for this collection.")
    else:
        st.line_chart(daily_df.set_index("date")["count"])

with right:
    st.markdown(f"### Source Breakdown: `{selected_collection}`")
    source_df = source_breakdown(db, selected_collection)
    if source_df.empty:
        st.info("No `source` field found in this collection.")
    else:
        st.bar_chart(source_df.set_index("source")["count"])

# -----------------------------
# Latest records
# -----------------------------
st.subheader(f"Latest Records in `{selected_collection}`")
limit = st.slider("How many latest records to show", min_value=5, max_value=50, value=10, step=5)
latest_df = latest_docs(db, selected_collection, limit=limit)

if latest_df.empty:
    st.info("No records found.")
else:
    st.dataframe(latest_df, use_container_width=True)