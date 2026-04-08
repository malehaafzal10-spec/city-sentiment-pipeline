"""
app.py — City Sentiment Monitor dashboard.
Fully integrated with MongoDB.
Run: streamlit run app.py
"""

import os
import pandas as pd
import streamlit as st
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

CITY_FEATURES_COLLECTION = "city_weekly_features"
ALERTS_COLLECTION = "monitoring_alerts"
JUDGE_COLLECTION = "llm_judge_results"
VALIDATION_COLLECTION = "validation_samples"

st.set_page_config(
    page_title="City Sentiment Monitor",
    layout="wide",
    initial_sidebar_state="collapsed"
)

CITY_IMAGES = {
    "Paris": "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?w=400&h=200&fit=crop",
    "Rome": "https://images.unsplash.com/photo-1552832230-c0197dd311b5?w=400&h=200&fit=crop",
    "Barcelona": "https://images.unsplash.com/photo-1583422409516-2895a77efded?w=400&h=200&fit=crop",
    "Lisbon": "https://images.unsplash.com/photo-1548707309-dcebeab9ea9b?w=400&h=200&fit=crop",
    "Amsterdam": "https://images.unsplash.com/photo-1534351590666-13e3e96b5017?w=400&h=200&fit=crop",
    "Prague": "https://images.unsplash.com/photo-1592906209472-a36b1f3782ef?w=400&h=200&fit=crop",
    "Athens": "https://images.unsplash.com/photo-1555993539-1732b0258235?w=400&h=200&fit=crop",
    "London": "https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?w=400&h=200&fit=crop",
}

