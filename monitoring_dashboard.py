"""
monitoring_dashboard.py — Internal Pipeline Monitoring Dashboard
Run with: streamlit run monitoring_dashboard.py
"""

import os
import streamlit as st
from pymongo import MongoClient
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

st.set_page_config(
    page_title="Pipeline Monitor",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --bg: #ffffff;
    --bg-soft: #f8f9fc;
    --bg-card: #ffffff;
    --border: #e4e7ef;
    --border-soft: #eef0f6;
    --text: #0f1117;
    --text-2: #4a5068;
    --text-3: #8b91a8;
    --blue: #3b6ef8;
    --blue-light: #eff3ff;
    --blue-mid: #c7d4fd;
    --pink: #e8458b;
    --pink-light: #fdf0f6;
    --pink-mid: #f8c0d8;
    --yellow: #f5a623;
    --yellow-light: #fff8ec;
    --green: #1a9e6b;
    --green-light: #edfaf4;
    --red: #e53e3e;
    --red-light: #fff5f5;
}

*, *::before, *::after { box-sizing: border-box; }

html, body, [class*="css"], .stApp {
    background: var(--bg-soft) !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    color: var(--text) !important;
}

.block-container {
    padding: 2rem 2.5rem 3rem !important;
    max-width: 1440px !important;
}

/* ── Header ── */
.page-header {
    display: flex;
    align-items: baseline;
    gap: 1rem;
    padding-bottom: 1.5rem;
    border-bottom: 2px solid var(--border);
    margin-bottom: 2rem;
}
.page-title {
    font-size: 1.6rem;
    font-weight: 700;
    color: var(--text);
    letter-spacing: -0.03em;
}
.page-pill {
    background: var(--blue-light);
    color: var(--blue);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.6rem;
    font-weight: 500;
    padding: 0.2rem 0.6rem;
    border-radius: 20px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

/* ── Section headers ── */
.sec-header {
    font-size: 0.65rem;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-3);
    margin: 2rem 0 0.9rem 0;
}

/* ── Stat cards ── */
.stat-row { display: flex; gap: 1rem; margin-bottom: 0.5rem; }
.stat-card {
    flex: 1;
    background: var(--bg-card);
    border: 1.5px solid var(--border);
    border-radius: 12px;
    padding: 1.25rem 1.4rem;
    position: relative;
    overflow: hidden;
}
.stat-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 12px 12px 0 0;
}
.stat-card.blue::before { background: var(--blue); }
.stat-card.pink::before { background: var(--pink); }
.stat-card.yellow::before { background: var(--yellow); }
.stat-card.green::before { background: var(--green); }
.stat-card.gray::before { background: var(--border); }

.stat-label {
    font-size: 0.65rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-3);
    margin-bottom: 0.4rem;
}
.stat-num {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.8rem;
    font-weight: 500;
    color: var(--text);
    line-height: 1;
    letter-spacing: -0.02em;
}
.stat-meta {
    font-size: 0.68rem;
    color: var(--text-3);
    margin-top: 0.45rem;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}

/* ── Badges ── */
.badge {
    display: inline-flex;
    align-items: center;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.58rem;
    font-weight: 500;
    letter-spacing: 0.05em;
    padding: 0.18rem 0.55rem;
    border-radius: 20px;
    white-space: nowrap;
}
.badge-live  { background: var(--green-light);  color: var(--green); }
.badge-empty { background: var(--bg-soft);      color: var(--text-3); border: 1px solid var(--border); }
.badge-ok    { background: var(--green-light);  color: var(--green); }
.badge-warn  { background: var(--yellow-light); color: var(--yellow); }
.badge-error { background: var(--red-light);    color: var(--red); }

/* ── Pipeline flow ── */
.flow-bar {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    flex-wrap: wrap;
    background: var(--bg-card);
    border: 1.5px solid var(--border);
    border-radius: 10px;
    padding: 0.9rem 1.2rem;
    margin-bottom: 1.5rem;
}
.flow-node {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem;
    color: var(--text-2);
    background: var(--bg-soft);
    border: 1px solid var(--border);
    padding: 0.22rem 0.65rem;
    border-radius: 5px;
}
.flow-arrow { color: var(--text-3); font-size: 0.8rem; line-height: 1; }

