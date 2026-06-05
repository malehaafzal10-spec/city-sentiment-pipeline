import os
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from pymongo import MongoClient

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
    "reddit_comments_final": "Comments",
    "reddit_relevant": "Relevant Posts",
    "reddit_comments_relevant": "Relevant Comments",
}

OUTPUT_DIR = Path("eda_outputs")
PLOTS_DIR = Path("eda_plots")

OUTPUT_DIR.mkdir(exist_ok=True)
PLOTS_DIR.mkdir(exist_ok=True)


def get_daily_counts(collection_name, label):
    docs = list(
        db[collection_name].find(
            {},
            {"published_at": 1, "_id": 0}
        )
    )

    if not docs:
        return pd.DataFrame(columns=["date", label])

    df = pd.DataFrame(docs)

    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")
    df = df.dropna(subset=["published_at"])

    df["date"] = df["published_at"].dt.date

    daily_counts = (
        df.groupby("date")
        .size()
        .reset_index(name=label)
    )

    return daily_counts


# ── Create daily count tables ─────────────────────────────────────────────────
daily_tables = []

for collection_name, label in COLLECTIONS.items():
    daily = get_daily_counts(collection_name, label)
    daily_tables.append(daily)

    daily.to_csv(
        OUTPUT_DIR / f"{collection_name}_daily_temporal_counts.csv",
        index=False
    )

# ── Merge all collections into one table ──────────────────────────────────────
temporal_df = daily_tables[0]

for daily in daily_tables[1:]:
    temporal_df = temporal_df.merge(daily, on="date", how="outer")

temporal_df = temporal_df.sort_values("date").fillna(0)

# Cut off incomplete period
CUTOFF_DATE = pd.Timestamp("2026-06-01").date()

temporal_df = temporal_df[
    temporal_df["date"] <= CUTOFF_DATE
]

for col in temporal_df.columns:
    if col != "date":
        temporal_df[col] = temporal_df[col].astype(int)

temporal_df.to_csv(OUTPUT_DIR / "temporal_distribution_all_collections.csv", index=False)

print("\nTemporal distribution table:")
print(temporal_df.head())


# ── Plot 1: Posts vs Comments ─────────────────────────────────────────────────
plt.figure(figsize=(12, 6))

plt.plot(temporal_df["date"], temporal_df["Posts"], marker="o", label="Posts")
plt.plot(temporal_df["date"], temporal_df["Comments"], marker="o", label="Comments")

plt.title("Daily Distribution of Reddit Posts and Comments")
plt.xlabel("Publication Date")
plt.ylabel("Number of Documents")
plt.xticks(rotation=45)
plt.legend()
plt.tight_layout()

plt.savefig(PLOTS_DIR / "temporal_posts_comments_daily.png", dpi=300)
plt.close()


# ── Plot 2: Relevant Posts vs Relevant Comments ───────────────────────────────
plt.figure(figsize=(12, 6))

plt.plot(
    temporal_df["date"],
    temporal_df["Relevant Posts"],
    marker="o",
    label="Relevant Posts"
)

plt.plot(
    temporal_df["date"],
    temporal_df["Relevant Comments"],
    marker="o",
    label="Relevant Comments"
)

plt.title("Daily Distribution of Relevant Reddit Posts and Comments")
plt.xlabel("Publication Date")
plt.ylabel("Number of Relevant Documents")
plt.xticks(rotation=45)
plt.legend()
plt.tight_layout()

plt.savefig(PLOTS_DIR / "temporal_relevant_posts_comments_daily.png", dpi=300)
plt.close()


# ── Plot 3: All four collections together ─────────────────────────────────────
plt.figure(figsize=(12, 6))

for column in ["Posts", "Comments", "Relevant Posts", "Relevant Comments"]:
    plt.plot(
        temporal_df["date"],
        temporal_df[column],
        marker="o",
        label=column
    )

plt.title("Temporal Distribution Across Reddit Collections")
plt.xlabel("Publication Date")
plt.ylabel("Number of Documents")
plt.xticks(rotation=45)
plt.legend()
plt.tight_layout()

plt.savefig(PLOTS_DIR / "temporal_all_collections_daily.png", dpi=300)
plt.close()

print("\nTemporal EDA completed.")
print(f"CSV saved in: {OUTPUT_DIR.resolve()}")
print(f"Plots saved in: {PLOTS_DIR.resolve()}")