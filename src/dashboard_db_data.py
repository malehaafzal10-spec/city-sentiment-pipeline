import os
from pathlib import Path
from datetime import datetime, timezone

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
        flex-wrap: wrap;
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
    .feedback-card {
        background: white;
        border: 1px solid #e7eef4;
        border-radius: 12px;
        padding: 14px 16px;
        margin-bottom: 10px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.04);
    }
    .star-rating { font-size: 1.2rem; }
    .feedback-comment { font-size: 0.85rem; color: #555; margin-top: 4px; font-style: italic; }
    .feedback-meta { font-size: 0.72rem; color: #aaa; margin-top: 6px; }
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
    if not doc:
        return pd.NaT
    for field in ["created_at", "timestamp", "fetched_at", "ingested_at", "date_fetched", "aggregated_at"]:
        if field in doc and doc[field]:
            try:
                dt = pd.to_datetime(doc[field], errors="coerce", utc=True)
                if pd.notna(dt):
                    try:
                        return dt.tz_localize(None)
                    except Exception:
                        return dt
            except Exception:
                pass
    try:
        return pd.to_datetime(doc["_id"].generation_time).tz_localize(None)
    except Exception:
        return pd.NaT


def get_published_datetime(doc):
    if not doc:
        return pd.NaT
    for field in ["published_at", "publishedAt", "publication_date", "published_date", "date"]:
        if field in doc and doc[field]:
            try:
                dt = pd.to_datetime(doc[field], errors="coerce", utc=True)
                if pd.notna(dt):
                    try:
                        return dt.tz_localize(None)
                    except Exception:
                        return dt
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


def classify_sentiment(score):
    try:
        score = float(score)
    except Exception:
        return "unknown"
    if score > 0:
        return "positive"
    if score < 0:
        return "negative"
    return "neutral"


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
            dates.append(pd.to_datetime(dt).date())
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
            "city": str(doc.get("city", "")).strip()[:100],
            "published_at": get_published_datetime(doc),
            "added_at": get_doc_added_datetime(doc),
            "run_id": str(doc.get("run_id", "")).strip()[:100],
            "url": str(doc.get("url", ""))[:250],
            "sentiment_score": pd.to_numeric(doc.get("sentiment_score", None), errors="coerce"),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    if "published_at" in df.columns:
        df["published_date"] = pd.to_datetime(df["published_at"], errors="coerce").dt.date
    if "added_at" in df.columns:
        df["added_date"] = pd.to_datetime(df["added_at"], errors="coerce").dt.date
    return df


def load_document_features(db):
    # Use city_weekly_features which has actual metric values per city per week
    rows = []
    docs = list(db["city_weekly_features"].find())
    for doc in docs:
        city = str(doc.get("city", "")).strip()
        if not city:
            continue
        # Use week_start as the time axis
        week_start = doc.get("week_start", "")
        rows.append({
            "_id": str(doc.get("_id", "")),
            "city": city,
            "week_start": week_start,
            "mention_count": pd.to_numeric(doc.get("mention_count", None), errors="coerce"),
            "avg_sentiment": pd.to_numeric(doc.get("avg_sentiment", None), errors="coerce"),
            "positive_ratio": pd.to_numeric(doc.get("positive_ratio", None), errors="coerce"),
            "negative_ratio": pd.to_numeric(doc.get("negative_ratio", None), errors="coerce"),
            "neutral_ratio": pd.to_numeric(doc.get("neutral_ratio", None), errors="coerce"),
            "crowding_score": pd.to_numeric(doc.get("crowding_score", None), errors="coerce"),
            "cost_score": pd.to_numeric(doc.get("cost_score", None), errors="coerce"),
            "safety_score": pd.to_numeric(doc.get("safety_score", None), errors="coerce"),
            "run_id": str(doc.get("run_id", "")).strip(),
            "aggregated_at": pd.to_datetime(week_start, errors="coerce"),
        })
    df = pd.DataFrame(rows)
    return df


def load_feedback(db):
    col = db["user_feedback"]
    docs = list(col.find().sort("submitted_at", -1))
    rows = []
    for doc in docs:
        submitted = doc.get("submitted_at")
        try:
            submitted_str = pd.to_datetime(submitted, utc=True).strftime("%Y-%m-%d %H:%M UTC") if submitted else "—"
        except Exception:
            submitted_str = str(submitted)
        rows.append({
            "rating": int(doc.get("rating", 0)),
            "comment": str(doc.get("comment", "")).strip(),
            "submitted_at": submitted_str,
            "source": str(doc.get("source", "public_dashboard")),
        })
    return pd.DataFrame(rows)


@st.cache_data(ttl=300)
def get_collection_dataframe(collection_name):
    return load_collection_docs(db, collection_name)


@st.cache_data(ttl=300)
def get_document_features_dataframe():
    return load_document_features(db)


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


def docs_by_city_from_df(df):
    if df.empty or "city" not in df.columns:
        return pd.DataFrame(columns=["city", "count"])
    temp = df.copy()
    temp["city"] = temp["city"].fillna("").astype(str).str.strip()
    temp = temp[temp["city"] != ""]
    if temp.empty:
        return pd.DataFrame(columns=["city", "count"])
    result = (
        temp.groupby("city")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .head(15)
    )
    return result


def latest_article_table_from_df(df, limit=20):
    if df.empty:
        return pd.DataFrame(columns=["title", "source", "city", "published_at", "added_at", "sentiment_score", "url", "run_id"])
    cols = ["title", "source", "city", "published_at", "added_at", "sentiment_score", "url", "run_id"]
    available_cols = [c for c in cols if c in df.columns]
    latest = df.sort_values("added_at", ascending=False).head(limit).copy()
    return latest[available_cols]


def sentiment_score_distribution(df):
    if df.empty or "sentiment_score" not in df.columns:
        return pd.DataFrame(columns=["sentiment_score", "count"])
    temp = df.dropna(subset=["sentiment_score"]).copy()
    if temp.empty:
        return pd.DataFrame(columns=["sentiment_score", "count"])
    temp["sentiment_score_rounded"] = temp["sentiment_score"].round(2)
    result = (
        temp.groupby("sentiment_score_rounded")
        .size()
        .reset_index(name="count")
        .sort_values("sentiment_score_rounded")
        .rename(columns={"sentiment_score_rounded": "sentiment_score"})
    )
    return result


def city_sentiment_summary(df):
    if df.empty or "city" not in df.columns or "sentiment_score" not in df.columns:
        return pd.DataFrame(columns=["city", "avg_sentiment"])
    temp = df.copy()
    temp["city"] = temp["city"].fillna("").astype(str).str.strip()
    temp = temp[(temp["city"] != "") & (temp["sentiment_score"].notna())]
    if temp.empty:
        return pd.DataFrame(columns=["city", "avg_sentiment"])
    result = (
        temp.groupby("city")["sentiment_score"]
        .mean()
        .reset_index(name="avg_sentiment")
        .sort_values("avg_sentiment", ascending=False)
    )
    return result


def sentiment_label_counts(df):
    if df.empty or "sentiment_score" not in df.columns:
        return pd.DataFrame(columns=["sentiment", "count"])
    temp = df.dropna(subset=["sentiment_score"]).copy()
    if temp.empty:
        return pd.DataFrame(columns=["sentiment", "count"])
    temp["sentiment"] = temp["sentiment_score"].apply(classify_sentiment)
    result = temp.groupby("sentiment").size().reset_index(name="count")
    order = ["positive", "neutral", "negative", "unknown"]
    result["sort_order"] = result["sentiment"].apply(lambda x: order.index(x) if x in order else 999)
    result = result.sort_values("sort_order").drop(columns="sort_order")
    return result


def feature_history_for_city(df, city_name, feature_name):
    if df.empty:
        return pd.DataFrame(columns=["aggregated_at", feature_name, "run_id"])
    temp = df.copy()
    temp["city"] = temp["city"].fillna("").astype(str).str.strip()
    temp = temp[temp["city"] == city_name].copy()
    if temp.empty:
        return pd.DataFrame(columns=["aggregated_at", feature_name, "run_id"])
    # Use week_start as aggregated_at if aggregated_at is missing
    if "aggregated_at" not in temp.columns or temp["aggregated_at"].isna().all():
        if "week_start" in temp.columns:
            temp["aggregated_at"] = pd.to_datetime(temp["week_start"], errors="coerce")
        else:
            return pd.DataFrame(columns=["aggregated_at", feature_name, "run_id"])
    else:
        temp["aggregated_at"] = pd.to_datetime(temp["aggregated_at"], errors="coerce")
        if "week_start" in temp.columns:
            mask = temp["aggregated_at"].isna()
            temp.loc[mask, "aggregated_at"] = pd.to_datetime(temp.loc[mask, "week_start"], errors="coerce")
    temp = temp.dropna(subset=["aggregated_at"])
    if feature_name not in temp.columns or temp[feature_name].isna().all():
        return pd.DataFrame(columns=["aggregated_at", feature_name, "run_id"])
    temp = temp.dropna(subset=[feature_name])
    if temp.empty:
        return pd.DataFrame(columns=["aggregated_at", feature_name, "run_id"])
    temp = temp.sort_values("aggregated_at")
    return temp[["aggregated_at", feature_name, "run_id"]].copy()

def latest_feature_snapshot(df):
    if df.empty:
        return df
    temp = df.copy()
    temp["city"] = temp["city"].fillna("").astype(str).str.strip()
    temp = temp[temp["city"] != ""].copy()
    if temp.empty:
        return temp
    # Use aggregated_at or fall back to week_start
    if "aggregated_at" not in temp.columns or temp["aggregated_at"].isna().all():
        if "week_start" in temp.columns:
            temp["aggregated_at"] = pd.to_datetime(temp["week_start"], errors="coerce")
        else:
            return temp.groupby("city", as_index=False).tail(1).sort_values("city")
    else:
        temp["aggregated_at"] = pd.to_datetime(temp["aggregated_at"], errors="coerce")
        if "week_start" in temp.columns:
            mask = temp["aggregated_at"].isna()
            temp.loc[mask, "aggregated_at"] = pd.to_datetime(temp.loc[mask, "week_start"], errors="coerce")
    temp = temp.dropna(subset=["aggregated_at"])
    if temp.empty:
        return temp
    temp = temp.sort_values("aggregated_at")
    latest = temp.groupby("city", as_index=False).tail(1)
    return latest.sort_values("city")


def render_timeseries_chart(df, x_col, y_col, title):
    st.markdown(f"### {title}")
    if df.empty:
        st.info("No data available for this view.")
    else:
        st.line_chart(df.set_index(x_col)[y_col], use_container_width=True)


def render_runid_chart(df, title):
    st.markdown(f"### {title}")
    if df.empty:
        st.info("No run_id data available.")
    else:
        st.bar_chart(df.set_index("run_id")["count"], use_container_width=True)
        st.dataframe(df, use_container_width=True, hide_index=True)


def render_city_chart(df, title, value_col="count"):
    st.markdown(f"### {title}")
    if df.empty:
        st.info("No city data available.")
    else:
        st.bar_chart(df.set_index("city")[value_col], use_container_width=True)
        st.dataframe(df, use_container_width=True, hide_index=True)


def render_latest_table(df, title):
    st.markdown(f"### {title}")
    if df.empty:
        st.info("No records found.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def render_source_section(df, section_title, latest_limit):
    st.markdown(f"## {section_title}")
    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    total_docs = len(df)
    total_dates = df["published_date"].nunique() if not df.empty and "published_date" in df.columns else 0
    total_runs = df["run_id"].replace("", pd.NA).dropna().nunique() if not df.empty and "run_id" in df.columns else 0
    total_cities = df["city"].replace("", pd.NA).dropna().nunique() if not df.empty and "city" in df.columns else 0
    with metric_col1:
        st.metric("Documents", total_docs)
    with metric_col2:
        st.metric("Published Dates", total_dates)
    with metric_col3:
        st.metric("Run IDs", total_runs)
    with metric_col4:
        st.metric("Cities", total_cities)
    date_df = docs_by_published_date_from_df(df)
    run_df = docs_by_run_id_from_df(df)
    city_df = docs_by_city_from_df(df)
    latest_df = latest_article_table_from_df(df, limit=latest_limit)
    left, right = st.columns([1.4, 1])
    with left:
        render_timeseries_chart(date_df, "published_date", "count", f"{section_title} — Articles by Published Date")
    with right:
        render_latest_table(latest_df, f"{section_title} — Latest {latest_limit} Articles")
    render_city_chart(city_df, f"{section_title} — Articles per City", value_col="count")
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
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🧭 Overview",
    "📰 Raw Historical",
    "✨ Processed Documents",
    "💬 Scored Documents",
    "🏙️ Document Features",
    "⭐ User Feedback"
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
    latest_limit_overview = st.slider("How many latest records to show", min_value=5, max_value=50, value=10, step=5, key="overview_latest_slider")
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
        latest_limit_raw = st.slider("Latest article table size", min_value=5, max_value=50, value=20, step=5, key="raw_latest_limit")
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
        latest_limit_processed = st.slider("Latest processed article table size", min_value=5, max_value=50, value=20, step=5, key="processed_latest_limit")
        source_options = sorted(processed_df["source"].dropna().unique().tolist())
        st.write("Detected sources:", ", ".join(source_options) if source_options else "none")
        news_df = filter_by_source(processed_df, "news")
        reddit_df = filter_by_source(processed_df, "reddit")
        subtab1, subtab2 = st.tabs(["🗞️ News", "💬 Reddit"])
        with subtab1:
            render_source_section(news_df, "News Articles", latest_limit_processed)
        with subtab2:
            render_source_section(reddit_df, "Reddit Articles", latest_limit_processed)

# --------------------------------------------------
# TAB 4: Scored Documents
# --------------------------------------------------
with tab4:
    st.subheader("Scored Documents")
    st.caption("Sentiment-driven exploration of scored travel-related content")
    scored_df = get_collection_dataframe("scored_documents")
    if scored_df.empty:
        st.warning("No records found in `scored_documents`.")
    else:
        metric1, metric2, metric3 = st.columns(3)
        with metric1:
            st.metric("Scored Documents", len(scored_df))
        with metric2:
            scored_city_count = scored_df["city"].replace("", pd.NA).dropna().nunique() if "city" in scored_df.columns else 0
            st.metric("Cities", scored_city_count)
        with metric3:
            avg_sentiment = round(scored_df["sentiment_score"].dropna().mean(), 3) if "sentiment_score" in scored_df.columns and scored_df["sentiment_score"].dropna().shape[0] > 0 else 0
            st.metric("Average Sentiment", avg_sentiment)
        sentiment_dist_df = sentiment_score_distribution(scored_df)
        city_sentiment_df = city_sentiment_summary(scored_df)
        sentiment_counts_df = sentiment_label_counts(scored_df)
        left, right = st.columns(2)
        with left:
            st.markdown("### Number of Articles per Sentiment Score")
            if sentiment_dist_df.empty:
                st.info("No sentiment score data available.")
            else:
                st.line_chart(sentiment_dist_df.set_index("sentiment_score")["count"], use_container_width=True)
                st.dataframe(sentiment_dist_df, use_container_width=True, hide_index=True)
        with right:
            st.markdown("### Cities and Sentiment")
            if city_sentiment_df.empty:
                st.info("No city sentiment data available.")
            else:
                st.bar_chart(city_sentiment_df.set_index("city")["avg_sentiment"], use_container_width=True)
                st.dataframe(city_sentiment_df, use_container_width=True, hide_index=True)
        st.markdown("### Positive vs Negative vs Neutral Sentiments")
        if sentiment_counts_df.empty:
            st.info("No sentiment labels available.")
        else:
            st.bar_chart(sentiment_counts_df.set_index("sentiment")["count"], use_container_width=True)
            st.dataframe(sentiment_counts_df, use_container_width=True, hide_index=True)

# --------------------------------------------------
# TAB 5: Document Features
# --------------------------------------------------
with tab5:
    st.subheader("Document Features")
    st.caption("City-level feature trends from the `document_features` collection")
    features_df = get_document_features_dataframe()
    if features_df.empty:
        st.warning("No records found in `document_features`.")
    else:
        latest_snapshot_df = latest_feature_snapshot(features_df)
        metric1, metric2, metric3 = st.columns(3)
        with metric1:
            st.metric("Feature Records", len(features_df))
        with metric2:
            st.metric("Cities", latest_snapshot_df["city"].nunique() if not latest_snapshot_df.empty else 0)
        with metric3:
            st.metric("Runs", features_df["run_id"].replace("", pd.NA).dropna().nunique() if "run_id" in features_df.columns else 0)
        st.markdown("### Latest Feature Snapshot by City")
        if latest_snapshot_df.empty:
            st.info("No latest feature snapshot available.")
        else:
            st.dataframe(latest_snapshot_df, use_container_width=True, hide_index=True)
        city_options = sorted([c for c in features_df["city"].dropna().unique().tolist() if str(c).strip() != ""])
        if not city_options:
            st.info("No city values found in `document_features`.")
        else:
            selected_city = st.selectbox("Choose a city", city_options, key="features_city_selector")
            feature_columns = ["mention_count", "avg_sentiment", "positive_ratio", "negative_ratio", "neutral_ratio", "crowding_score", "cost_score", "safety_score"]
            st.markdown(f"## Feature Trends for {selected_city}")
            for feature_name in feature_columns:
                feature_df = feature_history_for_city(features_df, selected_city, feature_name)
                st.markdown(f"### {feature_name.replace('_', ' ').title()}")
                if feature_df.empty:
                    st.info(f"No data available for {feature_name}.")
                else:
                    st.line_chart(feature_df.set_index("aggregated_at")[feature_name], use_container_width=True)
                    st.dataframe(feature_df, use_container_width=True, hide_index=True)

# --------------------------------------------------
# TAB 6: User Feedback
# --------------------------------------------------
with tab6:
    st.subheader("⭐ User Feedback")
    st.caption("All ratings and comments submitted from the public dashboard")

    try:
        feedback_df = load_feedback(db)

        if feedback_df.empty:
            st.info("No feedback submitted yet. Share the public dashboard URL to start collecting responses.")
        else:
            # Summary metrics
            avg_rating = feedback_df["rating"].mean()
            total_responses = len(feedback_df)
            with_comments = feedback_df[feedback_df["comment"] != ""]

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Responses", total_responses)
            m2.metric("Average Rating", f"{avg_rating:.1f} / 5")
            m3.metric("With Comments", len(with_comments))
            m4.metric("5-Star Ratings", len(feedback_df[feedback_df["rating"] == 5]))

            # Rating distribution chart
            st.markdown("### Rating Distribution")
            rating_counts = feedback_df.groupby("rating").size().reset_index(name="count")
            rating_counts["stars"] = rating_counts["rating"].apply(lambda x: "⭐" * x)
            st.bar_chart(rating_counts.set_index("rating")["count"], use_container_width=True)

            # Rating over time
            st.markdown("### Ratings Over Time")
            try:
                time_df = feedback_df.copy()
                time_df["date"] = pd.to_datetime(
                    time_df["submitted_at"].str[:10], errors="coerce"
                )
                time_df = time_df.dropna(subset=["date"])
                if not time_df.empty:
                    daily_avg = time_df.groupby("date")["rating"].mean().reset_index()
                    st.line_chart(daily_avg.set_index("date")["rating"], use_container_width=True)
            except Exception:
                st.info("Not enough data to show trend yet.")

            # Individual responses
            st.markdown("### All Responses")
            filter_col1, filter_col2 = st.columns(2)
            with filter_col1:
                min_rating = st.selectbox("Filter by minimum rating", [1, 2, 3, 4, 5], index=0, key="fb_min_rating")
            with filter_col2:
                show_comments_only = st.checkbox("Show only responses with comments", key="fb_comments_only")

            filtered = feedback_df[feedback_df["rating"] >= min_rating]
            if show_comments_only:
                filtered = filtered[filtered["comment"] != ""]

            if filtered.empty:
                st.info("No responses match your filter.")
            else:
                for _, row in filtered.iterrows():
                    rating = int(row["rating"])
                    stars = "⭐" * rating
                    comment = str(row["comment"]).strip() if row["comment"] else ""
                    submitted = str(row["submitted_at"])
                    # Build HTML safely without nested f-string
                    comment_part = f'<div class="feedback-comment">"{comment}"</div>' if comment else ""
                    html = (
                        f'<div class="feedback-card">'
                        f'<div class="star-rating">{stars}</div>'
                        f'{comment_part}'
                        f'<div class="feedback-meta">Submitted: {submitted}</div>'
                        f'</div>'
                    )
                    st.markdown(html, unsafe_allow_html=True)

            # Raw table
            with st.expander("View raw data table"):
                st.dataframe(feedback_df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Could not load feedback: {e}")