/* ── Consistency cards ── */
.check-card {
    background: var(--bg-card);
    border: 1.5px solid var(--border);
    border-radius: 10px;
    padding: 1rem 1.2rem;
}
.check-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem;
    color: var(--text-3);
    margin-bottom: 0.5rem;
}

/* ── Tabs ── */
div[data-testid="stTabs"] > div:first-child {
    background: var(--bg-card);
    border: 1.5px solid var(--border);
    border-bottom: none;
    border-radius: 10px 10px 0 0;
    padding: 0 0.5rem;
    gap: 0;
}
div[data-testid="stTabs"] button {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
    color: var(--text-3) !important;
    padding: 0.85rem 1.2rem !important;
    border-radius: 0 !important;
    border-bottom: 2px solid transparent !important;
    transition: color 0.15s !important;
}
div[data-testid="stTabs"] button[aria-selected="true"] {
    color: var(--blue) !important;
    border-bottom: 2px solid var(--blue) !important;
    background: transparent !important;
}
div[data-testid="stTabContent"] {
    background: var(--bg-card);
    border: 1.5px solid var(--border);
    border-top: none;
    border-radius: 0 0 10px 10px;
    padding: 2rem 2rem;
}

/* ── Inner tabs (collection explorer) ── */
div[data-testid="stTabContent"] div[data-testid="stTabs"] > div:first-child {
    background: var(--bg-soft);
    border: 1px solid var(--border-soft);
    border-radius: 8px 8px 0 0;
}
div[data-testid="stTabContent"] div[data-testid="stTabs"] button {
    font-size: 0.67rem !important;
    padding: 0.6rem 1rem !important;
}
div[data-testid="stTabContent"] div[data-testid="stTabContent"] {
    background: var(--bg-soft);
    border: 1px solid var(--border-soft);
    border-top: none;
    border-radius: 0 0 8px 8px;
    padding: 1.5rem;
}

/* ── Dataframe ── */
.stDataFrame { border-radius: 8px !important; overflow: hidden !important; }
.stDataFrame thead th {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.62rem !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    background: var(--bg-soft) !important;
    color: var(--text-3) !important;
}
.stDataFrame tbody td {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.72rem !important;
}

