"""
EDA & Results Statistics — Reddit Travel Collections
=====================================================
Outputs clean CSV files ready for plotting and paper reporting.

CSV outputs:
  eda_01_collection_overview.csv
  eda_02_location_stats_summary.csv
  eda_03_top20_countries.csv
  eda_04_top20_cities.csv
  eda_05a_aspect_summary_stats.csv
  eda_05b_top20_aspects.csv
  eda_05c_aspect_frequency_full.csv
  eda_06_sentiment_distribution.csv
  results_01_most_positive_aspects.csv
  results_02_most_negative_aspects.csv
  results_03_country_sentiment.csv
  results_04_city_sentiment.csv

Usage:
  pip install pymongo pandas
  export MONGO_URI="mongodb://localhost:27017"
  export MONGO_DB_NAME="travel_pipeline_db"
  python eda_stats.py
"""

import os
from collections import Counter
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from pymongo import MongoClient

# ── Config ────────────────────────────────────────────────────────────────────
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME   = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
OUT_DIR   = Path("eda_output")

if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable is not set.")

OUT_DIR.mkdir(exist_ok=True)
client = MongoClient(MONGO_URI)
db     = client[DB_NAME]

def save(df, filename):
    path = OUT_DIR / filename
    df.to_csv(path, index=False)
    print(f"  ✓  {filename}  ({len(df)} rows)")

print("\n=== Loading collections ===")

# ── All 4 collections for the overview ───────────────────────────────────────
ALL_COLLECTIONS = [
    "reddit_posts_final",
    "reddit_comments_final",
    "reddit_relevant",
    "reddit_comments_relevant",
]

# ── Only relevant collections for location / aspect / sentiment analysis ─────
RELEVANT_COLLECTIONS = [
    "reddit_relevant",
    "reddit_comments_relevant",
]

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def load_collection(name):
    docs = list(db[name].find())
    for d in docs:
        d["_collection"] = name
        d.pop("_id", None)
    return docs

def get_locations(doc, key):
    locs = doc.get("locations")
    if isinstance(locs, dict):
        return [x for x in (locs.get(key) or []) if x]
    return []

def get_aspects(doc):
    a = doc.get("analysis")
    if isinstance(a, dict):
        return [x for x in (a.get("aspects") or []) if isinstance(x, dict)]
    return []

def get_mentioned_locations(doc, key):
    """
    For reddit_comments_relevant: tries mentioned_cities / mentioned_countries first,
    falls back to locations field.
    """
    # prefer the explicit 'mentioned_*' fields where available
    if key == "cities":
        direct = doc.get("mentioned_cities")
        if isinstance(direct, list) and direct:
            return [x for x in direct if x]
    if key == "countries":
        direct = doc.get("mentioned_countries")
        if isinstance(direct, list) and direct:
            return [x for x in direct if x]
    return get_locations(doc, key)

# ─────────────────────────────────────────────────────────────────────────────
# EDA 01 — COLLECTION OVERVIEW
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== EDA 01 — Collection overview ===")

overview_rows = []
for name in ALL_COLLECTIONS:
    docs = load_collection(name)
    df   = pd.DataFrame(docs)

    n_posts    = int((df["type"] == "post").sum())    if "type" in df.columns else 0
    n_comments = int((df["type"] == "comment").sum()) if "type" in df.columns else 0

    pub = pd.to_datetime(df.get("published_at"), utc=True, errors="coerce").dropna()
    has_analysis = df["analysis"].notna().sum() if "analysis" in df.columns else 0

    relevant_count = None
    if "analysis" in df.columns:
        relevant_count = df["analysis"].apply(
            lambda x: x.get("relevant") == "yes" if isinstance(x, dict) else False
        ).sum()

    overview_rows.append({
        "collection":        name,
        "total_documents":   len(df),
        "posts":             n_posts,
        "comments":          n_comments,
        "unique_post_ids":   df["post_id"].nunique()    if "post_id"    in df.columns else None,
        "unique_doc_ids":    df["doc_id"].nunique()     if "doc_id"     in df.columns else None,
        "unique_urls":       df["url"].nunique()        if "url"        in df.columns else None,
        "unique_subreddits": df["subreddit"].nunique()  if "subreddit"  in df.columns else None,
        "date_earliest":     pub.min().date() if not pub.empty else None,
        "date_latest":       pub.max().date() if not pub.empty else None,
        "has_analysis":      int(has_analysis),
        "relevant_yes":      int(relevant_count) if relevant_count is not None else None,
    })

overview_df = pd.DataFrame(overview_rows)
save(overview_df, "eda_01_collection_overview.csv")

