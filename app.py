"""
app.py — City Sentiment Monitor dashboard.
Clean light design, clickable star feedback, MongoDB.
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
FEEDBACK_COLLECTION = "user_feedback"

st.set_page_config(
    page_title="City Sentiment Monitor",
    layout="wide",
    initial_sidebar_state="collapsed"
)

CITY_INFO = {
    "Paris": {
        "image": "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?w=400&h=200&fit=crop",
        "best_time": "Apr–Jun, Sep–Oct",
        "avg_temp": "15°C / 59°F",
        "attractions": "Eiffel Tower, Louvre, Montmartre",
        "tips": "Book museums in advance. Avoid August — tourist crowds surge.",
        "accent": "#E74C3C",
    },
    "Rome": {
        "image": "https://images.unsplash.com/photo-1552832230-c0197dd311b5?w=400&h=200&fit=crop",
        "best_time": "Apr–May, Sep–Oct",
        "avg_temp": "20°C / 68°F",
        "attractions": "Colosseum, Vatican, Trevi Fountain",
        "tips": "Validate your bus ticket. Tap water from fountains is free.",
        "accent": "#E67E22",
    },
    "Barcelona": {
        "image": "https://images.unsplash.com/photo-1583422409516-2895a77efded?w=400&h=200&fit=crop",
        "best_time": "May–Jun, Sep–Oct",
        "avg_temp": "22°C / 72°F",
        "attractions": "Sagrada Família, Park Güell, La Boqueria",
        "tips": "Watch for pickpockets on Las Ramblas. Dinner starts at 9pm.",
        "accent": "#8E44AD",
    },
    "Lisbon": {
        "image": "https://images.unsplash.com/photo-1548707309-dcebeab9ea9b?w=400&h=200&fit=crop",
        "best_time": "Mar–May, Sep–Nov",
        "avg_temp": "18°C / 64°F",
        "attractions": "Belém Tower, Alfama district, Sintra day trip",
        "tips": "Tram 28 is scenic but crowded. Walking the hills is worth it.",
        "accent": "#16A085",
    },
    "Amsterdam": {
        "image": "https://images.unsplash.com/photo-1534351590666-13e3e96b5017?w=400&h=200&fit=crop",
        "best_time": "Apr–May (tulips), Jun–Aug",
        "avg_temp": "14°C / 57°F",
        "attractions": "Rijksmuseum, Anne Frank House, Canal cruise",
        "tips": "Rent a bike. Watch tram tracks. Book Anne Frank months ahead.",
        "accent": "#27AE60",
    },
    "Prague": {
        "image": "https://images.unsplash.com/photo-1592906209472-a36b1f3782ef?w=400&h=200&fit=crop",
        "best_time": "May–Sep",
        "avg_temp": "16°C / 61°F",
        "attractions": "Prague Castle, Old Town Square, Charles Bridge",
        "tips": "Very affordable. Avoid restaurants near the Astronomical Clock.",
        "accent": "#C0392B",
    },
    "Athens": {
        "image": "https://images.unsplash.com/photo-1555993539-1732b0258235?w=400&h=200&fit=crop",
        "best_time": "Apr–Jun, Sep–Oct",
        "avg_temp": "24°C / 75°F",
        "attractions": "Acropolis, Parthenon, Plaka district",
        "tips": "Visit Acropolis at opening time. Summer heat is intense.",
        "accent": "#F39C12",
    },
    "London": {
        "image": "https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?w=400&h=200&fit=crop",
        "best_time": "May–Sep",
        "avg_temp": "12°C / 54°F",
        "attractions": "British Museum, Tower of London, Hyde Park",
        "tips": "Get an Oyster card. Many world-class museums are free.",
        "accent": "#2980B9",
    },
}

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');

html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background-color: #f4f6fb !important;
    font-family: 'Plus Jakarta Sans', sans-serif;
}
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1400px; }
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }

/* Header */
.dash-header {
    background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
    border-radius: 20px;
    padding: 2.2rem 2.8rem;
    margin-bottom: 1.8rem;
    position: relative;
    overflow: hidden;
}
.dash-header::before {
    content: '';
    position: absolute;
    top: -60px; right: -60px;
    width: 300px; height: 300px;
    background: radial-gradient(circle, rgba(255,255,255,0.04) 0%, transparent 70%);
    pointer-events: none;
}
.dash-title { font-size: 2.1rem; font-weight: 800; color: #fff; margin: 0; letter-spacing: -0.5px; }
.dash-subtitle { color: rgba(255,255,255,0.45); font-size: 0.85rem; margin-top: 5px; }
.dash-week {
    display: inline-block;
    background: rgba(255,255,255,0.08);
    color: rgba(255,255,255,0.6);
    font-size: 0.65rem; font-weight: 700;
    padding: 3px 11px; border-radius: 20px;
    margin-top: 12px; letter-spacing: 1.2px;
    text-transform: uppercase;
    border: 1px solid rgba(255,255,255,0.12);
}

/* Metrics */
[data-testid="stMetric"] {
    background: #fff;
    border: 1px solid #e4e8f0;
    border-radius: 14px;
    padding: 1rem 1.3rem;
    box-shadow: 0 1px 6px rgba(0,0,0,0.04);
}
[data-testid="stMetricLabel"] p {
    font-size: 0.65rem !important; color: #9ca3b0 !important;
    text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600 !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.55rem !important; font-weight: 800 !important; color: #1a1a2e !important;
}

/* City cards */
.city-card {
    background: #fff; border-radius: 16px; border: 1px solid #e4e8f0;
    overflow: hidden; margin-bottom: 20px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.04);
    transition: box-shadow 0.2s;
}
.city-card:hover { box-shadow: 0 6px 24px rgba(0,0,0,0.09); }
.city-card-alert {
    background: #fff; border-radius: 16px;
    border: 1px solid #fcd34d; border-top: 4px solid #f59e0b;
    overflow: hidden; margin-bottom: 20px;
}
.card-img { width: 100%; height: 130px; object-fit: cover; display: block; }
.card-accent-bar { height: 3px; width: 100%; }
.card-body { padding: 14px 15px 15px; }
.card-city-name { font-size: 0.98rem; font-weight: 700; color: #1a1a2e; margin: 0 0 2px 0; }
.card-score-row { display: flex; align-items: baseline; gap: 7px; margin-bottom: 1px; }
.card-score { font-size: 1.8rem; font-weight: 800; line-height: 1; }
.score-pos { color: #059669; }
.score-neg { color: #DC2626; }
.score-mix { color: #D97706; }
.card-label { font-size: 0.7rem; font-weight: 700; }
.card-change { font-size: 0.7rem; margin-bottom: 9px; font-weight: 500; }
.change-up { color: #059669; }
.change-down { color: #DC2626; }
.change-flat { color: #9ca3b0; }
.card-stats {
    display: flex; border-top: 1px solid #f1f3f8;
    border-bottom: 1px solid #f1f3f8; padding: 7px 0; margin-bottom: 10px;
}
.card-stat { flex: 1; display: flex; flex-direction: column; align-items: center; }
.card-stat-label { font-size: 0.57rem; color: #b0b7c3; text-transform: uppercase; letter-spacing: 0.4px; }
.card-stat-val { font-size: 0.9rem; font-weight: 700; color: #1a1a2e; }
.dim-row { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }
.dim-lbl { font-size: 0.62rem; color: #9ca3b0; width: 44px; font-weight: 500; }
.dim-track { flex: 1; height: 3px; background: #f0f2f7; border-radius: 2px; overflow: hidden; }
.dim-fill { height: 100%; border-radius: 2px; }

/* City info */
.city-info-section { margin-top: 10px; padding-top: 9px; border-top: 1px solid #f1f3f8; }
.info-row { display: flex; gap: 10px; margin-bottom: 6px; }
.info-item { flex: 1; }
.info-label { font-size: 0.55rem; color: #b0b7c3; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; display: block; }
.info-val { font-size: 0.7rem; color: #4a5568; font-weight: 500; line-height: 1.3; }
.info-full { margin-bottom: 5px; }
.city-tip { font-size: 0.66rem; color: #6b7280; font-style: italic; line-height: 1.4; padding: 5px 8px; background: #f8f9fc; border-radius: 6px; border-left: 2px solid #d1d5e0; }

/* Alerts */
.alert-tag { display: inline-block; font-size: 0.57rem; font-weight: 700; padding: 1px 6px; border-radius: 7px; background: #fef3c7; color: #92400e; margin-left: 5px; vertical-align: middle; }
.alert-box { font-size: 0.68rem; color: #92400e; background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; padding: 5px 8px; margin-top: 6px; line-height: 1.5; }
.recommendation-yes { font-size: 0.69rem; color: #065f46; background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 6px; padding: 5px 9px; margin-top: 7px; line-height: 1.5; }
.recommendation-no { font-size: 0.69rem; color: #7f1d1d; background: #fef2f2; border: 1px solid #fecaca; border-radius: 6px; padding: 5px 9px; margin-top: 7px; line-height: 1.5; }
.recommendation-maybe { font-size: 0.69rem; color: #78350f; background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; padding: 5px 9px; margin-top: 7px; line-height: 1.5; }

/* Section titles */
.section-title { font-size: 0.7rem; font-weight: 700; color: #9ca3b0; text-transform: uppercase; letter-spacing: 1.5px; margin: 1.8rem 0 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid #e4e8f0; }
.alert-row { padding: 9px 14px; border-radius: 8px; margin-bottom: 6px; font-size: 0.8rem; line-height: 1.5; }
.alert-high { background: #fef2f2; border-left: 3px solid #DC2626; color: #7f1d1d; }
.alert-medium { background: #fffbeb; border-left: 3px solid #D97706; color: #78350f; }
.alert-low { background: #ecfdf5; border-left: 3px solid #059669; color: #065f46; }

/* Feedback */
.feedback-wrap {
    background: linear-gradient(135deg, #0f2027, #203a43);
    border-radius: 18px; padding: 2rem 2.5rem; margin-top: 0.5rem;
}
.feedback-title { font-size: 1.2rem; font-weight: 800; color: #fff; margin-bottom: 3px; }
.feedback-sub { color: rgba(255,255,255,0.4); font-size: 0.8rem; margin-bottom: 1.5rem; }

/* Star rating widget */
.stars-container { display: flex; gap: 6px; margin-bottom: 16px; }
.star-btn {
    font-size: 2rem; cursor: pointer; background: none;
    border: none; padding: 0; line-height: 1;
    transition: transform 0.1s; filter: grayscale(30%);
}
.star-btn:hover { transform: scale(1.2); }

/* Tabs */
.stTabs [data-baseweb="tab-list"] { gap: 6px; }
.stTabs [data-baseweb="tab"] {
    background: #eef0f5; border-radius: 10px; color: #6b7280;
    font-weight: 600; padding: 7px 15px; border: 1px solid #e4e8f0;
    font-family: 'Plus Jakarta Sans', sans-serif;
}
.stTabs [aria-selected="true"] { background: #0f2027 !important; color: #fff !important; border-color: #0f2027 !important; }

/* Text area in feedback */
.stTextArea textarea {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    color: #fff !important; border-radius: 10px !important;
}
.stTextArea textarea::placeholder { color: rgba(255,255,255,0.25) !important; }

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
    color: #fff !important; border: none !important; border-radius: 10px !important;
    font-weight: 700 !important; padding: 0.45rem 1.8rem !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
}
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
        latest = db[CITY_FEATURES_COLLECTION].find_one(sort=[("week_start", -1)])
        if not latest:
            return None, None, None, None
        week = latest["week_start"]
        metrics = pd.DataFrame(list(
            db[CITY_FEATURES_COLLECTION].find({"week_start": week}).sort("avg_sentiment", -1)
        ))
        alerts = pd.DataFrame(list(db[ALERTS_COLLECTION].find({"week_start": week})))
        history = pd.DataFrame(list(
            db[CITY_FEATURES_COLLECTION].find({}, {"city": 1, "week_start": 1, "avg_sentiment": 1}).sort("week_start", 1)
        ))
        prev_row = db[CITY_FEATURES_COLLECTION].find_one(
            {"week_start": {"$lt": week}}, sort=[("week_start", -1)]
        )
        prev_metrics = {}
        if prev_row:
            prev_week = prev_row["week_start"]
            prev_metrics = {r["city"]: r.get("avg_sentiment", 0.0) for r in db[CITY_FEATURES_COLLECTION].find({"week_start": prev_week})}
        client.close()
        return metrics, alerts, history, prev_metrics
    except Exception as e:
        st.error(f"Could not load data from MongoDB: {e}")
        return None, None, None, None


@st.cache_data(ttl=3600)
def get_visit_recommendation(city, avg_sentiment, crowding_score, cost_score,
                              positive_ratio, negative_ratio, mention_count):
    GROQ_KEY = os.getenv("GROQ_API_KEY", "")
    if not GROQ_KEY:
        return {"recommendation": "", "verdict": "maybe"}
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_KEY)
        crowding_level = "very high" if crowding_score > 0.4 else "high" if crowding_score > 0.2 else "moderate" if crowding_score > 0.1 else "low"
        cost_level = "very expensive" if cost_score > 0.4 else "expensive" if cost_score > 0.2 else "moderate" if cost_score > 0.1 else "affordable"
        sentiment_desc = "strongly positive" if avg_sentiment > 0.3 else "positive" if avg_sentiment > 0.1 else "mixed" if avg_sentiment > -0.1 else "negative"
        prompt = f"""You are a brutally honest travel advisor. Give a SPECIFIC, DATA-DRIVEN recommendation.
