import os
from pathlib import Path
from collections import Counter

import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient
from tabulate import tabulate

# ── Load environment variables ────────────────────────────────────────────────
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable is not set.")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# ── Collections ───────────────────────────────────────────────────────────────
COLLECTIONS = {
    "reddit_posts_final": "Posts",
    "reddit_relevant": "Relevant Posts",
    "reddit_comments_final": "Comments",
    "reddit_comments_relevant": "Relevant Comments",
}

OUTPUT_DIR = Path("eda_outputs")
OUTPUT_DIR.mkdir(exist_ok=True)


# ── Helper functions ──────────────────────────────────────────────────────────
def get_nested(doc, path, default=None):
    keys = path.split(".")
    value = doc

    for key in keys:
        if isinstance(value, dict):
            value = value.get(key, default)
        else:
            return default

    return value


def flatten_list(docs, path):
    values = []
    for doc in docs:
        item = get_nested(doc, path, [])
        if isinstance(item, list):
            values.extend(item)
    return values


def has_location(doc):
    cities = get_nested(doc, "locations.cities", [])
    countries = get_nested(doc, "locations.countries", [])
    mentioned_cities = doc.get("mentioned_cities", [])
    mentioned_countries = doc.get("mentioned_countries", [])

    return bool(cities or countries or mentioned_cities or mentioned_countries)


def count_missing(docs, path):
    missing = 0
    for doc in docs:
        value = get_nested(doc, path)
        if value is None or value == "" or value == [] or value == {}:
            missing += 1
    return missing


def save_csv(df, filename):
    path = OUTPUT_DIR / filename
    df.to_csv(path, index=False)
    print(f"Saved: {path}")


def save_counter(counter, filename, key_name):
    df = pd.DataFrame(counter.items(), columns=[key_name, "count"])

    if not df.empty:
        df = df.sort_values("count", ascending=False)

    save_csv(df, filename)
    return df


# ── Main EDA ──────────────────────────────────────────────────────────────────
summary_rows = []
all_aspect_rows = []
all_subreddit_rows = []

