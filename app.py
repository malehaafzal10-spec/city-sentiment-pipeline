"""
app.py — City Sentiment Monitor
Clean, modern design. Shows last 30 days of data across all cities.
Run: streamlit run app.py
"""

import os
from datetime import datetime, timezone, timedelta
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
CITY_FEATURES_COLLECTION = "city_weekly_features"
ALERTS_COLLECTION = "monitoring_alerts"
FEEDBACK_COLLECTION = "user_feedback"

st.set_page_config(page_title="City Sentiment Monitor", layout="wide", initial_sidebar_state="collapsed")

CITY_INFO = {
    "Paris":     {"image": "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?w=600&h=300&fit=crop", "best_time": "Apr–Jun, Sep–Oct", "avg_temp": "15°C", "attractions": "Eiffel Tower, Louvre, Montmartre", "tips": "Book museums ahead. Avoid August crowds.", "accent": "#e74c3c", "bg": "#fff5f5"},
    "Rome":      {"image": "https://images.unsplash.com/photo-1552832230-c0197dd311b5?w=600&h=300&fit=crop", "best_time": "Apr–May, Sep–Oct", "avg_temp": "20°C", "attractions": "Colosseum, Vatican, Trevi Fountain", "tips": "Validate bus tickets. Fountain water is free & safe.", "accent": "#e67e22", "bg": "#fff8f0"},
    "Barcelona": {"image": "https://images.unsplash.com/photo-1583422409516-2895a77efded?w=600&h=300&fit=crop", "best_time": "May–Jun, Sep–Oct", "avg_temp": "22°C", "attractions": "Sagrada Família, Park Güell, La Boqueria", "tips": "Watch pickpockets on Las Ramblas. Dinner at 9pm.", "accent": "#8e44ad", "bg": "#faf5ff"},
    "Lisbon":    {"image": "https://images.unsplash.com/photo-1548707309-dcebeab9ea9b?w=600&h=300&fit=crop", "best_time": "Mar–May, Sep–Nov", "avg_temp": "18°C", "attractions": "Belém Tower, Alfama, Sintra", "tips": "Tram 28 is scenic but packed. Walk the hills.", "accent": "#16a085", "bg": "#f0faf8"},
    "Amsterdam": {"image": "https://images.unsplash.com/photo-1534351590666-13e3e96b5017?w=600&h=300&fit=crop", "best_time": "Apr–May, Jun–Aug", "avg_temp": "14°C", "attractions": "Rijksmuseum, Anne Frank House, Canals", "tips": "Rent a bike. Book Anne Frank months ahead.", "accent": "#27ae60", "bg": "#f0fdf4"},
    "Prague":    {"image": "https://images.unsplash.com/photo-1592906209472-a36b1f3782ef?w=600&h=300&fit=crop", "best_time": "May–Sep", "avg_temp": "16°C", "attractions": "Prague Castle, Old Town Square, Charles Bridge", "tips": "Very affordable. Avoid restaurants near the Clock.", "accent": "#c0392b", "bg": "#fff5f5"},
    "Athens":    {"image": "https://images.unsplash.com/photo-1555993539-1732b0258235?w=600&h=300&fit=crop", "best_time": "Apr–Jun, Sep–Oct", "avg_temp": "24°C", "attractions": "Acropolis, Parthenon, Plaka district", "tips": "Visit Acropolis early. Stay hydrated in summer.", "accent": "#f39c12", "bg": "#fffbf0"},
    "London":    {"image": "https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?w=600&h=300&fit=crop", "best_time": "May–Sep", "avg_temp": "12°C", "attractions": "British Museum, Tower of London, Hyde Park", "tips": "Get Oyster card. Most major museums are free.", "accent": "#2980b9", "bg": "#f0f7ff"},
}

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

*, html, body { font-family: 'Inter', sans-serif; }
html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background: #f8f9fe !important;
}
.block-container { padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1380px; }
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }

/* ─── Header ─── */
.header-wrap {
    background: linear-gradient(135deg, #1e3a5f 0%, #0d2137 100%);
    border-radius: 24px;
    padding: 2.2rem 2.8rem;
    margin-bottom: 2rem;
    display: flex; align-items: center; justify-content: space-between;
    box-shadow: 0 8px 32px rgba(13,33,55,0.18);
}
.header-left {}
.header-title { font-size: 1.9rem; font-weight: 800; color: #fff; letter-spacing: -0.5px; margin: 0; }
.header-sub { font-size: 0.82rem; color: rgba(255,255,255,0.45); margin-top: 4px; }
.header-badge {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 20px; padding: 4px 12px;
    font-size: 0.68rem; font-weight: 600;
    color: rgba(255,255,255,0.6);
    letter-spacing: 0.8px; text-transform: uppercase;
    margin-top: 10px;
}
.header-right { display: flex; align-items: center; gap: 10px; }
.live-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: #4ade80;
    box-shadow: 0 0 0 3px rgba(74,222,128,0.25);
    display: inline-block;
}

/* ─── Metric cards ─── */
[data-testid="stMetric"] {
    background: #fff !important;
    border: 1px solid #eaedf5 !important;
    border-radius: 16px !important;
    padding: 1.1rem 1.4rem !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04) !important;
}
[data-testid="stMetricLabel"] p {
    font-size: 0.65rem !important; color: #94a3b8 !important;
    text-transform: uppercase; letter-spacing: 0.9px; font-weight: 600 !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.6rem !important; font-weight: 800 !important; color: #1e293b !important;
}

/* ─── Section title ─── */
.sec-title {
    font-size: 0.65rem; font-weight: 700; color: #94a3b8;
    text-transform: uppercase; letter-spacing: 1.8px;
    margin: 2rem 0 1.2rem; padding-bottom: 0.6rem;
    border-bottom: 1px solid #eaedf5;
}

/* ─── City card ─── */
.c-card {
    background: #fff; border-radius: 20px;
    border: 1px solid #eaedf5;
    overflow: hidden; margin-bottom: 22px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.05);
    transition: transform 0.15s, box-shadow 0.15s;
    height: 100%;
    display: flex; flex-direction: column;
}