City: {city}
Data from {mention_count} traveller mentions this week:
- Overall sentiment: {avg_sentiment:+.2f} ({sentiment_desc})
- {positive_ratio:.0%} positive mentions, {negative_ratio:.0%} negative mentions
- Crowding level: {crowding_level} (score: {crowding_score:.2f})
- Cost level: {cost_level} (score: {cost_score:.2f})
Rules:
- If crowding score > 0.3, you MUST mention overcrowding
- If cost score > 0.2, you MUST mention high costs
- If negative ratio > 40%, reflect that negativity
- If sentiment is below 0, recommend against visiting
- Maximum 20 words. Start with "Yes —", "No —", or "Maybe —"
Reply with only that one sentence."""
        response = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60, temperature=0.1
        )
        text = response.choices[0].message.content.strip()
        verdict = "yes" if text.lower().startswith("yes") else "no" if text.lower().startswith("no") else "maybe"
        return {"recommendation": text, "verdict": verdict}
    except Exception:
        return {"recommendation": "", "verdict": "maybe"}


def save_feedback(rating, comment):
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        db[FEEDBACK_COLLECTION].insert_one({
            "rating": rating,
            "comment": comment.strip() if comment else "",
            "submitted_at": datetime.now(timezone.utc),
            "source": "public_dashboard"
        })
        client.close()
        return True
    except Exception as e:
        st.error(f"Could not save feedback: {e}")
        return False


def score_css(s):
    if s >= 0.15: return "score-pos"
    if s <= -0.05: return "score-neg"
    return "score-mix"

def sentiment_label(s):
    if s >= 0.15: return "Positive"
    if s <= -0.05: return "Negative"
    return "Mixed"

def change_html(current, prev):
    if prev is None: return '<span class="card-change change-flat">First week of data</span>'
    diff = current - prev
    if diff > 0.05: return f'<span class="card-change change-up">▲ +{diff:.2f} vs last week</span>'
    if diff < -0.05: return f'<span class="card-change change-down">▼ {diff:.2f} vs last week</span>'
    return '<span class="card-change change-flat">● Stable vs last week</span>'

def dim_bar(label, value, color):
    pct = min(float(value) * 250, 100)
    return f'<div class="dim-row"><span class="dim-lbl">{label}</span><div class="dim-track"><div class="dim-fill" style="width:{pct:.0f}%;background:{color}"></div></div></div>'

def fmt_alert(message):
    import re
    m = re.search(r"dropped ([\d.]+) \(([+\-\d.]+) → ([+\-\d.]+)\)", message)
    if m: return f"Sentiment dropped sharply ({m.group(2)} → {m.group(3)})."
    m = re.search(r"Only (\d+) mentions", message)
    if m: return f"Only {m.group(1)} traveller mentions — low confidence."
    if "deviates" in message.lower(): return "Unusual deviation from 4-week average."
    return message


# ── MAIN UI ────────────────────────────────────────────────────────────────────

metrics, alerts, history, prev_metrics = load_data()
week_display = metrics["week_start"].iloc[0] if metrics is not None and not metrics.empty else "—"

# Header
st.markdown(f"""
<div class="dash-header">
    <div class="dash-title">City Sentiment Monitor</div>
    <div class="dash-subtitle">Real-time traveller sentiment across European cities — powered by AI & MongoDB</div>
    <div class="dash-week">Week of {week_display}</div>