st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background-color: #f5f5f0 !important;
}
.block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 1280px; }
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stToolbar"] { display: none; }
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e8e8e3;
    border-radius: 10px;
    padding: 1rem 1.2rem;
}
[data-testid="stMetricLabel"] p {
    font-size: 0.72rem !important;
    color: #999 !important;
    text-transform: uppercase;
    letter-spacing: 0.6px;
}
[data-testid="stMetricValue"] {
    font-size: 1.4rem !important;
    font-weight: 700 !important;
    color: #111 !important;
}
.city-card {
    background: #ffffff;
    border-radius: 12px;
    border: 1px solid #e8e8e3;
    overflow: hidden;
    margin-bottom: 16px;
}
.city-card-alert {
    background: #ffffff;
    border-radius: 12px;
    border: 1px solid #e8e8e3;
    border-left: 4px solid #d97706;
    overflow: hidden;
    margin-bottom: 16px;
}
.card-body { padding: 14px 16px 16px; }
.card-city-name { font-size: 1rem; font-weight: 700; color: #111; margin: 0 0 4px 0; }
.card-score-row { display: flex; align-items: baseline; gap: 6px; margin-bottom: 2px; }
.card-score { font-size: 1.9rem; font-weight: 800; line-height: 1; }
.score-pos { color: #16a34a; }
.score-neg { color: #dc2626; }
.score-mix { color: #d97706; }
.card-label { font-size: 0.78rem; font-weight: 600; }
.card-change { font-size: 0.75rem; margin-bottom: 10px; }
.change-up { color: #16a34a; }
.change-down { color: #dc2626; }
.change-flat { color: #999; }
.card-stats {
    display: flex;
    gap: 0;
    border-top: 1px solid #f0f0ec;
    border-bottom: 1px solid #f0f0ec;
    padding: 8px 0;
    margin-bottom: 10px;
}
.card-stat { flex: 1; display: flex; flex-direction: column; align-items: center; }
.card-stat-label { font-size: 0.65rem; color: #bbb; text-transform: uppercase; letter-spacing: 0.4px; }
.card-stat-val { font-size: 0.9rem; font-weight: 600; color: #333; }
.dim-row { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }
.dim-lbl { font-size: 0.7rem; color: #999; width: 42px; }
.dim-track { flex: 1; height: 3px; background: #f0f0ec; border-radius: 2px; overflow: hidden; }
.dim-fill { height: 100%; border-radius: 2px; }
.alert-tag {
    display: inline-block;
    font-size: 0.65rem;
    font-weight: 600;
    padding: 1px 7px;
    border-radius: 8px;
    background: #fef3c7;
    color: #92400e;
    margin-left: 5px;
    vertical-align: middle;
}
.alert-box {
    font-size: 0.73rem;
    color: #92400e;
    background: #fffbeb;
    border: 1px solid #fde68a;
    border-radius: 5px;
    padding: 5px 9px;
    margin-top: 6px;
    line-height: 1.5;
}
.recommendation-yes {
    font-size: 0.75rem; color: #14532d; background: #f0fdf4; border: 1px solid #bbf7d0;
    border-radius: 5px; padding: 6px 10px; margin-top: 8px; line-height: 1.5;
}
.recommendation-no {
    font-size: 0.75rem; color: #7f1d1d; background: #fef2f2; border: 1px solid #fecaca;
    border-radius: 5px; padding: 6px 10px; margin-top: 8px; line-height: 1.5;
}
.recommendation-maybe {
    font-size: 0.75rem; color: #78350f; background: #fffbeb; border: 1px solid #fde68a;
    border-radius: 5px; padding: 6px 10px; margin-top: 8px; line-height: 1.5;
}
.section-title {
    font-size: 0.85rem; font-weight: 600; color: #999; text-transform: uppercase;
    letter-spacing: 0.8px; margin: 1.8rem 0 1rem; padding-bottom: 0.5rem;
    border-bottom: 1px solid #e8e8e3;
}
.alert-row {
    padding: 9px 14px; border-radius: 6px; margin-bottom: 6px; font-size: 0.82rem; line-height: 1.5;
}
.alert-high { background: #fef2f2; border-left: 3px solid #dc2626; }
.alert-medium { background: #fffbeb; border-left: 3px solid #d97706; }
.alert-low { background: #f0fdf4; border-left: 3px solid #16a34a; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def load_data():
    if not MONGO_URI:
        st.error("MONGO_URI not found in environment.")
        return None, None, None, None

    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]

        # 1. Get latest week
        latest = db[CITY_FEATURES_COLLECTION].find_one(sort=[("week_start", -1)])
        if not latest:
            return None, None, None, None

        week = latest["week_start"]

        # 2. Get metrics for latest week
        metrics_cursor = db[CITY_FEATURES_COLLECTION].find({"week_start": week}).sort("avg_sentiment", -1)
        metrics = pd.DataFrame(list(metrics_cursor))

        # 3. Get alerts for latest week
        alerts_cursor = db[ALERTS_COLLECTION].find({"week_start": week})
        alerts = pd.DataFrame(list(alerts_cursor))

        # 4. Get full history for charts
        history_cursor = db[CITY_FEATURES_COLLECTION].find(
            {}, {"city": 1, "week_start": 1, "avg_sentiment": 1}
        ).sort("week_start", 1)
        history = pd.DataFrame(list(history_cursor))

        # 5. Get previous week's metrics
        prev_row = db[CITY_FEATURES_COLLECTION].find_one(
            {"week_start": {"$lt": week}}, sort=[("week_start", -1)]
        )
        prev_metrics = {}
        if prev_row:
            prev_week = prev_row["week_start"]
            prev_cursor = db[CITY_FEATURES_COLLECTION].find({"week_start": prev_week})
            prev_metrics = {r["city"]: r.get("avg_sentiment", 0.0) for r in prev_cursor}

        client.close()
        return metrics, alerts, history, prev_metrics
    except Exception as e:
        st.error(f"Could not load data from MongoDB: {e}")
        return None, None, None, None


@st.cache_data(ttl=3600)
def get_visit_recommendation(city: str, avg_sentiment: float, crowding_score: float,
                             cost_score: float, positive_ratio: float,
                             negative_ratio: float, mention_count: int) -> dict:
    GROQ_KEY = os.getenv("GROQ_API_KEY", "")
    if not GROQ_KEY:
        return {"recommendation": "", "verdict": "maybe"}

    try:
        from groq import Groq
        client = Groq(api_key=GROQ_KEY)

        prompt = f"""You are a travel advisor giving honest advice.

Based on this week's traveller sentiment data for {city}:
- Overall sentiment score: {avg_sentiment:+.2f} (range: -1 to +1)
- Positive mentions: {positive_ratio:.0%}
- Negative mentions: {negative_ratio:.0%}
- Crowding complaints level: {crowding_score:.2f} (0=none, 1=high)
- Cost complaints level: {cost_score:.2f} (0=none, 1=high)
- Based on {mention_count} traveller mentions

Write ONE short honest sentence (max 20 words) saying whether travellers should visit {city} this week and the main reason why.
Start with either "Yes —", "No —", or "Maybe —"
Reply with only that one sentence, nothing else."""

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",  # <--- UPDATED MODEL
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0.3
        )

        text = response.choices[0].message.content.strip()
        verdict = "yes" if text.lower().startswith("yes") else "no" if text.lower().startswith("no") else "maybe"
        return {"recommendation": text, "verdict": verdict}

    except Exception as e:
        return {"recommendation": "", "verdict": "maybe"}


def score_css(score):
    if score >= 0.15: return "score-pos"
    if score <= -0.05: return "score-neg"
    return "score-mix"

def sentiment_label(score):
    if score >= 0.15: return "Positive"
    if score <= -0.05: return "Negative"
    return "Mixed"

def change_html(current, prev):
    if prev is None:
        return '<span class="card-change change-flat">First week of data</span>'
    diff = current - prev
    if diff > 0.05:
        return f'<span class="card-change change-up">+{diff:.2f} vs last week</span>'
    if diff < -0.05:
        return f'<span class="card-change change-down">{diff:.2f} vs last week</span>'
    return '<span class="card-change change-flat">Stable vs last week</span>'

def dim_bar_html(label, value, color):
    pct = min(float(value) * 250, 100)
    return f"""<div class="dim-row">
        <span class="dim-lbl">{label}</span>
        <div class="dim-track"><div class="dim-fill" style="width:{pct:.0f}%;background:{color}"></div></div>
    </div>"""

def format_alert_message(message: str) -> str:
    import re
    match = re.search(r"dropped ([\d.]+) \(([+\-\d.]+) → ([+\-\d.]+)\)", message)
    if match: return f"Sentiment dropped sharply this week ({match.group(2)} → {match.group(3)})."
    match = re.search(r"Only (\d+) mentions", message)
    if match: return f"Only {match.group(1)} traveller mentions this week — low confidence."
    if "deviates" in message.lower() or "rolling" in message.lower(): return "Unusual deviation from 4-week average."
    return message


# ─── MAIN UI ──────────────────────────────────────────────────────────────────

metrics, alerts, history, prev_metrics = load_data()

h1, h2 = st.columns([5, 1])
with h1:
    st.markdown("## City Sentiment Monitor")
    st.caption("Tracking how travellers talk about European cities — powered by MongoDB")
with h2:
    st.write("")
    if st.button("Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

if metrics is None or metrics.empty:
    st.info("No data yet — run the pipeline to populate MongoDB.")
    st.stop()

week_start = metrics["week_start"].iloc[0]
st.caption(f"Week of {week_start}")
st.divider()

# ─── SUMMARY ──────────────────────────────────────────────────────────────────

c1, c2, c3, c4 = st.columns(4)
c1.metric("Overall sentiment", f"{metrics['avg_sentiment'].mean():+.2f}")
c2.metric("Total mentions", f"{int(metrics['mention_count'].sum()):,}")
c3.metric("Positive cities", f"{len(metrics[metrics['avg_sentiment'] >= 0.15])} / {len(metrics)}")
c4.metric("Active alerts", str(len(alerts) if alerts is not None else 0))

# ─── CARDS ────────────────────────────────────────────────────────────────────

st.markdown('<div class="section-title">City breakdown</div>', unsafe_allow_html=True)

alerts_by_city = {}
if alerts is not None and not alerts.empty:
    for _, row in alerts.iterrows():
        alerts_by_city.setdefault(row["city"], []).append(row)

cols = st.columns(4)
for i, (_, row) in enumerate(metrics.iterrows()):
    city = row["city"]
    score = float(row.get("avg_sentiment", 0.0))
    prev = prev_metrics.get(city)
    city_alerts = alerts_by_city.get(city, [])
    img_url = CITY_IMAGES.get(city, "")

    alert_tag = '<span class="alert-tag">Alert</span>' if city_alerts else ""
    alert_html = "".join(f'<div class="alert-box">{format_alert_message(str(a.get("alert_message","")))}</div>' for a in city_alerts)
    card_class = "city-card-alert" if city_alerts else "city-card"

    dims = (
        dim_bar_html("Crowds", row.get("crowding_score", 0), "#ef4444") +
        dim_bar_html("Cost", row.get("cost_score", 0), "#f59e0b") +
        dim_bar_html("Safety", row.get("safety_score", 0), "#22c55e")
    )

    rec = get_visit_recommendation(
        city=city, avg_sentiment=score, crowding_score=float(row.get("crowding_score", 0)),
        cost_score=float(row.get("cost_score", 0)), positive_ratio=float(row.get("positive_ratio", 0)),
        negative_ratio=float(row.get("negative_ratio", 0)), mention_count=int(row.get("mention_count", 0))
    )

    rec_html = f'<div class="recommendation-{rec["verdict"]}">{rec["recommendation"]}</div>' if rec["recommendation"] else ""

    with cols[i % 4]:
        st.markdown(f"""
<div class="{card_class}">
  <img src="{img_url}" style="width:100%;height:130px;object-fit:cover;display:block">
  <div class="card-body">
    <p class="card-city-name">{city}{alert_tag}</p>
    <div class="card-score-row">
      <span class="card-score {score_css(score)}">{score:+.2f}</span>
      <span class="card-label {score_css(score)}">{sentiment_label(score)}</span>
    </div>
    {change_html(score, prev)}
    <div class="card-stats">
      <div class="card-stat">
        <span class="card-stat-label">Mentions</span>
        <span class="card-stat-val">{int(row.get('mention_count', 0))}</span>
      </div>
      <div class="card-stat">
        <span class="card-stat-label">Positive</span>
        <span class="card-stat-val">{row.get('positive_ratio', 0):.0%}</span>
      </div>
      <div class="card-stat">
        <span class="card-stat-label">Negative</span>
        <span class="card-stat-val">{row.get('negative_ratio', 0):.0%}</span>
      </div>
    </div>
    {dims}
    {rec_html}
    {alert_html}
  </div>
</div>
""", unsafe_allow_html=True)

# ─── TRENDS & ALERTS ──────────────────────────────────────────────────────────

st.markdown('<div class="section-title">Sentiment trends over time</div>', unsafe_allow_html=True)
if history is not None and not history.empty:
    pivot = history.pivot_table(index="week_start", columns="city", values="avg_sentiment")
    selected = st.multiselect("Cities", options=pivot.columns.tolist(), default=pivot.columns.tolist(), label_visibility="collapsed")
    if selected:
        st.line_chart(pivot[selected], height=300, use_container_width=True)

st.markdown('<div class="section-title">Monitoring alerts</div>', unsafe_allow_html=True)
if alerts is not None and not alerts.empty:
    for _, alert in alerts.iterrows():
        st.markdown(f'<div class="alert-row alert-{alert.get("severity", "medium")}"><strong>{alert.get("city", "")}</strong> — {format_alert_message(str(alert.get("alert_message", "")))}</div>', unsafe_allow_html=True)
else:
    st.markdown('<p style="font-size:0.85rem;color:#999;padding:8px 0">No alerts this week.</p>', unsafe_allow_html=True)

# ─── VALIDATION TAB ───────────────────────────────────────────────────────────

st.write("")
st.markdown('<div class="section-title">Model evaluation & human review</div>', unsafe_allow_html=True)
tab1, tab2 = st.tabs(["LLM Judge results", "Human review queue"])

with tab1:
    st.markdown("#### VADER vs LLM agreement this week")
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        
        # MongoDB Aggregation to replicate the complex GROUP BY SQL query
        pipeline = [
            {"$match": {"week_start": week_start}},
            {"$group": {
                "_id": "$city",
                "total_judged": {"$sum": 1},
                "agreed": {"$sum": "$agreement"},
                "agreement_pct": {"$avg": "$agreement"}
            }},
            {"$sort": {"agreement_pct": 1}}
        ]
        
        judge_results = list(db[JUDGE_COLLECTION].aggregate(pipeline))
        client.close()

        if not judge_results:
            st.info("No LLM Judge results yet. Run step 06 (llm_judge).")
        else:
            for row in judge_results:
                city = row["_id"]
                pct = row["agreement_pct"] * 100
                color = "#16a34a" if pct >= 70 else "#d97706" if pct >= 50 else "#dc2626"
                confidence = "High confidence" if pct >= 70 else "Medium confidence" if pct >= 50 else "Low confidence"
                st.markdown(f"""
                <div style="display:flex;justify-content:space-between;align-items:center;
                            padding:10px 14px;border-radius:6px;margin-bottom:6px;
                            background:#fafafa;border:1px solid #efefef">
                    <span style="font-weight:600;font-size:0.9rem">{city}</span>
                    <span style="font-size:0.8rem;color:#999">{row['agreed']}/{row['total_judged']} agreed</span>
                    <span style="font-weight:600;color:{color};font-size:0.9rem">{pct:.0f}% — {confidence}</span>
                </div>
                """, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Could not load judge results: {e}")

with tab2:
    st.markdown("#### Articles flagged for human review")
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        
        samples_cursor = db[VALIDATION_COLLECTION].find({"needs_review": True}).limit(20)
        samples = list(samples_cursor)
        
        if not samples:
            st.success("No articles need review right now!")
        else:
            st.info(f"{len(samples)} articles need review")

            for row in samples:
                doc_id = row.get("doc_id", str(row["_id"]))
                with st.expander(f"{row.get('city')} — VADER: {row.get('vader_label')} ({row.get('vader_score', 0):+.2f}) | LLM: {row.get('llm_label')}"):
                    st.write(row.get("clean_text", "")[:400])
                    st.caption("VADER and LLM disagreed. What is the correct label?")

                    col1, col2, col3, col4 = st.columns(4)
                    
                    def update_label(doc_id, vader_lbl, human_lbl):
                        c = MongoClient(MONGO_URI)
                        c[DB_NAME][VALIDATION_COLLECTION].update_one(
                            {"doc_id": doc_id}, 
                            {"$set": {"human_label": human_lbl, "needs_review": False}}
                        )
                        c.close()
                    
                    if col1.button("Positive", key=f"pos_{doc_id}"):
                        update_label(doc_id, row.get('vader_label'), "positive")
                        st.rerun()
                    if col2.button("Negative", key=f"neg_{doc_id}"):
                        update_label(doc_id, row.get('vader_label'), "negative")
                        st.rerun()
                    if col3.button("Neutral", key=f"neu_{doc_id}"):
                        update_label(doc_id, row.get('vader_label'), "neutral")
                        st.rerun()
                    if col4.button("Skip", key=f"skip_{doc_id}"):
                        update_label(doc_id, row.get('vader_label'), None)
                        st.rerun()

        # VADER Accuracy Chart (Aggregated from MongoDB)
        st.markdown("#### VADER accuracy from human reviews")
        acc_pipeline = [
            {"$match": {"human_label": {"$in": ["positive", "negative", "neutral"]}}},
            {"$group": {
                "_id": "$week_start",
                "total_reviewed": {"$sum": 1},
                "correct_count": {"$sum": {"$cond": [{"$eq": ["$human_label", "$vader_label"]}, 1, 0]}}
            }},
            {"$sort": {"_id": 1}}
        ]
        acc_results = list(db[VALIDATION_COLLECTION].aggregate(acc_pipeline))
        client.close()

        if not acc_results:
            st.info("No accuracy data yet — review some articles above first.")
        else:
            acc_df = pd.DataFrame(acc_results)
            acc_df["accuracy_pct"] = (acc_df["correct_count"] / acc_df["total_reviewed"]) * 100
            
            c1, c2, c3 = st.columns(3)
            latest = acc_df.iloc[-1]
            c1.metric("Latest accuracy", f"{latest['accuracy_pct']:.1f}%")
            c2.metric("Articles reviewed", int(latest["total_reviewed"]))
            c3.metric("Correct predictions", int(latest["correct_count"]))
            
            if len(acc_df) > 1:
                acc_df.rename(columns={"_id": "week_start"}, inplace=True)
                st.line_chart(acc_df.set_index("week_start")["accuracy_pct"], height=200)

    except Exception as e:
        st.error(f"Could not load validation samples: {e}")

st.divider()
st.caption(f"City Sentiment Monitor · Week of {week_start} · MLOps Pipeline · MongoDB Powered")