/* Misc */
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none !important; }
</style>
""", unsafe_allow_html=True)


# ── HELPERS ───────────────────────────────────────────────────────────────────

@st.cache_resource
def get_db():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return client[DB_NAME]


@st.cache_data(ttl=60)
def get_stats(collection_name):
    db = get_db()
    try:
        coll = db[collection_name]
        total = coll.count_documents({})
        by_run = list(coll.aggregate([
            {"$group": {"_id": "$run_id", "count": {"$sum": 1}}},
            {"$sort": {"_id": -1}}
        ]))
        n_runs = len([r for r in by_run if r["_id"]])
        return total, by_run, n_runs
    except:
        return 0, [], 0


def stat_card(label, value, meta="", badge="", color="blue"):
    badge_html = f'<span class="badge badge-{badge.lower()}">{badge}</span>' if badge else ""
    val_str = f"{value:,}" if isinstance(value, int) else str(value)
    st.markdown(f"""
    <div class="stat-card {color}">
        <div class="stat-label">{label}</div>
        <div class="stat-num">{val_str}</div>
        <div class="stat-meta">{meta} {badge_html}</div>
    </div>""", unsafe_allow_html=True)


def collection_detail(coll_name, desc=""):
    total, by_run, n_runs = get_stats(coll_name)
    avg = round(total / n_runs, 1) if n_runs > 0 else 0

    c1, c2, c3 = st.columns(3)
    with c1:
        stat_card("Total Documents", total,
                  badge="LIVE" if total > 0 else "EMPTY",
                  badge_class="live" if total > 0 else "empty",
                  color="blue" if total > 0 else "gray")
    with c2:
        stat_card("Unique Run IDs", n_runs, color="pink")
    with c3:
        stat_card("Avg Docs / Run", avg, color="yellow")

    if desc:
        st.markdown(f'<p style="font-size:0.72rem; color: var(--text-3); margin: 0.8rem 0 1rem 0; font-family: Plus Jakarta Sans, sans-serif;">{desc}</p>', unsafe_allow_html=True)

    if by_run:
        st.markdown('<p class="sec-header" style="margin-top:1.2rem">By Run ID</p>', unsafe_allow_html=True)
        df = pd.DataFrame(by_run).rename(columns={"_id": "run_id", "count": "documents"})
        df = df[df["run_id"].notna()].reset_index(drop=True)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No documents found in this collection.")


# fix the stat_card badge_class kwarg issue
def stat_card(label, value, meta="", badge="", badge_class="live", color="blue"):
    badge_html = f'<span class="badge badge-{badge_class}">{badge}</span>' if badge else ""
    val_str = f"{value:,}" if isinstance(value, int) else str(value)
    st.markdown(f"""
    <div class="stat-card {color}">
        <div class="stat-label">{label}</div>
        <div class="stat-num">{val_str}</div>
        <div class="stat-meta">{meta}&nbsp;{badge_html}</div>
    </div>""", unsafe_allow_html=True)


def collection_detail(coll_name, desc=""):
    total, by_run, n_runs = get_stats(coll_name)
    avg = round(total / n_runs, 1) if n_runs > 0 else 0

    c1, c2, c3 = st.columns(3)
    with c1:
        stat_card("Total Documents", total,
                  badge="LIVE" if total > 0 else "EMPTY",
                  badge_class="live" if total > 0 else "empty",
                  color="blue" if total > 0 else "gray")
    with c2:
        stat_card("Unique Run IDs", n_runs, color="pink")
    with c3:
        stat_card("Avg Docs / Run", avg, color="yellow")

    if desc:
        st.markdown(f'<p style="font-size:0.72rem; color:#8b91a8; margin: 0.8rem 0 1rem 0;">{desc}</p>', unsafe_allow_html=True)

    if by_run:
        st.markdown('<p class="sec-header" style="margin-top:1.2rem">By Run ID</p>', unsafe_allow_html=True)
        df = pd.DataFrame(by_run).rename(columns={"_id": "run_id", "count": "documents"})
        df = df[df["run_id"].notna()].reset_index(drop=True)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No documents found.")


# ── APP ───────────────────────────────────────────────────────────────────────

try:
    db = get_db()
    db.command("ping")
except Exception as e:
    st.error(f"MongoDB connection failed: {e}")
    st.stop()

# Header
st.markdown("""
<div class="page-header">
    <span class="page-title">🛰️ Pipeline Monitor</span>
    <span class="page-pill">City Sentiment Pipeline · Internal</span>