# ─────────────────────────────────────────────────────────────────────────────
# Load RELEVANT docs for all remaining analyses
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== Loading relevant collections ===")

rel_docs = []
for name in RELEVANT_COLLECTIONS:
    rel_docs.extend(load_collection(name))

rel_df = pd.DataFrame(rel_docs)

# Keep only relevant=yes
rel_df["_relevant"] = rel_df["analysis"].apply(
    lambda x: x.get("relevant") if isinstance(x, dict) else None
)
rel_df = rel_df[rel_df["_relevant"] == "yes"].copy()
print(f"  Relevant documents: {len(rel_df):,}")

# ─────────────────────────────────────────────────────────────────────────────
# EDA 02 — LOCATION STATS SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== EDA 02 — Location stats summary ===")

all_cities    = []
all_countries = []

for doc in rel_docs:
    if rel_df["_relevant"].tolist():  # only from filtered docs
        pass

# Re-iterate from filtered df rows (safe approach)
for _, row in rel_df.iterrows():
    all_cities.extend(get_mentioned_locations(row.to_dict(), "cities"))
    all_countries.extend(get_mentioned_locations(row.to_dict(), "countries"))

city_counter    = Counter(all_cities)
country_counter = Counter(all_countries)

top_city        = city_counter.most_common(1)[0]    if city_counter    else ("n/a", 0)
top_country     = country_counter.most_common(1)[0] if country_counter else ("n/a", 0)

has_city    = rel_df.apply(lambda r: bool(get_mentioned_locations(r.to_dict(), "cities")),    axis=1)
has_country = rel_df.apply(lambda r: bool(get_mentioned_locations(r.to_dict(), "countries")), axis=1)

summary_rows = [
    {"metric": "relevant_documents",              "value": len(rel_df)},
    {"metric": "unique_cities",                   "value": len(city_counter)},
    {"metric": "unique_countries",                "value": len(country_counter)},
    {"metric": "total_city_mentions",             "value": sum(city_counter.values())},
    {"metric": "total_country_mentions",          "value": sum(country_counter.values())},
    {"metric": "most_mentioned_city",             "value": top_city[0]},
    {"metric": "most_mentioned_city_count",       "value": top_city[1]},
    {"metric": "most_mentioned_country",          "value": top_country[0]},
    {"metric": "most_mentioned_country_count",    "value": top_country[1]},
    {"metric": "docs_with_city_extracted",        "value": int(has_city.sum())},
    {"metric": "docs_with_country_extracted",     "value": int(has_country.sum())},
    {"metric": "docs_with_no_location",           "value": int((~(has_city | has_country)).sum())},
]
save(pd.DataFrame(summary_rows), "eda_02_location_stats_summary.csv")

# ─────────────────────────────────────────────────────────────────────────────
# EDA 03 — TOP 20 COUNTRIES
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== EDA 03 — Top 20 countries ===")

country_df = pd.DataFrame(country_counter.most_common(20), columns=["country", "mentions"])
country_df["rank"]    = range(1, len(country_df) + 1)
country_df["pct_of_total_mentions"] = (
    country_df["mentions"] / country_df["mentions"].sum() * 100
).round(1)
country_df = country_df[["rank", "country", "mentions", "pct_of_total_mentions"]]
save(country_df, "eda_03_top20_countries.csv")

# ─────────────────────────────────────────────────────────────────────────────
# EDA 04 — TOP 20 CITIES
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== EDA 04 — Top 20 cities ===")

city_df = pd.DataFrame(city_counter.most_common(20), columns=["city", "mentions"])
city_df["rank"]    = range(1, len(city_df) + 1)
city_df["pct_of_total_mentions"] = (
    city_df["mentions"] / city_df["mentions"].sum() * 100
).round(1)
city_df = city_df[["rank", "city", "mentions", "pct_of_total_mentions"]]
save(city_df, "eda_04_top20_cities.csv")

# ─────────────────────────────────────────────────────────────────────────────
# Flatten all aspects from relevant docs
# ─────────────────────────────────────────────────────────────────────────────
aspect_records = []
for _, row in rel_df.iterrows():
    for asp in get_aspects(row.to_dict()):
        score = asp.get("sentiment_score")
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = None
        aspect_records.append({
            "aspect":          (asp.get("aspect") or "").lower().strip(),
            "sentiment_score": score,
            "city":            asp.get("city"),
            "country":         asp.get("country"),
            "doc_id":          row.get("doc_id"),
            "_collection":     row.get("_collection"),
        })

asp_df = pd.DataFrame(aspect_records)
asp_df["sentiment_score"] = pd.to_numeric(asp_df["sentiment_score"], errors="coerce")

print(f"  Total aspect instances: {len(asp_df):,}")