for collection_name, collection_label in COLLECTIONS.items():
    print(f"\nProcessing collection: {collection_name}")

    docs = list(db[collection_name].find())

    if not docs:
        print(f"No documents found in {collection_name}")
        continue

    df = pd.DataFrame(docs)

    published_at = pd.to_datetime(df.get("published_at"), errors="coerce")
    fetched_at = pd.to_datetime(df.get("fetched_at"), errors="coerce")

    cities = flatten_list(docs, "locations.cities")
    countries = flatten_list(docs, "locations.countries")

    documents_with_location = sum(has_location(doc) for doc in docs)
    location_coverage_percent = round((documents_with_location / len(docs)) * 100, 2)

    if "text" in df.columns:
        text_lengths = df["text"].fillna("").astype(str).str.len()
        avg_text_length = round(text_lengths.mean(), 2)
        median_text_length = round(text_lengths.median(), 2)
        min_text_length = int(text_lengths.min())
        max_text_length = int(text_lengths.max())
    else:
        avg_text_length = None
        median_text_length = None
        min_text_length = None
        max_text_length = None

    aspect_rows = []

    for doc in docs:
        aspects = get_nested(doc, "analysis.aspects", [])

        if not isinstance(aspects, list):
            continue

        for aspect in aspects:
            row = {
                "collection": collection_name,
                "collection_label": collection_label,
                "doc_id": doc.get("doc_id"),
                "post_id": doc.get("post_id"),
                "comment_id": doc.get("comment_id"),
                "type": doc.get("type"),
                "subreddit": doc.get("subreddit"),
                "published_at": doc.get("published_at"),
                "aspect": aspect.get("aspect"),
                "aspect_normalized": str(aspect.get("aspect")).lower().strip(),
                "sentiment_score": aspect.get("sentiment_score"),
                "city": aspect.get("city"),
                "country": aspect.get("country"),
            }

            aspect_rows.append(row)
            all_aspect_rows.append(row)

    aspect_df = pd.DataFrame(aspect_rows)

    total_docs = len(df)
    total_aspects = len(aspect_df)
    avg_aspects_per_doc = total_aspects / total_docs if total_docs else 0

    summary_rows.append({
        "collection": collection_name,
        "label": collection_label,
        "total_documents": total_docs,
        "unique_doc_ids": df["doc_id"].nunique() if "doc_id" in df.columns else None,
        "unique_post_ids": df["post_id"].nunique() if "post_id" in df.columns else None,
        "unique_comment_ids": df["comment_id"].nunique() if "comment_id" in df.columns else None,
        "unique_urls": df["url"].nunique() if "url" in df.columns else None,
        "duplicate_doc_ids": df["doc_id"].duplicated().sum() if "doc_id" in df.columns else None,
        "duplicate_urls": df["url"].duplicated().sum() if "url" in df.columns else None,
        "earliest_published_at": published_at.min(),
        "latest_published_at": published_at.max(),
        "earliest_fetched_at": fetched_at.min(),
        "latest_fetched_at": fetched_at.max(),
        "unique_cities": len(set(cities)),
        "unique_countries": len(set(countries)),
        "total_city_mentions": len(cities),
        "total_country_mentions": len(countries),
        "documents_with_location": documents_with_location,
        "location_coverage_percent": location_coverage_percent,
        "total_extracted_aspects": total_aspects,
        "avg_aspects_per_document": round(avg_aspects_per_doc, 2),
        "avg_text_length_chars": avg_text_length,
        "median_text_length_chars": median_text_length,
        "min_text_length_chars": min_text_length,
        "max_text_length_chars": max_text_length,
        "missing_text": count_missing(docs, "text"),
        "missing_locations": count_missing(docs, "locations"),
        "missing_analysis": count_missing(docs, "analysis"),
        "missing_aspects": count_missing(docs, "analysis.aspects"),
    })

    # Basic distributions
    for column in ["type", "source", "subreddit", "location_source", "run_id"]:
        if column in df.columns:
            out = df[column].value_counts(dropna=False).reset_index()
            out.columns = [column, "count"]
            save_csv(out, f"{collection_name}_{column}_distribution.csv")

    # Subreddit summary rows
    if "subreddit" in df.columns:
        subreddit_counts = df["subreddit"].value_counts(dropna=False)
        for subreddit, count in subreddit_counts.items():
            all_subreddit_rows.append({
                "collection": collection_name,
                "label": collection_label,
                "subreddit": subreddit,
                "count": count,
            })

    # Daily counts
    if "published_at" in df.columns:
        daily_counts = published_at.dt.date.value_counts().sort_index().reset_index()
        daily_counts.columns = ["date", "count"]
        save_csv(daily_counts, f"{collection_name}_daily_counts.csv")

    # Locations
    save_counter(Counter(cities), f"{collection_name}_top_cities.csv", "city")
    save_counter(Counter(countries), f"{collection_name}_top_countries.csv", "country")

    # Top 20 locations
    save_counter(Counter(cities), f"{collection_name}_top_20_cities.csv", "city").head(20).to_csv(
        OUTPUT_DIR / f"{collection_name}_top_20_cities.csv", index=False
    )

    save_counter(Counter(countries), f"{collection_name}_top_20_countries.csv", "country").head(20).to_csv(
        OUTPUT_DIR / f"{collection_name}_top_20_countries.csv", index=False
    )

    # Relevance distribution
    relevance_values = [
        get_nested(doc, "analysis.relevant")
        for doc in docs
        if get_nested(doc, "analysis.relevant") is not None
    ]

    save_counter(
        Counter(relevance_values),
        f"{collection_name}_relevance_distribution.csv",
        "relevant"
    )

    # Text type distribution
    text_types = [
        get_nested(doc, "analysis.text_type")
        for doc in docs
        if get_nested(doc, "analysis.text_type") is not None
    ]

    save_counter(
        Counter(text_types),
        f"{collection_name}_text_type_distribution.csv",
        "text_type"
    )

    # Aspect statistics
    if not aspect_df.empty:
        save_csv(aspect_df, f"{collection_name}_aspects_long_format.csv")

        aspect_frequency = (
            aspect_df["aspect_normalized"]
            .value_counts()
            .reset_index()
        )
        aspect_frequency.columns = ["aspect", "count"]
        save_csv(aspect_frequency, f"{collection_name}_aspect_frequency.csv")
        save_csv(aspect_frequency.head(20), f"{collection_name}_top_20_aspects.csv")

        sentiment_distribution = (
            aspect_df["sentiment_score"]
            .value_counts()
            .sort_index()
            .reset_index()
        )
        sentiment_distribution.columns = ["sentiment_score", "count"]
        save_csv(sentiment_distribution, f"{collection_name}_sentiment_distribution.csv")

        sentiment_summary = aspect_df["sentiment_score"].describe().reset_index()
        sentiment_summary.columns = ["metric", "value"]
        save_csv(sentiment_summary, f"{collection_name}_sentiment_summary.csv")

        sentiment_by_aspect = (
            aspect_df
            .dropna(subset=["sentiment_score"])
            .groupby("aspect_normalized")
            .agg(
                count=("sentiment_score", "count"),
                mean_sentiment=("sentiment_score", "mean"),
                median_sentiment=("sentiment_score", "median"),
                min_sentiment=("sentiment_score", "min"),
                max_sentiment=("sentiment_score", "max"),
                std_sentiment=("sentiment_score", "std"),
            )
            .reset_index()
            .rename(columns={"aspect_normalized": "aspect"})
            .sort_values("count", ascending=False)
        )

        save_csv(sentiment_by_aspect, f"{collection_name}_sentiment_by_aspect.csv")
        save_csv(sentiment_by_aspect.head(20), f"{collection_name}_top_20_aspects_with_sentiment.csv")

        sentiment_by_city = (
            aspect_df
            .dropna(subset=["city", "sentiment_score"])
            .groupby("city")
            .agg(
                count=("sentiment_score", "count"),
                mean_sentiment=("sentiment_score", "mean"),
                median_sentiment=("sentiment_score", "median"),
            )
            .reset_index()
            .sort_values("count", ascending=False)
        )

        save_csv(sentiment_by_city, f"{collection_name}_sentiment_by_city.csv")
        save_csv(sentiment_by_city.head(20), f"{collection_name}_top_20_cities_with_sentiment.csv")

        sentiment_by_country = (
            aspect_df
            .dropna(subset=["country", "sentiment_score"])
            .groupby("country")
            .agg(
                count=("sentiment_score", "count"),
                mean_sentiment=("sentiment_score", "mean"),
                median_sentiment=("sentiment_score", "median"),
            )
            .reset_index()
            .sort_values("count", ascending=False)
        )

        save_csv(sentiment_by_country, f"{collection_name}_sentiment_by_country.csv")
        save_csv(sentiment_by_country.head(20), f"{collection_name}_top_20_countries_with_sentiment.csv")


