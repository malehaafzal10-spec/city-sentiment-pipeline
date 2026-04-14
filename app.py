"""
app.py — City Sentiment Monitor dashboard.
Light background, vibrant colors, MongoDB, city info, feedback collection.
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
        "tips": "Book museums in advance. Avoid August — locals leave and tourist crowds surge.",
        "accent": "#E74C3C",
    },
    "Rome": {
        "image": "https://images.unsplash.com/photo-1552832230-c0197dd311b5?w=400&h=200&fit=crop",
        "best_time": "Apr–May, Sep–Oct",
        "avg_temp": "20°C / 68°F",
        "attractions": "Colosseum, Vatican, Trevi Fountain",
        "tips": "Validate your bus ticket. Tap water from fountains is free and safe.",
        "accent": "#E67E22",
    },
    "Barcelona": {
        "image": "https://images.unsplash.com/photo-1583422409516-2895a77efded?w=400&h=200&fit=crop",
        "best_time": "May–Jun, Sep–Oct",
        "avg_temp": "22°C / 72°F",
        "attractions": "Sagrada Família, Park Güell, La Boqueria",
        "tips": "Watch for pickpockets on Las Ramblas. Dinner starts at 9pm locally.",
        "accent": "#8E44AD",
    },
    "Lisbon": {
        "image": "https://images.unsplash.com/photo-1548707309-dcebeab9ea9b?w=400&h=200&fit=crop",
        "best_time": "Mar–May, Sep–Nov",
        "avg_temp": "18°C / 64°F",
        "attractions": "Belém Tower, Alfama district, Sintra day trip",
        "tips": "Tram 28 is scenic but crowded. Walking the hills is worth the effort.",
        "accent": "#16A085",
    },
    "Amsterdam": {
        "image": "https://images.unsplash.com/photo-1534351590666-13e3e96b5017?w=400&h=200&fit=crop",
        "best_time": "Apr–May (tulips), Jun–Aug",
        "avg_temp": "14°C / 57°F",
        "attractions": "Rijksmuseum, Anne Frank House, Canal cruise",
        "tips": "Rent a bike. Watch out for tram tracks. Book Anne Frank months ahead.",
        "accent": "#27AE60",
    },
    "Prague": {
        "image": "https://images.unsplash.com/photo-1592906209472-a36b1f3782ef?w=400&h=200&fit=crop",
        "best_time": "May–Sep",
        "avg_temp": "16°C / 61°F",
        "attractions": "Prague Castle, Old Town Square, Charles Bridge",
        "tips": "Very affordable. Avoid tourist trap restaurants near the Astronomical Clock.",
        "accent": "#C0392B",
    },
    "Athens": {
        "image": "https://images.unsplash.com/photo-1555993539-1732b0258235?w=400&h=200&fit=crop",
        "best_time": "Apr–Jun, Sep–Oct",
        "avg_temp": "24°C / 75°F",
        "attractions": "Acropolis, Parthenon, Plaka district",
        "tips": "Visit the Acropolis at opening time. Summer heat is intense — stay hydrated.",
        "accent": "#F39C12",
    },
    "London": {
        "image": "https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?w=400&h=200&fit=crop",
        "best_time": "May–Sep",
        "avg_temp": "12°C / 54°F",
        "attractions": "British Museum, Tower of London, Hyde Park",
        "tips": "Get an Oyster card for transport. Many world-class museums are free.",
        "accent": "#2980B9",
    },
}

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');

html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background-color: #f7f8fc !important;
    font-family: 'Plus Jakarta Sans', sans-serif;
}
.block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 1400px; }
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stToolbar"] { display: none; }

.dash-header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%);
    border-radius: 20px;
    padding: 2.2rem 2.8rem;
    margin-bottom: 2rem;
    position: relative;
    overflow: hidden;
}
.dash-header::after {
    content: '🌍';
    position: absolute;
    right: 2rem;
    top: 50%;
    transform: translateY(-50%);
    font-size: 5rem;
    opacity: 0.12;
}
.dash-title { font-size: 2.2rem; font-weight: 800; color: #ffffff; margin: 0; letter-spacing: -0.5px; }
.dash-subtitle { color: rgba(255,255,255,0.5); font-size: 0.9rem; margin-top: 5px; }
.dash-week {
    display: inline-block;
    background: rgba(255,255,255,0.1);
    color: rgba(255,255,255,0.75);
    font-size: 0.7rem; font-weight: 600;
    padding: 3px 12px; border-radius: 20px;
    margin-top: 10px; letter-spacing: 1px;
    text-transform: uppercase;
    border: 1px solid rgba(255,255,255,0.15);
}

[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e8eaf0;
    border-radius: 14px;
    padding: 1.1rem 1.4rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
[data-testid="stMetricLabel"] p {
    font-size: 0.68rem !important;
    color: #9ca3b0 !important;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    font-weight: 600 !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.6rem !important;
    font-weight: 800 !important;
    color: #1a1a2e !important;
}

.city-card {
    background: #ffffff;
    border-radius: 16px;
    border: 1px solid #e8eaf0;
    overflow: hidden;
    margin-bottom: 20px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.05);
}
.city-card-alert {
    background: #ffffff;
    border-radius: 16px;
    border: 1px solid #fcd34d;
    border-top: 4px solid #f59e0b;
    overflow: hidden;
    margin-bottom: 20px;
    box-shadow: 0 2px 12px rgba(245,158,11,0.1);
}
.card-img { width: 100%; height: 135px; object-fit: cover; display: block; }
.card-accent-bar { height: 4px; width: 100%; }
.card-body { padding: 15px 16px 16px; }
.card-city-name { font-size: 1rem; font-weight: 700; color: #1a1a2e; margin: 0 0 3px 0; }
.card-score-row { display: flex; align-items: baseline; gap: 7px; margin-bottom: 1px; }
.card-score { font-size: 1.9rem; font-weight: 800; line-height: 1; }
.score-pos { color: #059669; }
.score-neg { color: #DC2626; }
.score-mix { color: #D97706; }
.card-label { font-size: 0.73rem; font-weight: 700; }
.card-change { font-size: 0.72rem; margin-bottom: 10px; font-weight: 500; }
.change-up { color: #059669; }
.change-down { color: #DC2626; }
.change-flat { color: #9ca3b0; }
.card-stats {
    display: flex;
    border-top: 1px solid #f1f3f8;
    border-bottom: 1px solid #f1f3f8;
    padding: 8px 0; margin-bottom: 11px;
}
.card-stat { flex: 1; display: flex; flex-direction: column; align-items: center; }
.card-stat-label { font-size: 0.6rem; color: #b0b7c3; text-transform: uppercase; letter-spacing: 0.4px; }
.card-stat-val { font-size: 0.92rem; font-weight: 700; color: #1a1a2e; }
.dim-row { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }
.dim-lbl { font-size: 0.65rem; color: #9ca3b0; width: 44px; font-weight: 500; }
.dim-track { flex: 1; height: 4px; background: #f1f3f8; border-radius: 2px; overflow: hidden; }
.dim-fill { height: 100%; border-radius: 2px; }

.city-info-section { margin-top: 11px; padding-top: 10px; border-top: 1px solid #f1f3f8; }
.city-info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; margin-bottom: 7px; }
.city-info-item { display: flex; flex-direction: column; }
.city-info-label { font-size: 0.57rem; color: #b0b7c3; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; }
.city-info-val { font-size: 0.72rem; color: #4a5568; font-weight: 500; line-height: 1.3; }
.city-info-full { display: flex; flex-direction: column; margin-bottom: 6px; }
.city-tip {
    font-size: 0.68rem; color: #6b7280; font-style: italic;
    line-height: 1.4; padding: 6px 9px;
    background: #f8f9fc; border-radius: 7px;
    border-left: 3px solid #e2e5ef;
}

.alert-tag {
    display: inline-block;
    font-size: 0.58rem; font-weight: 700;
    padding: 2px 7px; border-radius: 8px;
    background: #fef3c7; color: #92400e;
    margin-left: 5px; vertical-align: middle;
}
.alert-box {
    font-size: 0.7rem; color: #92400e;
    background: #fffbeb; border: 1px solid #fde68a;
    border-radius: 7px; padding: 5px 9px; margin-top: 7px; line-height: 1.5;
}
.recommendation-yes {
    font-size: 0.71rem; color: #065f46; background: #ecfdf5;
    border: 1px solid #a7f3d0; border-radius: 7px;
    padding: 6px 10px; margin-top: 8px; line-height: 1.5;
}
.recommendation-no {
    font-size: 0.71rem; color: #7f1d1d; background: #fef2f2;
    border: 1px solid #fecaca; border-radius: 7px;
    padding: 6px 10px; margin-top: 8px; line-height: 1.5;
}
.recommendation-maybe {
    font-size: 0.71rem; color: #78350f; background: #fffbeb;
    border: 1px solid #fde68a; border-radius: 7px;
    padding: 6px 10px; margin-top: 8px; line-height: 1.5;
}

.section-title {
    font-size: 0.72rem; font-weight: 700; color: #9ca3b0;
    text-transform: uppercase; letter-spacing: 1.5px;
    margin: 2rem 0 1.2rem; padding-bottom: 0.6rem;
    border-bottom: 2px solid #f1f3f8;
}
.alert-row { padding: 10px 15px; border-radius: 8px; margin-bottom: 7px; font-size: 0.82rem; line-height: 1.5; }
.alert-high { background: #fef2f2; border-left: 3px solid #DC2626; color: #7f1d1d; }
.alert-medium { background: #fffbeb; border-left: 3px solid #D97706; color: #78350f; }
.alert-low { background: #ecfdf5; border-left: 3px solid #059669; color: #065f46; }

.feedback-box {
    background: linear-gradient(135deg, #1a1a2e, #16213e);
    border-radius: 18px;
    padding: 2rem 2.5rem;
    margin-top: 1rem;
}
.feedback-title { font-size: 1.3rem; font-weight: 800; color: #ffffff; margin-bottom: 4px; }
.feedback-sub { color: rgba(255,255,255,0.45); font-size: 0.82rem; margin-bottom: 1.5rem; }

.stTabs [data-baseweb="tab-list"] { gap: 6px; }
.stTabs [data-baseweb="tab"] {
    background: #f1f3f8; border-radius: 10px;
    color: #6b7280; font-weight: 600;
    padding: 7px 16px; border: 1px solid #e2e5ef;
}
.stTabs [aria-selected="true"] {
    background: #1a1a2e !important;
    color: #ffffff !important;
    border-color: #1a1a2e !important;
}
.stTextArea textarea {
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    color: #ffffff !important;
    border-radius: 10px !important;
}
.stButton > button {
    background: linear-gradient(135deg, #1a1a2e, #0f3460) !important;
    color: white !important; border: none !important;
    border-radius: 10px !important; font-weight: 700 !important;
    padding: 0.5rem 2rem !important;
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
            db[CITY_FEATURES_COLLECTION].find(
                {}, {"city": 1, "week_start": 1, "avg_sentiment": 1}
            ).sort("week_start", 1)
        ))
        prev_row = db[CITY_FEATURES_COLLECTION].find_one(
            {"week_start": {"$lt": week}}, sort=[("week_start", -1)]
        )
        prev_metrics = {}
        if prev_row:
            prev_week = prev_row["week_start"]
            prev_metrics = {
                r["city"]: r.get("avg_sentiment", 0.0)
                for r in db[CITY_FEATURES_COLLECTION].find({"week_start": prev_week})
            }
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
- If crowding score > 0.3, you MUST mention overcrowding as a problem
- If cost score > 0.2, you MUST mention high costs
- If negative ratio > 40%, you MUST reflect that negativity
- If sentiment is below 0, recommend against visiting
- Do NOT be generically positive if the data shows problems
- Maximum 20 words
- Start with "Yes —", "No —", or "Maybe —"
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
        return f'<span class="card-change change-up">▲ +{diff:.2f} vs last week</span>'
    if diff < -0.05:
        return f'<span class="card-change change-down">▼ {diff:.2f} vs last week</span>'
    return '<span class="card-change change-flat">● Stable vs last week</span>'

def dim_bar_html(label, value, color):
    pct = min(float(value) * 250, 100)
    return f"""<div class="dim-row">
        <span class="dim-lbl">{label}</span>
        <div class="dim-track"><div class="dim-fill" style="width:{pct:.0f}%;background:{color}"></div></div>
    </div>"""

def format_alert_message(message):
    import re
    match = re.search(r"dropped ([\d.]+) \(([+\-\d.]+) → ([+\-\d.]+)\)", message)
    if match: return f"Sentiment dropped sharply ({match.group(2)} → {match.group(3)})."
    match = re.search(r"Only (\d+) mentions", message)
    if match: return f"Only {match.group(1)} traveller mentions — low confidence."
    if "deviates" in message.lower(): return "Unusual deviation from 4-week average."
    return message


# ── MAIN UI ────────────────────────────────────────────────────────────────────

metrics, alerts, history, prev_metrics = load_data()

week_display = metrics["week_start"].iloc[0] if metrics is not None and not metrics.empty else "—"
col_h1, col_h2 = st.columns([7, 1])
with col_h1:
    st.markdown(f"""
    <div class="dash-header">
        <div class="dash-title">City Sentiment Monitor</div>
        <div class="dash-subtitle">Real-time traveller sentiment across European cities — powered by AI & MongoDB</div>
        <div class="dash-week">Week of {week_display}</div>
    </div>
    """, unsafe_allow_html=True)
with col_h2:
    st.write("")
    st.write("")
    st.write("")
    if st.button("⟳ Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

if metrics is None or metrics.empty:
    st.info("No data yet — run the pipeline to populate MongoDB.")
    st.stop()

week_start = metrics["week_start"].iloc[0]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Overall Sentiment", f"{metrics['avg_sentiment'].mean():+.2f}")
c2.metric("Total Mentions", f"{int(metrics['mention_count'].sum()):,}")
c3.metric("Positive Cities", f"{len(metrics[metrics['avg_sentiment'] >= 0.15])} / {len(metrics)}")
c4.metric("Active Alerts", str(len(alerts) if alerts is not None and not alerts.empty else 0))

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
    alert_html = "".join(
        f'<div class="alert-box">⚠ {format_alert_message(str(a.get("alert_message", "")))}</div>'
        for a in city_alerts
    )
    card_class = "city-card-alert" if city_alerts else "city-card"

    dims = (
        dim_bar_html("Crowds", row.get("crowding_score", 0), "#EF4444") +
        dim_bar_html("Cost", row.get("cost_score", 0), "#F59E0B") +
        dim_bar_html("Safety", row.get("safety_score", 0), "#10B981")
    )

    rec = get_visit_recommendation(
        city=city, avg_sentiment=score,
        crowding_score=float(row.get("crowding_score", 0)),
        cost_score=float(row.get("cost_score", 0)),
        positive_ratio=float(row.get("positive_ratio", 0)),
        negative_ratio=float(row.get("negative_ratio", 0)),
        mention_count=int(row.get("mention_count", 0))
    )
    rec_html = f'<div class="recommendation-{rec["verdict"]}">{rec["recommendation"]}</div>' if rec["recommendation"] else ""

    city_info_html = ""
    if info:
        city_info_html = f"""
        <div class="city-info-section">
            <div class="city-info-grid">
                <div class="city-info-item">
                    <span class="city-info-label">🗓 Best time</span>
                    <span class="city-info-val">{info.get('best_time', '—')}</span>
                </div>
                <div class="city-info-item">
                    <span class="city-info-label">🌡 Avg temp</span>
                    <span class="city-info-val">{info.get('avg_temp', '—')}</span>
                </div>
            </div>
            <div class="city-info-full">
                <span class="city-info-label">📍 Top attractions</span>
                <span class="city-info-val">{info.get('attractions', '—')}</span>
            </div>
            <div class="city-tip">💡 {info.get('tips', '')}</div>
        </div>"""

    with cols[i % 4]:
        st.markdown(f"""
