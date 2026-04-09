import os

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
    for field in ["created_at", "timestamp", "fetched_at", "ingested_at", "date_fetched"]:
        if field in doc and doc[field]:
            try:
                return pd.to_datetime(doc[field], errors="coerce")
            except Exception:
                pass

    try:
        return pd.to_datetime(doc["_id"].generation_time)
    except Exception:
        return pd.NaT


def get_published_datetime(doc):
    """
    Try to read the article's own publishing date from common field names.
    """
    for field in ["published_at", "publishedAt", "publication_date", "published_date", "date"]:
        if field in doc and doc[field]:
            try:
                return pd.to_datetime(doc[field], errors="coerce")
            except Exception:
                pass

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
                flat["published_at_parsed"] = str(get_published_datetime(doc))
            else:
                flat[k] = str(v)[:300] if v is not None else ""
        cleaned.append(flat)

    return pd.DataFrame(cleaned)


def latest_article_table(db, collection_name, limit=20):
    col = db[collection_name]
    docs = list(col.find().sort("_id", -1).limit(limit))

    rows = []
    for doc in docs:
        rows.append({
            "title": str(doc.get("title", ""))[:200],
            "source": str(doc.get("source", ""))[:100],
            "city": str(doc.get("city", ""))[:100],   # NEW
            "published_at": str(get_published_datetime(doc)),
            "added_at": str(get_doc_added_datetime(doc)),
            "sentiment_score": doc.get("sentiment_score", None),  # NEW
            "url": str(doc.get("url", ""))[:250],
            "run_id": str(doc.get("run_id", ""))[:100]
        })

    return pd.DataFrame(rows)


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


def docs_by_run_id(db, collection_name="raw_documents"):
    col = db[collection_name]
    docs = list(col.find({}, {"run_id": 1}))

    run_ids = []
    for doc in docs:
        run_id = doc.get("run_id")
        if run_id:
            run_ids.append(str(run_id))

    if not run_ids:
        return pd.DataFrame(columns=["run_id", "count"])

    df = pd.DataFrame({"run_id": run_ids})
    result = df.groupby("run_id").size().reset_index(name="count")
    result = result.sort_values("run_id")
    return result


def docs_by_fetch_date(db, collection_name="raw_documents"):
    col = db[collection_name]
    docs = list(col.find())

    dates = []
    for doc in docs:
        dt = get_doc_added_datetime(doc)
        if pd.notna(dt):
            dates.append(pd.to_datetime(dt).date())

    if not dates:
        return pd.DataFrame(columns=["fetch_date", "count"])

    df = pd.DataFrame({"fetch_date": dates})
    result = df.groupby("fetch_date").size().reset_index(name="count")
    result = result.sort_values("fetch_date")
    return result


def docs_by_published_date(db, collection_name="raw_documents"):
    col = db[collection_name]
    docs = list(col.find())

    dates = []
    for doc in docs:
        dt = get_published_datetime(doc)
        if pd.notna(dt):
            dates.append(pd.to_datetime(dt).date())

    if not dates:
        return pd.DataFrame(columns=["published_date", "count"])

    df = pd.DataFrame({"published_date": dates})
    result = df.groupby("published_date").size().reset_index(name="count")
    result = result.sort_values("published_date")
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
# Chart 2: documents by run_id
# -----------------------------
st.subheader("Documents by Run ID")
run_df = docs_by_run_id(db, "raw_documents")

if run_df.empty:
    st.info("No run_id field found in raw_documents.")
else:
    st.bar_chart(run_df.set_index("run_id")["count"])
    st.dataframe(run_df, use_container_width=True)


# -----------------------------
# Chart 3: raw_documents by fetch date and published date
# -----------------------------
st.subheader("Articles in raw_documents by Date")

fetch_df = docs_by_fetch_date(db, "raw_documents")
published_df = docs_by_published_date(db, "raw_documents")
historical_published_df = docs_by_published_date(db, "raw_documents_historical")
processed_published_df = docs_by_published_date(db, "processed_documents")

left_dates, right_dates = st.columns(2)

with left_dates:
    st.markdown("### Articles by Fetch Date")
    if fetch_df.empty:
        st.info("No fetch date data found in raw_documents.")
    else:
        st.line_chart(fetch_df.set_index("fetch_date")["count"])
        st.dataframe(fetch_df, use_container_width=True)

with right_dates:
    st.markdown("### Articles by Published Date")
    if published_df.empty:
        st.info("No published date field found in raw_documents.")
    else:
        st.line_chart(published_df.set_index("published_date")["count"])
        st.dataframe(published_df, use_container_width=True)


# -----------------------------
# Chart 4: raw_documents_historical by published date
# -----------------------------
st.subheader("Historical Articles by Published Date")

if historical_published_df.empty:
    st.info("No published date field found in raw_documents_historical.")
else:
    st.line_chart(historical_published_df.set_index("published_date")["count"])


# -----------------------------
# Chart 5: processed_documents by published date
# -----------------------------
st.subheader("Processed Articles by Published Date")

if processed_published_df.empty:
    st.info("No published date field found in processed_documents.")
else:
    st.line_chart(processed_published_df.set_index("published_date")["count"])

st.markdown("### 20 Newest Articles in `processed_documents`")
processed_latest_df = latest_article_table(db, "processed_documents", limit=20)

if processed_latest_df.empty:
    st.info("No records found in processed_documents.")
else:
    st.dataframe(processed_latest_df, use_container_width=True)


# -----------------------------
# Chart 6: all collections by day
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