# ── Global summaries ──────────────────────────────────────────────────────────
summary_df = pd.DataFrame(summary_rows)
save_csv(summary_df, "dataset_summary_all_collections.csv")

all_aspects_df = pd.DataFrame(all_aspect_rows)

if not all_aspects_df.empty:
    save_csv(all_aspects_df, "all_aspects_long_format.csv")

    global_aspect_frequency = (
        all_aspects_df["aspect_normalized"]
        .value_counts()
        .reset_index()
    )
    global_aspect_frequency.columns = ["aspect", "count"]
    save_csv(global_aspect_frequency, "global_aspect_frequency.csv")
    save_csv(global_aspect_frequency.head(20), "global_top_20_aspects.csv")

    global_sentiment_distribution = (
        all_aspects_df["sentiment_score"]
        .value_counts()
        .sort_index()
        .reset_index()
    )
    global_sentiment_distribution.columns = ["sentiment_score", "count"]
    save_csv(global_sentiment_distribution, "global_sentiment_distribution.csv")

    global_sentiment_summary = all_aspects_df["sentiment_score"].describe().reset_index()
    global_sentiment_summary.columns = ["metric", "value"]
    save_csv(global_sentiment_summary, "global_sentiment_summary.csv")

    global_sentiment_by_aspect = (
        all_aspects_df
        .dropna(subset=["sentiment_score"])
        .groupby("aspect_normalized")
        .agg(
            count=("sentiment_score", "count"),
            mean_sentiment=("sentiment_score", "mean"),
            median_sentiment=("sentiment_score", "median"),
            min_sentiment=("sentiment_score", "min"),
            max_sentiment=("sentiment_score", "max"),
            std_sentiment=("sentiment_score", "std"),
        )
        .reset_index()
        .rename(columns={"aspect_normalized": "aspect"})
        .sort_values("count", ascending=False)
    )

    save_csv(global_sentiment_by_aspect, "global_sentiment_by_aspect.csv")
    save_csv(global_sentiment_by_aspect.head(20), "global_top_20_aspects_with_sentiment.csv")

    global_sentiment_by_country = (
        all_aspects_df
        .dropna(subset=["country", "sentiment_score"])
        .groupby("country")
        .agg(
            count=("sentiment_score", "count"),
            mean_sentiment=("sentiment_score", "mean"),
            median_sentiment=("sentiment_score", "median"),
        )
        .reset_index()
        .sort_values("count", ascending=False)
    )

    save_csv(global_sentiment_by_country, "global_sentiment_by_country.csv")
    save_csv(global_sentiment_by_country.head(20), "global_top_20_countries_with_sentiment.csv")

    global_sentiment_by_city = (
        all_aspects_df
        .dropna(subset=["city", "sentiment_score"])
        .groupby("city")
        .agg(
            count=("sentiment_score", "count"),
            mean_sentiment=("sentiment_score", "mean"),
            median_sentiment=("sentiment_score", "median"),
        )
        .reset_index()
        .sort_values("count", ascending=False)
    )

    save_csv(global_sentiment_by_city, "global_sentiment_by_city.csv")
    save_csv(global_sentiment_by_city.head(20), "global_top_20_cities_with_sentiment.csv")