<div class="{card_class}">
  <img class="card-img" src="{img_url}">
  <div class="card-accent-bar" style="background:{accent}"></div>
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
    {city_info_html}
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="section-title">Sentiment Trends Over Time</div>', unsafe_allow_html=True)
if history is not None and not history.empty:
    pivot = history.pivot_table(index="week_start", columns="city", values="avg_sentiment")
    selected = st.multiselect(
        "Cities", options=pivot.columns.tolist(),
        default=pivot.columns.tolist(), label_visibility="collapsed"
    )
    if selected:
        st.line_chart(pivot[selected], height=300, use_container_width=True)

st.markdown('<div class="section-title">Monitoring Alerts</div>', unsafe_allow_html=True)
if alerts is not None and not alerts.empty:
    for _, alert in alerts.iterrows():
        st.markdown(
            f'<div class="alert-row alert-{alert.get("severity", "medium")}">'
            f'<strong>{alert.get("city", "")}</strong> — '
            f'{format_alert_message(str(alert.get("alert_message", "")))}</div>',
            unsafe_allow_html=True
        )
else:
    st.markdown('<p style="font-size:0.85rem;color:#9ca3b0;padding:8px 0">No alerts this week.</p>', unsafe_allow_html=True)

st.write("")
st.markdown('<div class="section-title">Model Evaluation & Human Review</div>', unsafe_allow_html=True)
tab1, tab2 = st.tabs(["📊 LLM Judge Results", "👁 Human Review Queue"])

