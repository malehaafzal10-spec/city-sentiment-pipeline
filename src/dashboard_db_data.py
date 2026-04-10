import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from pymongo import MongoClient

# --------------------------------------------------
# Config
# --------------------------------------------------
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

st.set_page_config(
    page_title="Travel Data Dashboard",
    page_icon="🌍",
    layout="wide"
)

# --------------------------------------------------
# Styling
# --------------------------------------------------
st.markdown("""
<style>
    .main {
        background: linear-gradient(180deg, #f8fbff 0%, #eef6f7 100%);
    }
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    h1, h2, h3 {
        color: #16324f;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 52px;
        border-radius: 12px;
        padding-left: 18px;
        padding-right: 18px;
        background-color: #f3f7fa;
        color: #16324f;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #d9eef7 !important;
        color: #0d3b66 !important;
    }
    div[data-testid="metric-container"] {
        background: white;
        border: 1px solid #e7eef4;
        padding: 14px 16px;
        border-radius: 16px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    .section-card {
        background: white;
        border-radius: 18px;
        padding: 18px;
        border: 1px solid #e8eef3;
        box-shadow: 0 2px 10px rgba(0,0,0,0.04);
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

st.title("🌍 Travel Data Collection Dashboard")
st.caption("Interactive monitoring for MongoDB collections powering the travel-inspired analytics pipeline")

# --------------------------------------------------
# MongoDB connection
# --------------------------------------------------
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

# --------------------------------------------------
# Helpers
# --------------------------------------------------
def get_doc_added_datetime(doc):
    for field in ["created_at", "timestamp", "fetched_at", "ingested_at", "date_fetched"]:
        if field in doc and doc[field]:
            try:
                return pd.to_datetime(doc[field], errors="coerce", utc=True).tz_localize(None)
            except Exception:
                pass

    try:
        return pd.to_datetime(doc["_id"].generation_time).tz_localize(None)
    except Exception:
        return pd.NaT


def get_published_datetime(doc):
    for field in ["published_at", "publishedAt", "publication_date", "published_date", "date"]:
        if field in doc and doc[field]:
            try:
                return pd.to_datetime(doc[field], errors="coerce", utc=True).tz_localize(None)
            except Exception:
                pass

    return pd.NaT


def normalize_source(value):
    if value is None:
        return "unknown"

    s = str(value).strip().lower()

    if "reddit" in s:
        return "reddit"
    if "news" in s:
        return "news"

    return s


def collection_summary(db):
    rows = []

    for collection_name in db.list_collection_names():
        col = db[collection_name]
        count = col.count_documents({})

        first_doc = col.find_one(sort=[("_id", 1)])
        last_doc = col.find_one(sort=[("_id", -1)])

        first_added = get_doc_added_datetime(first_doc) if first_doc else pd.NaT
        last_added = get_doc_added_datetime(last_doc) if last_doc else pd.NaT

        rows.append({
            "collection": collection_name,
            "document_count": count,
            "first_added": first_added,
            "last_added": last_added
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("document_count", ascending=False)
    return df


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
    daily = df.groupby("date").size().reset_index(name="count").sort_values("date")
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


def source_breakdown(db, collection_name):
    col = db[collection_name]
    docs = list(col.find({}, {"source": 1}))

    sources = []
    for doc in docs:
        src = normalize_source(doc.get("source"))
        if src:
            sources.append(src)

    if not sources:
        return pd.DataFrame(columns=["source", "count"])

    df = pd.DataFrame({"source": sources})
    result = df.groupby("source").size().reset_index(name="count")
    result = result.sort_values("count", ascending=False)
    return result


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


def load_collection_docs(db, collection_name):
    col = db[collection_name]
    docs = list(col.find())

    rows = []
    for doc in docs:
        rows.append({
            "_id": str(doc.get("_id", "")),
            "title": str(doc.get("title", ""))[:200],
            "source": normalize_source(doc.get("source", "")),
            "city": str(doc.get("city", ""))[:100],
            "published_at": get_published_datetime(doc),
            "added_at": get_doc_added_datetime(doc),
            "run_id": str(doc.get("run_id", ""))[:100],
            "url": str(doc.get("url", ""))[:250],
            "sentiment_score": doc.get("sentiment_score", None),
        })

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    if "published_at" in df.columns:
        df["published_date"] = pd.to_datetime(df["published_at"], errors="coerce").dt.date

    if "added_at" in df.columns:
        df["added_date"] = pd.to_datetime(df["added_at"], errors="coerce").dt.date

    return df


@st.cache_data(ttl=300)
def get_collection_dataframe(collection_name):
    return load_collection_docs(db, collection_name)


def filter_by_source(df, source_name):
    if df.empty:
        return df.copy()
    return df[df["source"] == source_name].copy()


def docs_by_published_date_from_df(df):
    if df.empty or "published_date" not in df.columns:
        return pd.DataFrame(columns=["published_date", "count"])

    temp = df.dropna(subset=["published_date"]).copy()
    if temp.empty:
        return pd.DataFrame(columns=["published_date", "count"])

    result = (
        temp.groupby("published_date")
        .size()
        .reset_index(name="count")
        .sort_values("published_date")
    )
    return result


def docs_by_run_id_from_df(df):
    if df.empty or "run_id" not in df.columns:
        return pd.DataFrame(columns=["run_id", "count"])

    temp = df.copy()
    temp["run_id"] = temp["run_id"].fillna("").astype(str).str.strip()
    temp = temp[temp["run_id"] != ""]

    if temp.empty:
        return pd.DataFrame(columns=["run_id", "count"])

    result = (
        temp.groupby("run_id")
        .size()
        .reset_index(name="count")
        .sort_values("run_id")
    )
    return result


def latest_article_table_from_df(df, limit=20):
    if df.empty:
        return pd.DataFrame(columns=[
            "title", "source", "city", "published_at",
            "added_at", "sentiment_score", "url", "run_id"
        ])

    cols = ["title", "source", "city", "published_at", "added_at", "sentiment_score", "url", "run_id"]
    available_cols = [c for c in cols if c in df.columns]

    latest = df.sort_values("added_at", ascending=False).head(limit).copy()
    return latest[available_cols]


def render_timeseries_chart(df, x_col, y_col, title):
    st.markdown(f"### {title}")
    if df.empty:
        st.info("No data available for this view.")
    else:
        chart_df = df.set_index(x_col)[y_col]
        st.line_chart(chart_df, use_container_width=True)


def render_runid_chart(df, title):
    st.markdown(f"### {title}")
    if df.empty:
        st.info("No run_id data available.")
    else:
        st.bar_chart(df.set_index("run_id")["count"], use_container_width=True)
        st.dataframe(df, use_container_width=True, hide_index=True)


def render_latest_table(df, title):
    st.markdown(f"### {title}")
    if df.empty:
        st.info("No records found.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def render_source_section(df, section_title, latest_limit):
    st.markdown(f"## {section_title}")

    metric_col1, metric_col2, metric_col3 = st.columns(3)

    total_docs = len(df)
    total_dates = df["published_date"].nunique() if not df.empty and "published_date" in df.columns else 0
    total_runs = df["run_id"].replace("", pd.NA).dropna().nunique() if not df.empty and "run_id" in df.columns else 0

    with metric_col1:
        st.metric("Documents", total_docs)
    with metric_col2:
        st.metric("Published Dates", total_dates)
    with metric_col3:
        st.metric("Run IDs", total_runs)

    date_df = docs_by_published_date_from_df(df)
    run_df = docs_by_run_id_from_df(df)
    latest_df = latest_article_table_from_df(df, limit=latest_limit)

    left, right = st.columns([1.4, 1])

    with left:
        render_timeseries_chart(date_df, "published_date", "count", f"{section_title} — Articles by Published Date")

    with right:
        render_latest_table(latest_df, f"{section_title} — Latest {latest_limit} Articles")

    render_runid_chart(run_df, f"{section_title} — Documents by Run ID")
    st.divider()


# --------------------------------------------------
# Overview data
# --------------------------------------------------
summary_df = collection_summary(db)

if summary_df.empty:
    st.warning("No collections found in the database.")
    st.stop()

# --------------------------------------------------
# Tabs
# --------------------------------------------------
tab1, tab2, tab3 = st.tabs([
    "🧭 Overview",
    "📰 Raw Historical",
    "✨ Processed Documents"
])

# --------------------------------------------------
# TAB 1: Overview
# --------------------------------------------------
with tab1:
    st.subheader("Collections Overview")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Collections", len(summary_df))
    with col2:
        st.metric("Total Documents", int(summary_df["document_count"].sum()))
    with col3:
        largest_collection = summary_df.iloc[0]["collection"] if not summary_df.empty else "-"
        st.metric("Largest Collection", largest_collection)

    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    st.subheader("Documents by Collection")
    chart_df = summary_df[["collection", "document_count"]].set_index("collection")
    st.bar_chart(chart_df, use_container_width=True)

    st.subheader("Daily Documents Added Across All Collections")
    daily_all_df = all_collections_daily(db)

    if daily_all_df.empty:
        st.info("No timestamped records found.")
    else:
        pivot_df = daily_all_df.pivot(index="date", columns="collection", values="count").fillna(0)
        st.line_chart(pivot_df, use_container_width=True)

    st.subheader("Collection Explorer")

    collection_names = sorted(db.list_collection_names())
    selected_collection = st.selectbox("Choose a collection", collection_names, key="overview_collection")

    daily_df = docs_per_day(db, selected_collection)
    source_df = source_breakdown(db, selected_collection)

    left, right = st.columns(2)

    with left:
        st.markdown(f"### Daily Additions: `{selected_collection}`")
        if daily_df.empty:
            st.info("No date information found for this collection.")
        else:
            st.line_chart(daily_df.set_index("date")["count"], use_container_width=True)

    with right:
        st.markdown(f"### Source Breakdown: `{selected_collection}`")
        if source_df.empty:
            st.info("No source field found in this collection.")
        else:
            st.bar_chart(source_df.set_index("source")["count"], use_container_width=True)

    st.markdown(f"### Latest Records in `{selected_collection}`")
    latest_limit_overview = st.slider(
        "How many latest records to show",
        min_value=5,
        max_value=50,
        value=10,
        step=5,
        key="overview_latest_slider"
    )
    latest_df = latest_docs(db, selected_collection, limit=latest_limit_overview)

    if latest_df.empty:
        st.info("No records found.")
    else:
        st.dataframe(latest_df, use_container_width=True, hide_index=True)

# --------------------------------------------------
# TAB 2: Raw Historical
# --------------------------------------------------
with tab2:
    st.subheader("Raw Historical Collection")
    st.caption("Exploring published-date trends and ingestion runs from `raw_documents_historical`")

    raw_hist_df = get_collection_dataframe("raw_documents_historical")

    if raw_hist_df.empty:
        st.warning("No records found in `raw_documents_historical`.")
    else:
        latest_limit_raw = st.slider(
            "Latest article table size",
            min_value=5,
            max_value=50,
            value=20,
            step=5,
            key="raw_latest_limit"
        )

        source_options = sorted(raw_hist_df["source"].dropna().unique().tolist())
        st.write("Detected sources:", ", ".join(source_options) if source_options else "none")

        news_df = filter_by_source(raw_hist_df, "news")
        reddit_df = filter_by_source(raw_hist_df, "reddit")

        subtab1, subtab2 = st.tabs(["🗞️ News", "💬 Reddit"])

        with subtab1:
            render_source_section(news_df, "News Articles", latest_limit_raw)

        with subtab2:
            render_source_section(reddit_df, "Reddit Articles", latest_limit_raw)

# --------------------------------------------------
# TAB 3: Processed Documents
# --------------------------------------------------
with tab3:
    st.subheader("Processed Documents Collection")
    st.caption("Exploring processed travel content by publishing timeline and pipeline runs")

    processed_df = get_collection_dataframe("processed_documents")

    if processed_df.empty:
        st.warning("No records found in `processed_documents`.")
    else:
        latest_limit_processed = st.slider(
            "Latest processed article table size",
            min_value=5,
            max_value=50,
            value=20,
            step=5,
            key="processed_latest_limit"
        )

        source_options = sorted(processed_df["source"].dropna().unique().tolist())
        st.write("Detected sources:", ", ".join(source_options) if source_options else "none")

        news_df = filter_by_source(processed_df, "news")
        reddit_df = filter_by_source(processed_df, "reddit")

        subtab1, subtab2 = st.tabs(["🗞️ News", "💬 Reddit"])

        with subtab1:
            render_source_section(news_df, "News Articles", latest_limit_processed)

        with subtab2:
            render_source_section(reddit_df, "Reddit Articles", latest_limit_processed)