# ── Subreddit summary ─────────────────────────────────────────────────────────
subreddit_df = pd.DataFrame(all_subreddit_rows)

if not subreddit_df.empty:
    save_csv(subreddit_df, "subreddit_distribution_by_collection.csv")

    global_subreddit_summary = (
        subreddit_df
        .groupby("subreddit")
        .agg(total_count=("count", "sum"))
        .reset_index()
        .sort_values("total_count", ascending=False)
    )

    save_csv(global_subreddit_summary, "global_subreddit_summary.csv")
    save_csv(global_subreddit_summary.head(20), "global_top_20_subreddits.csv")


# ── Filtering summary ─────────────────────────────────────────────────────────
posts_total = db["reddit_posts_final"].count_documents({})
posts_relevant = db["reddit_relevant"].count_documents({})

comments_total = db["reddit_comments_final"].count_documents({})
comments_relevant = db["reddit_comments_relevant"].count_documents({})

filtering_summary = pd.DataFrame([
    {
        "data_type": "posts",
        "total_collected": posts_total,
        "relevant": posts_relevant,
        "not_relevant_or_filtered_out": posts_total - posts_relevant,
        "relevance_rate_percent": round((posts_relevant / posts_total) * 100, 2)
        if posts_total > 0 else 0,
    },
    {
        "data_type": "comments",
        "total_collected": comments_total,
        "relevant": comments_relevant,
        "not_relevant_or_filtered_out": comments_total - comments_relevant,
        "relevance_rate_percent": round((comments_relevant / comments_total) * 100, 2)
        if comments_total > 0 else 0,
    },
])

save_csv(filtering_summary, "filtering_summary.csv")


# ── Print key tables in terminal ──────────────────────────────────────────────
print("\nDATASET SUMMARY")
print(tabulate(summary_df, headers="keys", tablefmt="github", showindex=False))

print("\nFILTERING SUMMARY")
print(tabulate(filtering_summary, headers="keys", tablefmt="github", showindex=False))

if not all_aspects_df.empty:
    print("\nGLOBAL TOP 20 ASPECTS WITH SENTIMENT")
    print(tabulate(global_sentiment_by_aspect.head(20), headers="keys", tablefmt="github", showindex=False))

print("\nEDA completed successfully.")
print(f"All files saved in: {OUTPUT_DIR.resolve()}")