</div>
""", unsafe_allow_html=True)

if st.button("⟳ Refresh", key="refresh_main"):
    st.cache_data.clear()
    st.rerun()

if metrics is None or metrics.empty:
    st.info("No data yet — run the pipeline to populate MongoDB.")
    st.stop()

week_start = metrics["week_start"].iloc[0]

# Summary
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overall Sentiment", f"{metrics['avg_sentiment'].mean():+.2f}")
c2.metric("Total Mentions", f"{int(metrics['mention_count'].sum()):,}")
c3.metric("Positive Cities", f"{len(metrics[metrics['avg_sentiment'] >= 0.15])} / {len(metrics)}")
c4.metric("Active Alerts", str(len(alerts) if alerts is not None and not alerts.empty else 0))

# City cards
st.markdown('<div class="section-title">City Breakdown</div>', unsafe_allow_html=True)

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
    info = CITY_INFO.get(city, {})
    img_url = info.get("image", "")
    accent = info.get("accent", "#6366f1")

    alert_tag = '<span class="alert-tag">⚠ Alert</span>' if city_alerts else ""
    alert_html = "".join(f'<div class="alert-box">⚠ {fmt_alert(str(a.get("alert_message", "")))}</div>' for a in city_alerts)
    card_class = "city-card-alert" if city_alerts else "city-card"
    dims = dim_bar("Crowds", row.get("crowding_score", 0), "#EF4444") + dim_bar("Cost", row.get("cost_score", 0), "#F59E0B") + dim_bar("Safety", row.get("safety_score", 0), "#10B981")

    rec = get_visit_recommendation(city=city, avg_sentiment=score, crowding_score=float(row.get("crowding_score", 0)), cost_score=float(row.get("cost_score", 0)), positive_ratio=float(row.get("positive_ratio", 0)), negative_ratio=float(row.get("negative_ratio", 0)), mention_count=int(row.get("mention_count", 0)))
    rec_html = f'<div class="recommendation-{rec["verdict"]}">{rec["recommendation"]}</div>' if rec["recommendation"] else ""

    city_info_html = ""
    if info:
        city_info_html = f'<div class="city-info-section"><div class="info-row"><div class="info-item"><span class="info-label">🗓 Best time</span><span class="info-val">{info.get("best_time","—")}</span></div><div class="info-item"><span class="info-label">🌡 Avg temp</span><span class="info-val">{info.get("avg_temp","—")}</span></div></div><div class="info-full"><span class="info-label">📍 Attractions</span><span class="info-val">{info.get("attractions","—")}</span></div><div class="city-tip">💡 {info.get("tips","")}</div></div>'

    with cols[i % 4]:
        st.markdown(f"""<div class="{card_class}"><img class="card-img" src="{img_url}"><div class="card-accent-bar" style="background:{accent}"></div><div class="card-body"><p class="card-city-name">{city}{alert_tag}</p><div class="card-score-row"><span class="card-score {score_css(score)}">{score:+.2f}</span><span class="card-label {score_css(score)}">{sentiment_label(score)}</span></div>{change_html(score, prev)}<div class="card-stats"><div class="card-stat"><span class="card-stat-label">Mentions</span><span class="card-stat-val">{int(row.get("mention_count",0))}</span></div><div class="card-stat"><span class="card-stat-label">Positive</span><span class="card-stat-val">{row.get("positive_ratio",0):.0%}</span></div><div class="card-stat"><span class="card-stat-label">Negative</span><span class="card-stat-val">{row.get("negative_ratio",0):.0%}</span></div></div>{dims}{rec_html}{alert_html}{city_info_html}</div></div>""", unsafe_allow_html=True)

# Trends
st.markdown('<div class="section-title">Sentiment Trends Over Time</div>', unsafe_allow_html=True)
if history is not None and not history.empty:
    pivot = history.pivot_table(index="week_start", columns="city", values="avg_sentiment")
    selected = st.multiselect("Cities", options=pivot.columns.tolist(), default=pivot.columns.tolist(), label_visibility="collapsed")
    if selected:
        st.line_chart(pivot[selected], height=280, use_container_width=True)

# Alerts
st.markdown('<div class="section-title">Monitoring Alerts</div>', unsafe_allow_html=True)
if alerts is not None and not alerts.empty:
    for _, alert in alerts.iterrows():
        st.markdown(f'<div class="alert-row alert-{alert.get("severity","medium")}"><strong>{alert.get("city","")}</strong> — {fmt_alert(str(alert.get("alert_message","")))}</div>', unsafe_allow_html=True)
else:
    st.markdown('<p style="font-size:0.82rem;color:#9ca3b0;padding:6px 0">No alerts this week.</p>', unsafe_allow_html=True)

# ── FEEDBACK — clickable stars ─────────────────────────────────────────────────
st.markdown('<div class="section-title">Share Your Feedback</div>', unsafe_allow_html=True)

st.markdown("""
<div class="feedback-wrap">
    <div class="feedback-title">Was this dashboard helpful?</div>
    <div class="feedback-sub">Help us improve — takes 10 seconds</div>