with tab1:
    st.markdown("#### VADER vs LLM Agreement This Week")
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
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
            for r in judge_results:
                city = r["_id"]
                pct = r["agreement_pct"] * 100
                color = "#059669" if pct >= 70 else "#D97706" if pct >= 50 else "#DC2626"
                confidence = "High confidence" if pct >= 70 else "Medium confidence" if pct >= 50 else "Low confidence"
                st.markdown(f"""
                <div style="display:flex;justify-content:space-between;align-items:center;
                            padding:10px 16px;border-radius:10px;margin-bottom:8px;
                            background:#f8f9fc;border:1px solid #e8eaf0">
                    <span style="font-weight:700;font-size:0.9rem;color:#1a1a2e">{city}</span>
                    <span style="font-size:0.8rem;color:#9ca3b0">{r['agreed']}/{r['total_judged']} agreed</span>
                    <span style="font-weight:700;color:{color};font-size:0.9rem">{pct:.0f}% — {confidence}</span>
                </div>""", unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Could not load judge results: {e}")

with tab2:
    st.markdown("#### Articles Flagged for Human Review")
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        samples = list(db[VALIDATION_COLLECTION].find({"needs_review": True}).limit(20))
        if not samples:
            st.success("✓ No articles need review right now!")
        else:
            st.info(f"{len(samples)} articles need review")
            for r in samples:
                doc_id = r.get("doc_id", str(r["_id"]))
                with st.expander(f"{r.get('city')} — VADER: {r.get('vader_label')} ({r.get('vader_score', 0):+.2f}) | LLM: {r.get('llm_label')}"):
                    st.write(r.get("clean_text", "")[:400])
                    st.caption("VADER and LLM disagreed. What is the correct label?")
                    col1, col2, col3, col4 = st.columns(4)
                    def update_label(doc_id, human_lbl):
                        c = MongoClient(MONGO_URI)
                        c[DB_NAME][VALIDATION_COLLECTION].update_one(
                            {"doc_id": doc_id},
                            {"$set": {"human_label": human_lbl, "needs_review": False}}
                        )
                        c.close()
                    if col1.button("Positive", key=f"pos_{doc_id}"): update_label(doc_id, "positive"); st.rerun()
                    if col2.button("Negative", key=f"neg_{doc_id}"): update_label(doc_id, "negative"); st.rerun()
                    if col3.button("Neutral", key=f"neu_{doc_id}"): update_label(doc_id, "neutral"); st.rerun()
                    if col4.button("Skip", key=f"skip_{doc_id}"): update_label(doc_id, None); st.rerun()

        st.markdown("#### VADER Accuracy from Human Reviews")
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
            latest_acc = acc_df.iloc[-1]
            c1.metric("Latest Accuracy", f"{latest_acc['accuracy_pct']:.1f}%")
            c2.metric("Articles Reviewed", int(latest_acc["total_reviewed"]))
            c3.metric("Correct Predictions", int(latest_acc["correct_count"]))
            if len(acc_df) > 1:
                acc_df.rename(columns={"_id": "week_start"}, inplace=True)
                st.line_chart(acc_df.set_index("week_start")["accuracy_pct"], height=200)
    except Exception as e:
        st.error(f"Could not load validation samples: {e}")

st.markdown('<div class="section-title">Share Your Feedback</div>', unsafe_allow_html=True)
st.markdown("""
<div class="feedback-box">
    <div class="feedback-title">Was this dashboard helpful?</div>
    <div class="feedback-sub">Help us improve — takes 10 seconds</div>
</div>
""", unsafe_allow_html=True)

fb1, fb2 = st.columns([1, 2])
with fb1:
    rating = st.select_slider(
        "Rating", options=[1, 2, 3, 4, 5], value=5,
        format_func=lambda x: "⭐" * x,
        label_visibility="collapsed"
    )
    labels = {1: "Poor", 2: "Fair", 3: "Good", 4: "Very Good", 5: "Excellent!"}
    st.markdown(f'<p style="font-size:1.5rem;margin:4px 0">{"⭐" * rating}</p>', unsafe_allow_html=True)
    st.markdown(f'<p style="color:#6b7280;font-size:0.8rem;margin:0">{labels[rating]}</p>', unsafe_allow_html=True)
with fb2:
    comment = st.text_area(
        "Comment", height=90,
        placeholder="What did you find most useful? Any suggestions?",
        label_visibility="collapsed"
    )

if st.button("Submit Feedback"):
    if save_feedback(rating, comment):
        st.success("✓ Thank you for your feedback!")
        st.balloons()

st.divider()
st.markdown(
    f'<p style="text-align:center;color:#c0c7d4;font-size:0.72rem;">'
    f'City Sentiment Monitor · Week of {week_start} · M6 MLOps Pipeline · Aalborg University · MongoDB Powered</p>',
    unsafe_allow_html=True
)