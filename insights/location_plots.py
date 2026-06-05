"""
Bar charts: Top 10 mentioned countries and cities (from relevant collections).
Cities excluded: Most, Nice, Tours (ambiguous / not travel destinations)

Usage:
  export MONGO_URI="mongodb://localhost:27017"
  export MONGO_DB_NAME="travel_pipeline_db"
  python plot_locations.py
"""

import os
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pymongo import MongoClient

# ── Config ────────────────────────────────────────────────────────────────────
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME   = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
OUT_DIR   = Path("eda_plots")
OUT_DIR.mkdir(exist_ok=True)

CITY_EXCLUDE = {"Most", "Nice", "Tours"}

RELEVANT_COLLECTIONS = ["reddit_relevant", "reddit_comments_relevant"]

# load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
    MONGO_URI = os.getenv("MONGO_URI")
    DB_NAME   = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
except ImportError:
    pass

if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable is not set.")

client = MongoClient(MONGO_URI)
db     = client[DB_NAME]

# ── Load relevant docs ────────────────────────────────────────────────────────
def get_locations(doc, key):
    locs = doc.get("locations")
    if isinstance(locs, dict):
        return [x for x in (locs.get(key) or []) if x]
    return []

def get_mentioned(doc, key):
    if key == "cities":
        direct = doc.get("mentioned_cities")
        if isinstance(direct, list) and direct:
            return [x for x in direct if x]
    if key == "countries":
        direct = doc.get("mentioned_countries")
        if isinstance(direct, list) and direct:
            return [x for x in direct if x]
    return get_locations(doc, key)

all_cities    = []
all_countries = []

for name in RELEVANT_COLLECTIONS:
    for doc in db[name].find():
        ana = doc.get("analysis")
        if not isinstance(ana, dict) or ana.get("relevant") != "yes":
            continue
        all_cities.extend(get_mentioned(doc, "cities"))
        all_countries.extend(get_mentioned(doc, "countries"))

# Filter excluded cities
all_cities = [c for c in all_cities if c not in CITY_EXCLUDE]

top_countries = Counter(all_countries).most_common(10)
top_cities    = Counter(all_cities).most_common(10)

# ── Style ─────────────────────────────────────────────────────────────────────
COUNTRY_COLOR = "#2E86AB"
CITY_COLOR    = "#E84855"
FONT          = "DejaVu Sans"

plt.rcParams.update({
    "font.family":    FONT,
    "axes.grid":      True,
    "grid.color":     "#e0e0e0",
    "grid.linewidth": 0.8,
})

def make_bar_chart(data, title, xlabel, color, filename):
    labels  = [d[0] for d in data]
    values  = [d[1] for d in data]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.grid(False)
    ax.xaxis.grid(True)
    bars = ax.barh(labels[::-1], values[::-1], color=color, height=0.6, zorder=3)

    # value labels at end of each bar
    for bar, val in zip(bars, values[::-1]):
        ax.text(
            bar.get_width() + max(values) * 0.01,
            bar.get_y() + bar.get_height() / 2,
            str(val),
            va="center", ha="left", fontsize=10, color="#333333"
        )

    ax.set_title(title, fontsize=14, fontweight="bold", pad=14)
    ax.set_xlabel(xlabel, fontsize=11)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.set_xlim(0, max(values) * 1.15)
    ax.tick_params(axis="y", labelsize=10)
    ax.tick_params(axis="x", labelsize=9)

    plt.tight_layout()
    path = OUT_DIR / filename
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓  {filename}")

# ── Generate charts ───────────────────────────────────────────────────────────
print("\n=== Generating location bar charts ===")

make_bar_chart(
    top_countries,
    title    = "Top 10 Most Mentioned Countries",
    xlabel   = "Number of mentions",
    color    = COUNTRY_COLOR,
    filename = "top10_countries.png",
)

make_bar_chart(
    top_cities,
    title    = "Top 10 Most Mentioned Cities",
    xlabel   = "Number of mentions",
    color    = CITY_COLOR,
    filename = "top10_cities.png",
)

print(f"\nSaved to: {OUT_DIR.resolve()}")
client.close()