</div>
""", unsafe_allow_html=True)

st.write("")

# Star rating using session state
if "star_rating" not in st.session_state:
    st.session_state.star_rating = 0

star_cols = st.columns([1, 1, 1, 1, 1, 4])
labels = {1: "Poor", 2: "Fair", 3: "Good", 4: "Very good", 5: "Excellent"}

for idx, col in enumerate(star_cols[:5]):
    star_num = idx + 1
    filled = star_num <= st.session_state.star_rating
    icon = "⭐" if filled else "☆"
    with col:
        if st.button(icon, key=f"star_{star_num}", help=labels[star_num]):
            st.session_state.star_rating = star_num
            st.rerun()

if st.session_state.star_rating > 0:
    rating_label = labels[st.session_state.star_rating]
    st.markdown(f'<p style="font-size:0.8rem;color:#6b7280;margin-top:2px">You rated: <strong>{st.session_state.star_rating}/5</strong> — {rating_label}</p>', unsafe_allow_html=True)
else:
    st.markdown('<p style="font-size:0.8rem;color:#b0b7c3;margin-top:2px">Click a star to rate</p>', unsafe_allow_html=True)

comment = st.text_area(
    "Comment",
    height=80,
    placeholder="What did you find most useful? Any suggestions?",
    label_visibility="collapsed",
    key="feedback_comment"
)

fb_col1, fb_col2 = st.columns([1, 5])
with fb_col1:
    if st.button("Submit", key="submit_feedback"):
        if st.session_state.star_rating == 0:
            st.warning("Please select a star rating first.")
        else:
            if save_feedback(st.session_state.star_rating, comment):
                st.success(f"{'⭐' * st.session_state.star_rating} Thank you for your feedback!")
                st.session_state.star_rating = 0
                st.balloons()

# Footer
st.divider()
st.markdown(f'<p style="text-align:center;color:#c0c7d4;font-size:0.7rem;">City Sentiment Monitor · Week of {week_start} · M6 MLOps Pipeline · Aalborg University · MongoDB Powered</p>', unsafe_allow_html=True)