# ─────────────────────────────────────────────────────────────────────────────
# EDA 05 — ASPECT SUMMARY STATS  +  TOP 20  +  FULL FREQUENCY TABLE
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== EDA 05 — Aspect statistics ===")

asp_freq = (
    asp_df.groupby("aspect")
    .agg(
        mention_count   =("aspect", "count"),
        mean_sentiment  =("sentiment_score", "mean"),
        median_sentiment=("sentiment_score", "median"),
        std_sentiment   =("sentiment_score", "std"),
    )
    .sort_values("mention_count", ascending=False)
    .round(3)
    .reset_index()
)
asp_freq["rank"] = range(1, len(asp_freq) + 1)
asp_freq["pct_of_aspects"] = (asp_freq["mention_count"] / asp_freq["mention_count"].sum() * 100).round(1)
asp_freq = asp_freq[["rank", "aspect", "mention_count", "pct_of_aspects",
                      "mean_sentiment", "median_sentiment", "std_sentiment"]]

top_aspect_row  = asp_freq.iloc[0] if len(asp_freq) else None
valid_scores    = asp_df["sentiment_score"].dropna()
docs_with_aspects = sum(1 for doc in rel_df.to_dict("records") if get_aspects(doc))

# --- eda_05a: summary key metrics (the table you asked for) ---
asp_summary = pd.DataFrame([
    {"metric": "total_extracted_aspects",          "value": len(asp_df)},
    {"metric": "unique_aspects",                   "value": asp_df["aspect"].nunique()},
    {"metric": "avg_aspects_per_document",         "value": round(len(asp_df) / len(rel_df), 2)},
    {"metric": "most_frequent_aspect",             "value": top_aspect_row["aspect"] if top_aspect_row is not None else None},
    {"metric": "most_frequent_aspect_count",       "value": int(top_aspect_row["mention_count"]) if top_aspect_row is not None else None},
    {"metric": "total_sentiment_observations",     "value": len(valid_scores)},
    {"metric": "mean_sentiment_score",             "value": round(valid_scores.mean(), 3)},
    {"metric": "median_sentiment_score",           "value": valid_scores.median()},
    {"metric": "std_sentiment_score",              "value": round(valid_scores.std(), 3)},
    {"metric": "min_sentiment_score",              "value": valid_scores.min()},
    {"metric": "max_sentiment_score",              "value": valid_scores.max()},
])
save(asp_summary, "eda_05a_aspect_summary_stats.csv")

# --- eda_05b: top 20 aspects ---
save(asp_freq.head(20), "eda_05b_top20_aspects.csv")

# --- eda_05c: full frequency table (all aspects) ---
save(asp_freq, "eda_05c_aspect_frequency_full.csv")

# ─────────────────────────────────────────────────────────────────────────────
# EDA 06 — SENTIMENT SCORE DISTRIBUTION
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== EDA 06 — Sentiment distribution ===")

score_dist = (
    asp_df["sentiment_score"]
    .dropna()
    .value_counts()
    .sort_index()
    .reset_index()
)
score_dist.columns = ["sentiment_score", "count"]
score_dist["pct"] = (score_dist["count"] / score_dist["count"].sum() * 100).round(1)
save(score_dist, "eda_06_sentiment_distribution.csv")

# ─────────────────────────────────────────────────────────────────────────────
# RESULTS 01 — MOST POSITIVELY PERCEIVED ASPECTS
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== Results 01 — Most positive aspects ===")

MIN_MENTIONS = 3

positive_aspects = (
    asp_df.groupby("aspect")
    .agg(
        mention_count   =("aspect", "count"),
        mean_sentiment  =("sentiment_score", "mean"),
        median_sentiment=("sentiment_score", "median"),
        std_sentiment   =("sentiment_score", "std"),
    )
    .query(f"mention_count >= {MIN_MENTIONS}")
    .sort_values("mean_sentiment", ascending=False)
    .round(3)
    .reset_index()
)
positive_aspects["rank"] = range(1, len(positive_aspects) + 1)
positive_aspects = positive_aspects[["rank", "aspect", "mention_count",
                                      "mean_sentiment", "median_sentiment", "std_sentiment"]]
save(positive_aspects, "results_01_most_positive_aspects.csv")

# ─────────────────────────────────────────────────────────────────────────────
# RESULTS 02 — MOST NEGATIVELY PERCEIVED ASPECTS
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== Results 02 — Most negative aspects ===")

negative_aspects = positive_aspects.copy().sort_values("mean_sentiment", ascending=True).reset_index(drop=True)
negative_aspects["rank"] = range(1, len(negative_aspects) + 1)
save(negative_aspects, "results_02_most_negative_aspects.csv")