.c-card-lowconf { background: #f8f9fb; border-radius: 20px; border: 1px solid #e2e8f0; border-top: 3px dashed #94a3b8; overflow: hidden; margin-bottom: 22px; box-shadow: none; display: flex; flex-direction: column; height: 100%; opacity: 0.75; filter: saturate(0.4); }
.c-card:hover { transform: translateY(-3px); box-shadow: 0 8px 28px rgba(0,0,0,0.09); }
.c-card-alert { background: #fff; border-radius: 20px; border: 1px solid #fde68a; border-top: 4px solid #f59e0b; overflow: hidden; margin-bottom: 22px; box-shadow: 0 2px 12px rgba(245,158,11,0.08); height: 100%; display: flex; flex-direction: column; }
.c-body { padding: 14px 16px 16px; flex: 1; }
.c-img { width: 100%; height: 140px; object-fit: cover; display: block; }
.c-bar { height: 3px; }
.c-name { font-size: 0.95rem; font-weight: 700; color: #1e293b; margin: 0 0 2px 0; }
.c-score-row { display: flex; align-items: baseline; gap: 7px; margin-bottom: 2px; }
.c-score { font-size: 1.75rem; font-weight: 800; line-height: 1; }
.s-pos { color: #059669; }
.s-neg { color: #dc2626; }
.s-mix { color: #d97706; }
.c-lbl { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.3px; }
.c-chg { font-size: 0.68rem; margin-bottom: 10px; font-weight: 500; }
.chg-up { color: #059669; } .chg-dn { color: #dc2626; } .chg-fl { color: #94a3b8; }
.c-stats { display: flex; border-top: 1px solid #f1f5f9; border-bottom: 1px solid #f1f5f9; padding: 7px 0; margin-bottom: 10px; }
.c-stat { flex: 1; display: flex; flex-direction: column; align-items: center; }
.c-sl { font-size: 0.56rem; color: #cbd5e1; text-transform: uppercase; letter-spacing: 0.4px; }
.c-sv { font-size: 0.88rem; font-weight: 700; color: #1e293b; }
.dim-row { display: flex; align-items: center; gap: 7px; margin-bottom: 5px; }
.dim-l { font-size: 0.6rem; color: #94a3b8; width: 42px; font-weight: 500; }
.dim-t { flex: 1; height: 3px; background: #f1f5f9; border-radius: 2px; overflow: hidden; }
.dim-f { height: 100%; border-radius: 2px; }
.c-info { margin-top: 10px; padding-top: 9px; border-top: 1px solid #f1f5f9; }
.c-info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 5px; }
.c-info-item { display: flex; flex-direction: column; }
.c-il { font-size: 0.52rem; color: #cbd5e1; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; display: block; }
.c-iv { font-size: 0.68rem; color: #475569; font-weight: 500; }
.c-tip { font-size: 0.64rem; color: #64748b; font-style: italic; line-height: 1.4; padding: 5px 8px; background: #f8fafc; border-radius: 6px; border-left: 2px solid #e2e8f0; margin-top: 5px; }
.c-alert { font-size: 0.67rem; color: #92400e; background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; padding: 5px 8px; margin-top: 6px; line-height: 1.5; }
.c-alert-tag { display: inline-block; font-size: 0.55rem; font-weight: 700; padding: 1px 5px; border-radius: 6px; background: #fef3c7; color: #92400e; margin-left: 4px; vertical-align: middle; }
.rec-yes { font-size: 0.67rem; color: #065f46; background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 6px; padding: 5px 8px; margin-top: 7px; line-height: 1.5; }
.rec-no { font-size: 0.67rem; color: #7f1d1d; background: #fef2f2; border: 1px solid #fecaca; border-radius: 6px; padding: 5px 8px; margin-top: 7px; line-height: 1.5; }
.rec-maybe { font-size: 0.67rem; color: #78350f; background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; padding: 5px 8px; margin-top: 7px; line-height: 1.5; }

/* ─── Alert rows ─── */
.al-row { padding: 9px 14px; border-radius: 8px; margin-bottom: 6px; font-size: 0.8rem; line-height: 1.5; }
.al-h { background: #fef2f2; border-left: 3px solid #dc2626; color: #7f1d1d; }
.al-m { background: #fffbeb; border-left: 3px solid #d97706; color: #78350f; }
.al-l { background: #ecfdf5; border-left: 3px solid #059669; color: #065f46; }

/* ─── Feedback ─── */
.fb-wrap {
    background: linear-gradient(135deg, #1e3a5f, #0d2137);
    border-radius: 20px; padding: 2rem 2.5rem;
    box-shadow: 0 8px 32px rgba(13,33,55,0.15);
}
.fb-title { font-size: 1.15rem; font-weight: 800; color: #fff; margin-bottom: 3px; }
.fb-sub { color: rgba(255,255,255,0.35); font-size: 0.78rem; margin-bottom: 1.6rem; }

/* Star rating buttons — invisible clickable area over SVG squares */
div[data-testid="stHorizontalBlock"] div[data-testid="column"]:nth-child(-n+5) button {
    margin-top: -48px !important;
    width: 40px !important;
    height: 40px !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: transparent !important;
    font-size: 0 !important;
    cursor: pointer !important;
    z-index: 10 !important;
    padding: 0 !important;
    min-width: 0 !important;
    opacity: 0 !important;
}

/* Comment box — dark bg, dark text */
.stTextArea textarea {
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    color: #1e293b !important;
    border-radius: 10px !important;
    font-size: 0.85rem !important;
}
.stTextArea textarea::placeholder { color: rgba(30,41,59,0.4) !important; }

/* Submit button */
.stButton > button {
    background: linear-gradient(135deg, #3b82f6, #1d4ed8) !important;
    color: #fff !important; border: none !important;
    border-radius: 10px !important; font-weight: 700 !important;
    padding: 0.5rem 1.8rem !important; font-size: 0.85rem !important;
}
.stButton > button:hover { opacity: 0.9; }

/* Multiselect tags */
[data-baseweb="tag"] { background: #1e3a5f !important; border-radius: 8px !important; }
[data-baseweb="tag"] span { color: #fff !important; }
</style>
""", unsafe_allow_html=True)


# ── Data loading — last 30 days across ALL weeks ───────────────────────────────
@st.cache_data(ttl=300)
def load_data():
    if not MONGO_URI:
        st.error("MONGO_URI not found.")
        return None, None, None, None
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]

        # Get all weekly features from last 30 days
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        all_weeks = list(db[CITY_FEATURES_COLLECTION].find(
            {"week_start": {"$gte": cutoff}},
            sort=[("week_start", -1)]
        ))

        # Also get ALL weeks for the trend chart
        all_history = list(db[CITY_FEATURES_COLLECTION].find(
            {}, {"city": 1, "week_start": 1, "avg_sentiment": 1}
        ).sort("week_start", 1))

        if not all_weeks:
            # Fallback: just get whatever exists
            all_weeks = list(db[CITY_FEATURES_COLLECTION].find(sort=[("week_start", -1)]))

        if not all_weeks:
            client.close()
            return None, None, None, None

        # Aggregate per city across all matching weeks (weighted by mention count)
        city_agg = {}
        for doc in all_weeks:
            city = doc.get("city")
            if not city:
                continue
            if city not in city_agg:
                city_agg[city] = {
                    "city": city,
                    "sentiment_total": 0.0,
                    "mention_count": 0,
                    "pos_total": 0,
                    "neg_total": 0,
                    "crowding_total": 0.0,
                    "cost_total": 0.0,
                    "safety_total": 0.0,
                    "week_count": 0
                }
            n = doc.get("mention_count", 0) or 0
            city_agg[city]["sentiment_total"] += doc.get("avg_sentiment", 0) * max(n, 1)
            city_agg[city]["mention_count"] += n
            city_agg[city]["pos_total"] += doc.get("positive_ratio", 0) * max(n, 1)
            city_agg[city]["neg_total"] += doc.get("negative_ratio", 0) * max(n, 1)
            city_agg[city]["crowding_total"] += doc.get("crowding_score", 0) * max(n, 1)
            city_agg[city]["cost_total"] += doc.get("cost_score", 0) * max(n, 1)
            city_agg[city]["safety_total"] += doc.get("safety_score", 0) * max(n, 1)
            city_agg[city]["week_count"] += 1

        rows = []
        for city, agg in city_agg.items():
            total = max(agg["mention_count"], 1)
            rows.append({
                "city": city,
                "avg_sentiment": round(agg["sentiment_total"] / total, 4),
                "mention_count": agg["mention_count"],
                "positive_ratio": round(agg["pos_total"] / total, 3),
                "negative_ratio": round(agg["neg_total"] / total, 3),
                "crowding_score": round(agg["crowding_total"] / total, 3),
                "cost_score": round(agg["cost_total"] / total, 3),
                "safety_score": round(agg["safety_total"] / total, 3),
                "week_start": max(d.get("week_start","") for d in all_weeks if d.get("city") == city),
            })

        metrics = pd.DataFrame(rows).sort_values("avg_sentiment", ascending=False)

        # Alerts — latest week only
        latest_week = all_weeks[0].get("week_start", "")
        alerts = pd.DataFrame(list(db[ALERTS_COLLECTION].find({"week_start": latest_week})))

        # History for trend chart
        history = pd.DataFrame(all_history)

        # Previous period for comparison
        prev_cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%d")
        prev_weeks = list(db[CITY_FEATURES_COLLECTION].find({
            "week_start": {"$gte": prev_cutoff, "$lt": cutoff}
        }))
        prev_metrics = {}
        prev_city_agg = {}
        for doc in prev_weeks:
            city = doc.get("city")
            if not city:
                continue
            n = doc.get("mention_count", 0) or 0
            if city not in prev_city_agg:
                prev_city_agg[city] = {"total": 0.0, "count": 0}
            prev_city_agg[city]["total"] += doc.get("avg_sentiment", 0) * max(n, 1)
            prev_city_agg[city]["count"] += max(n, 1)
        for city, pa in prev_city_agg.items():
            prev_metrics[city] = round(pa["total"] / pa["count"], 4)

        client.close()
        return metrics, alerts, history, prev_metrics
    except Exception as e:
        st.error(f"Could not load data: {e}")
        return None, None, None, None


@st.cache_data(ttl=3600)
def get_recommendation(city, avg_sentiment, crowding_score, cost_score, positive_ratio, negative_ratio, mention_count):
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return {"recommendation": "", "verdict": "maybe"}
    try:
        from groq import Groq
        client = Groq(api_key=key)
        cl = "very high" if crowding_score > 0.4 else "high" if crowding_score > 0.2 else "moderate" if crowding_score > 0.1 else "low"
        co = "very expensive" if cost_score > 0.4 else "expensive" if cost_score > 0.2 else "moderate" if cost_score > 0.1 else "affordable"
        sd = "strongly positive" if avg_sentiment > 0.3 else "positive" if avg_sentiment > 0.1 else "mixed" if avg_sentiment > -0.1 else "negative"
        r = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": f"Brutally honest travel advisor. City: {city}. Sentiment: {avg_sentiment:+.2f} ({sd}). {positive_ratio:.0%} positive, {negative_ratio:.0%} negative. Crowds: {cl}. Cost: {co}. {mention_count} mentions. Give ONE sentence max 20 words starting Yes—, No—, or Maybe—. Be specific about problems if crowding>0.3 or cost>0.2 or sentiment<0."}],
            max_tokens=50, temperature=0.1
        )
        text = r.choices[0].message.content.strip()
        v = "yes" if text.lower().startswith("yes") else "no" if text.lower().startswith("no") else "maybe"
        return {"recommendation": text, "verdict": v}
    except Exception:
        return {"recommendation": "", "verdict": "maybe"}


def save_feedback(rating, comment):
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        db[FEEDBACK_COLLECTION].insert_one({"rating": rating, "comment": comment.strip() if comment else "", "submitted_at": datetime.now(timezone.utc), "source": "public_dashboard"})
        client.close()
        return True
    except Exception as e:
        st.error(f"Could not save feedback: {e}")
        return False


def scls(s):
    return "s-pos" if s >= 0.15 else "s-neg" if s <= -0.05 else "s-mix"

def slbl(s):
    return "Positive" if s >= 0.15 else "Negative" if s <= -0.05 else "Mixed"

def chg_html(cur, prev):
    if prev is None: return '<span class="c-chg chg-fl">First period</span>'
    d = cur - prev
    if d > 0.05: return f'<span class="c-chg chg-up">▲ +{d:.2f} vs prev period</span>'
    if d < -0.05: return f'<span class="c-chg chg-dn">▼ {d:.2f} vs prev period</span>'
    return '<span class="c-chg chg-fl">● Stable</span>'

def dim(label, val, color):
    pct = min(float(val) * 250, 100)
    return f'<div class="dim-row"><span class="dim-l">{label}</span><div class="dim-t"><div class="dim-f" style="width:{pct:.0f}%;background:{color}"></div></div></div>'

def fmt_alert(msg):
    import re
    m = re.search(r"dropped ([\d.]+) \(([+\-\d.]+) → ([+\-\d.]+)\)", msg)
    if m: return f"Sentiment dropped ({m.group(2)} → {m.group(3)})."
    m = re.search(r"Only (\d+) mentions", msg)
    if m: return f"Only {m.group(1)} mentions — low confidence."
    return msg


# ── UI ─────────────────────────────────────────────────────────────────────────

metrics, alerts, history, prev_metrics = load_data()

# Header
st.markdown(f"""
<div class="header-wrap">
  <div class="header-left">
    <div class="header-title">City Sentiment Monitor</div>
    <div class="header-sub">Real-time traveller sentiment across European cities — AI & MongoDB powered</div>
    <div class="header-badge"><span class="live-dot"></span> Last 30 days · Updated daily</div>
  </div>
</div>
""", unsafe_allow_html=True)

if st.button("⟳ Refresh", key="refresh"):
    st.cache_data.clear()
    st.rerun()

if metrics is None or metrics.empty:
    st.info("No data yet — run the pipeline first.")
    st.stop()

# Summary metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Avg Sentiment (30d)", f"{metrics['avg_sentiment'].mean():+.2f}")
c2.metric("Total Mentions", f"{int(metrics['mention_count'].sum()):,}")
c3.metric("Positive Cities", f"{len(metrics[metrics['avg_sentiment'] >= 0.15])} / {len(metrics)}")
c4.metric("Active Alerts", str(len(alerts) if alerts is not None and not alerts.empty else 0))

# City cards — with sort filter
st.markdown('<div class="sec-title">City Breakdown — Last 30 Days</div>', unsafe_allow_html=True)

sort_col1, sort_col2 = st.columns([2, 5])
with sort_col1:
    sort_by = st.selectbox(
        "Sort by",
        options=["Sentiment (best first)", "Cost (cheapest first)", "Crowds (least crowded first)", "Safety (safest first)", "Mentions (most discussed first)"],
        label_visibility="collapsed",
        key="sort_by"
    )

sort_map = {
    "Sentiment (best first)": ("avg_sentiment", False),
    "Cost (cheapest first)": ("cost_score", True),
    "Crowds (least crowded first)": ("crowding_score", True),
    "Safety (safest first)": ("safety_score", False),
    "Mentions (most discussed first)": ("mention_count", False),
}
sort_col, sort_asc = sort_map[sort_by]

# Flag low-confidence cities (fewer than 5 mentions)
LOW_MENTION_THRESHOLD = 5
metrics["low_confidence"] = metrics["mention_count"] < LOW_MENTION_THRESHOLD

# Sort: low-confidence cities always go to the end regardless of filter
metrics_confident = metrics[~metrics["low_confidence"]].sort_values(sort_col, ascending=sort_asc)
metrics_low = metrics[metrics["low_confidence"]].sort_values(sort_col, ascending=sort_asc)
metrics = pd.concat([metrics_confident, metrics_low]).reset_index(drop=True)

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
    img = info.get("image", "")
    accent = info.get("accent", "#6366f1")

    low_conf = bool(row.get("low_confidence", False))
    alert_tag = '<span class="c-alert-tag">⚠ Alert</span>' if city_alerts else ""
    if low_conf:
        alert_tag += '<span style="display:inline-block;font-size:0.58rem;font-weight:700;padding:2px 7px;border-radius:6px;background:#f1f5f9;color:#64748b;margin-left:4px;vertical-align:middle;border:1px solid #cbd5e1;">⚠ Low data</span>'
    cc = "c-card-alert" if city_alerts else ("c-card-lowconf" if low_conf else "c-card")
    alert_html = "".join(f'<div class="c-alert">⚠ {fmt_alert(str(a.get("alert_message","")))} </div>' for a in city_alerts)


    dims_html = dim("Crowds", row.get("crowding_score",0), "#ef4444") + dim("Cost", row.get("cost_score",0), "#f59e0b") + dim("Safety", row.get("safety_score",0), "#10b981")

    rec = get_recommendation(city=city, avg_sentiment=score, crowding_score=float(row.get("crowding_score",0)), cost_score=float(row.get("cost_score",0)), positive_ratio=float(row.get("positive_ratio",0)), negative_ratio=float(row.get("negative_ratio",0)), mention_count=int(row.get("mention_count",0)))
    rec_html = f'<div class="rec-{rec["verdict"]}">{rec["recommendation"]}</div>' if rec["recommendation"] else ""

    ci = f'<div class="c-info"><div class="c-info-grid"><div class="c-info-item"><span class="c-il">🗓 Best time</span><span class="c-iv">{info.get("best_time","—")}</span></div><div class="c-info-item"><span class="c-il">🌡 Avg temp</span><span class="c-iv">{info.get("avg_temp","—")}</span></div></div><div class="c-info-item" style="margin-bottom:5px"><span class="c-il">📍 Attractions</span><span class="c-iv">{info.get("attractions","—")}</span></div><div class="c-tip">💡 {info.get("tips","")}</div></div>' if info else ""

    with cols[i % 4]:
        st.markdown(f'<div class="{cc}"><img class="c-img" src="{img}"><div class="c-bar" style="background:{accent}"></div><div class="c-body"><p class="c-name">{city}{alert_tag}</p><div class="c-score-row"><span class="c-score {scls(score)}">{score:+.2f}</span><span class="c-lbl {scls(score)}">{slbl(score)}</span></div>{chg_html(score,prev)}<div class="c-stats"><div class="c-stat"><span class="c-sl">Mentions</span><span class="c-sv">{int(row.get("mention_count",0))}</span></div><div class="c-stat"><span class="c-sl">Positive</span><span class="c-sv">{row.get("positive_ratio",0):.0%}</span></div><div class="c-stat"><span class="c-sl">Negative</span><span class="c-sv">{row.get("negative_ratio",0):.0%}</span></div></div>{dims_html}{rec_html}{alert_html}{ci}</div></div>', unsafe_allow_html=True)

# Trend chart
st.markdown('<div class="sec-title">Sentiment Trends</div>', unsafe_allow_html=True)
if history is not None and not history.empty:
    pivot = history.pivot_table(index="week_start", columns="city", values="avg_sentiment")
    cities_available = pivot.columns.tolist()
    selected = st.multiselect("Select cities", options=cities_available, default=cities_available, label_visibility="collapsed")
    if selected:
        try:
            import altair as alt
            CITY_COLORS = {
                "Paris": "#e74c3c", "Rome": "#e67e22", "Barcelona": "#8e44ad",
                "Lisbon": "#16a085", "Amsterdam": "#27ae60", "Prague": "#c0392b",
                "Athens": "#f39c12", "London": "#2980b9"
            }
            chart_data = pivot[selected].reset_index().melt(
                id_vars="week_start", var_name="City", value_name="Sentiment"
            ).dropna()
            chart_data["week_start"] = chart_data["week_start"].astype(str)

            color_scale = alt.Scale(
                domain=list(CITY_COLORS.keys()),
                range=list(CITY_COLORS.values())
            )

            line = alt.Chart(chart_data).mark_line(
                interpolate="monotone", strokeWidth=2.5
            ).encode(
                x=alt.X("week_start:O", axis=alt.Axis(
                    labelAngle=-30, labelFontSize=10,
                    labelColor="#94a3b8", ticks=False,
                    domainColor="#eaedf5", grid=False
                )),
                y=alt.Y("Sentiment:Q", scale=alt.Scale(domain=[-0.2, 1.2]),
                    axis=alt.Axis(labelFontSize=10, labelColor="#94a3b8",
                                  gridColor="#eaedf5", ticks=False, domainOpacity=0)
                ),
                color=alt.Color("City:N", scale=color_scale,
                    legend=alt.Legend(orient="bottom", columns=4,
                        labelFontSize=11, symbolSize=80,
                        labelColor="#475569", titleOpacity=0)
                ),
                tooltip=["City:N", "week_start:O", alt.Tooltip("Sentiment:Q", format=".2f")]
            )

            area = alt.Chart(chart_data).mark_area(
                interpolate="monotone", opacity=0.07
            ).encode(
                x=alt.X("week_start:O", sort=None),
                y=alt.Y("Sentiment:Q", scale=alt.Scale(domain=[-0.2, 1.2])),
                color=alt.Color("City:N", scale=color_scale, legend=None)
            )

            chart = (area + line).properties(
                height=250, background="transparent"
            ).configure_view(strokeWidth=0).configure_axis(labelFont="sans-serif")
            st.altair_chart(chart, use_container_width=True)
        except Exception as ex:
            st.error(f"Chart error: {ex}")
            st.line_chart(pivot[selected], height=260, use_container_width=True)

# Feedback
st.markdown('<div class="sec-title">Share Your Feedback</div>', unsafe_allow_html=True)
st.markdown('<div class="fb-wrap"><div class="fb-title">Was this dashboard helpful?</div><div class="fb-sub">Help us improve — takes 10 seconds</div></div>', unsafe_allow_html=True)
st.write("")

if "star_rating" not in st.session_state:
    st.session_state.star_rating = 0

# Stars — Trustpilot style using buttons hidden behind HTML
rating_labels = {0: "Click a star to rate", 1: "Poor", 2: "Fair", 3: "Good", 4: "Very good", 5: "Excellent!"}
current_rating = st.session_state.star_rating

# Star buttons — ★ filled green, ☆ empty grey
star_cols = st.columns([1, 1, 1, 1, 1, 8])
for idx in range(5):
    star_num = idx + 1
    filled = star_num <= current_rating
    star_char = "★" if filled else "☆"
    color = "#00b67a" if filled else "#94a3b8"
    with star_cols[idx]:
        st.markdown(f"""<style>
        div[data-testid="column"]:nth-child({idx+1}) button {{
            color: {color} !important;
            font-size: 2.2rem !important;
            background: none !important;
            border: none !important;
            box-shadow: none !important;
            padding: 0 !important;
            line-height: 1.2 !important;
            min-width: 0 !important;
        }}
        div[data-testid="column"]:nth-child({idx+1}) button:hover {{
            color: #00b67a !important;
            transform: scale(1.15);
        }}
        </style>""", unsafe_allow_html=True)
        if st.button(star_char, key=f"s{star_num}"):
            st.session_state.star_rating = star_num
            st.rerun()
lbl = rating_labels[current_rating]
lbl_color = "#00b67a" if current_rating > 0 else "#94a3b8"
st.markdown(f'<p style="font-size:0.78rem;color:{lbl_color};margin:6px 0 10px;font-weight:600">{lbl}</p>', unsafe_allow_html=True)

comment = st.text_area("", height=75, placeholder="What did you find most useful? Any suggestions?", label_visibility="collapsed", key="fb_comment")

if st.button("Submit Feedback", key="fb_submit"):
    if st.session_state.star_rating == 0:
        st.warning("Please select a star rating first.")
    else:
        if save_feedback(st.session_state.star_rating, comment):
            st.success(f"{'⭐' * st.session_state.star_rating} Thank you!")
            st.session_state.star_rating = 0
            st.balloons()

st.divider()
st.markdown('<p style="text-align:center;color:#cbd5e1;font-size:0.68rem;">City Sentiment Monitor · Last 30 Days · M6 MLOps Pipeline · Aalborg University · MongoDB</p>', unsafe_allow_html=True)