</div>
""", unsafe_allow_html=True)

# ── TOP-LEVEL TABS ────────────────────────────────────────────────────────────
tab_reddit, tab_news = st.tabs(["📡  Reddit Pipeline", "📰  News Pipeline"])

# ══════════════════════════════════════════════════════════════════════════════
# REDDIT
# ══════════════════════════════════════════════════════════════════════════════
with tab_reddit:

    # Flow
    st.markdown("""
    <div class="flow-bar">
        <span class="flow-node">r01_reddit_posts_raw_final</span><span class="flow-arrow">→</span>
        <span class="flow-node">reddit_relevant</span><span class="flow-arrow">→</span>
        <span class="flow-node">reddit_comments_final</span><span class="flow-arrow">→</span>
        <span class="flow-node">reddit_comments_relevant</span><span class="flow-arrow">→</span>
        <span class="flow-node">reddit_aggregated</span><span class="flow-arrow">→</span>
        <span class="flow-node">reddit_cleaned</span>
    </div>
    """, unsafe_allow_html=True)

    # Overview stats
    st.markdown('<p class="sec-header">Overview</p>', unsafe_allow_html=True)

    REDDIT = {
        "r01_reddit_posts_raw_final": ("Posts", "blue"),
        "reddit_relevant":            ("Rel. Posts", "blue"),
        "reddit_comments_final":      ("Comments", "pink"),
        "reddit_comments_relevant":   ("Rel. Comments", "pink"),
        "reddit_aggregated":          ("Aggregated", "yellow"),
        "reddit_cleaned":             ("Cleaned", "green"),
    }

    cols = st.columns(len(REDDIT))
    for i, (coll, (label, color)) in enumerate(REDDIT.items()):
        total, _, n_runs = get_stats(coll)
        with cols[i]:
            stat_card(label, total,
                      meta=f"{n_runs} run IDs",
                      badge="LIVE" if total > 0 else "EMPTY",
                      badge_class="live" if total > 0 else "empty",
                      color=color)

    # Consistency
    st.markdown('<p class="sec-header">Run ID Consistency</p>', unsafe_allow_html=True)

    r01 = set(db["r01_reddit_posts_raw_final"].distinct("run_id"))
    r02 = set(db["reddit_relevant"].distinct("run_id"))
    r03 = set(db["reddit_comments_final"].distinct("run_id"))
    r04 = set(db["reddit_comments_relevant"].distinct("run_id"))
    r05 = set(db["reddit_aggregated"].distinct("run_id"))

    checks = [("R01 → R02", r01 - r02), ("R02 → R03", r02 - r03),
              ("R03 → R04", r03 - r04), ("R04 → R05", r04 - r05)]

    for col, (label, missing) in zip(st.columns(4), checks):
        with col:
            if not missing:
                st.markdown(f"""
                <div class="check-card">
                    <div class="check-label">{label}</div>
                    <span class="badge badge-ok">✓ Consistent</span>
                </div>""", unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="check-card">
                    <div class="check-label">{label}</div>
                    <span class="badge badge-warn">⚠ {len(missing)} missing</span>
                    <div style="font-size:0.62rem; color:#f5a623; margin-top:0.4rem; font-family: JetBrains Mono, monospace;">{', '.join(sorted(missing))}</div>
                </div>""", unsafe_allow_html=True)

    # Collection explorer
    st.markdown('<p class="sec-header">Collection Explorer</p>', unsafe_allow_html=True)

    REDDIT_DESC = {
        "r01_reddit_posts_raw_final": "Raw r/travel posts fetched daily (n-2 date). Filtered by location mention in title.",
        "reddit_relevant":            "Posts that passed LLM relevance filter (R02). Contains aspect-level sentiment analysis.",
        "reddit_comments_final":      "Top 20 comments fetched per relevant post (R03).",
        "reddit_comments_relevant":   "Comments that passed LLM relevance + scoring (R04).",
        "reddit_aggregated":          "Aspect-level records aggregated from posts and comments (R05).",
        "reddit_cleaned":             "Cleaned aggregated data. Run IDs to be assigned.",
    }

    sub_labels = ["Raw Posts", "Rel. Posts", "Comments", "Rel. Comments", "Aggregated", "Cleaned"]
    sub_tabs = st.tabs(sub_labels)
    for tab, coll in zip(sub_tabs, REDDIT.keys()):
        with tab:
            collection_detail(coll, REDDIT_DESC.get(coll, ""))


# ══════════════════════════════════════════════════════════════════════════════
# NEWS
# ══════════════════════════════════════════════════════════════════════════════
with tab_news:

    st.markdown("""
    <div class="flow-bar">
        <span class="flow-node">raw_documents_historical</span>
        <span class="flow-arrow">→</span>
        <span class="flow-node">news_alert</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<p class="sec-header">Overview</p>', unsafe_allow_html=True)

    NEWS = {
        "raw_documents_historical": ("Raw News", "blue"),
        "news_alert":               ("News Alerts", "pink"),
    }

    news_cols = st.columns(2)
    for col, (coll, (label, color)) in zip(news_cols, NEWS.items()):
        total, _, n_runs = get_stats(coll)
        with col:
            stat_card(label, total,
                      meta=f"{n_runs} run IDs",
                      badge="LIVE" if total > 0 else "EMPTY",
                      badge_class="live" if total > 0 else "empty",
                      color=color)

    st.markdown('<p class="sec-header">Collection Explorer</p>', unsafe_allow_html=True)

    NEWS_DESC = {
        "raw_documents_historical": "Historical news articles ingested from NewsAPI.",
        "news_alert":               "News documents that triggered the alert system.",
    }

    news_sub = st.tabs(["Raw News", "News Alerts"])
    for tab, coll in zip(news_sub, NEWS.keys()):
        with tab:
            collection_detail(coll, NEWS_DESC.get(coll, ""))