# ─────────────────────────────────────────────────────────────────────────────
# RESULTS 03 — COUNTRY-LEVEL SENTIMENT
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== Results 03 — Country-level sentiment ===")

country_asp = asp_df[asp_df["country"].notna() & (asp_df["country"] != "")]

country_sentiment = (
    country_asp.groupby("country")
    .agg(
        aspect_mentions  =("aspect", "count"),
        unique_aspects   =("aspect", "nunique"),
        mean_sentiment   =("sentiment_score", "mean"),
        median_sentiment =("sentiment_score", "median"),
        std_sentiment    =("sentiment_score", "std"),
        min_sentiment    =("sentiment_score", "min"),
        max_sentiment    =("sentiment_score", "max"),
    )
    .query(f"aspect_mentions >= {MIN_MENTIONS}")
    .sort_values("mean_sentiment", ascending=False)
    .round(3)
    .reset_index()
)
country_sentiment["rank"] = range(1, len(country_sentiment) + 1)

# top positive / negative aspect per country
def top_aspect(group, ascending=False):
    s = group.groupby("aspect")["sentiment_score"].mean().sort_values(ascending=ascending)
    return s.index[0] if len(s) else None

country_sentiment["top_positive_aspect"] = country_sentiment["country"].apply(
    lambda c: top_aspect(country_asp[country_asp["country"] == c], ascending=False)
)
country_sentiment["top_negative_aspect"] = country_sentiment["country"].apply(
    lambda c: top_aspect(country_asp[country_asp["country"] == c], ascending=True)
)

country_sentiment = country_sentiment[["rank", "country", "aspect_mentions", "unique_aspects",
                                        "mean_sentiment", "median_sentiment", "std_sentiment",
                                        "min_sentiment", "max_sentiment",
                                        "top_positive_aspect", "top_negative_aspect"]]
save(country_sentiment, "results_03_country_sentiment.csv")

# ─────────────────────────────────────────────────────────────────────────────
# RESULTS 04 — CITY-LEVEL SENTIMENT
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== Results 04 — City-level sentiment ===")

city_asp = asp_df[asp_df["city"].notna() & (asp_df["city"] != "")]

city_sentiment = (
    city_asp.groupby("city")
    .agg(
        aspect_mentions  =("aspect", "count"),
        unique_aspects   =("aspect", "nunique"),
        mean_sentiment   =("sentiment_score", "mean"),
        median_sentiment =("sentiment_score", "median"),
        std_sentiment    =("sentiment_score", "std"),
        min_sentiment    =("sentiment_score", "min"),
        max_sentiment    =("sentiment_score", "max"),
    )
    .query(f"aspect_mentions >= {MIN_MENTIONS}")
    .sort_values("mean_sentiment", ascending=False)
    .round(3)
    .reset_index()
)
city_sentiment["rank"] = range(1, len(city_sentiment) + 1)

city_sentiment["top_positive_aspect"] = city_sentiment["city"].apply(
    lambda c: top_aspect(city_asp[city_asp["city"] == c], ascending=False)
)
city_sentiment["top_negative_aspect"] = city_sentiment["city"].apply(
    lambda c: top_aspect(city_asp[city_asp["city"] == c], ascending=True)
)

city_sentiment = city_sentiment[["rank", "city", "aspect_mentions", "unique_aspects",
                                  "mean_sentiment", "median_sentiment", "std_sentiment",
                                  "min_sentiment", "max_sentiment",
                                  "top_positive_aspect", "top_negative_aspect"]]
save(city_sentiment, "results_04_city_sentiment.csv")

# ─────────────────────────────────────────────────────────────────────────────
print(f"""
=== Done ===
All files saved to: {OUT_DIR.resolve()}

  EDA files:
    eda_01_collection_overview.csv      — document counts, date ranges per collection
    eda_02_location_stats_summary.csv   — unique cities/countries, top mentions
    eda_03_top20_countries.csv          — top 20 countries by mention count
    eda_04_top20_cities.csv             — top 20 cities by mention count
    eda_05a_aspect_summary_stats.csv    — key metrics: totals, mean, median, std, min, max
    eda_05b_top20_aspects.csv           — top 20 aspects by frequency + sentiment
    eda_05c_aspect_frequency_full.csv   — all aspects ranked by frequency
    eda_06_sentiment_distribution.csv   — score distribution 1–5 with %

  Results files:
    results_01_most_positive_aspects.csv — ranked by highest mean sentiment
    results_02_most_negative_aspects.csv — ranked by lowest mean sentiment
    results_03_country_sentiment.csv     — country-level sentiment + top/bottom aspect
    results_04_city_sentiment.csv        — city-level sentiment + top/bottom aspect
""")

client.close()