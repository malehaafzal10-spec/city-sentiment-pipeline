"""
app.py — City Sentiment Monitor dashboard.
Run: streamlit run app.py
"""

import os
import sqlite3
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="City Sentiment Monitor",
    page_icon="assets/favicon.ico" if os.path.exists("assets/favicon.ico") else None,
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ─── STYLING ──────────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* Force white background everywhere */
html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background-color: #ffffff !important;
}
[data-testid="stSidebar"] { background-color: #f8f8f8 !important; }

/* Remove default padding */
.block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 1200px; }

/* Header */
.dash-header { border-bottom: 1px solid #e8e8e8; padding-bottom: 1.2rem; margin-bottom: 1.8rem; }
.dash-title { font-size: 1.6rem; font-weight: 600; color: #111; letter-spacing: -0.3px; margin: 0; }
.dash-subtitle { font-size: 0.85rem; color: #888; margin-top: 4px; }

/* Summary bar */
.summary-bar { display: flex; gap: 32px; padding: 1rem 1.4rem; background: #f9f9f9; border-radius: 8px; border: 1px solid #efefef; margin-bottom: 2rem; }
.summary-item { display: flex; flex-direction: column; }
.summary-label { font-size: 0.72rem; color: #999; text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 2px; }
.summary-value { font-size: 1.3rem; font-weight: 600; color: #111; }

/* City card */
.city-card { background: #ffffff; border: 1px solid #e8e8e8; border-radius: 10px; padding: 1.2rem 1.3rem; height: 100%; }
.city-card.has-alert { border-left: 3px solid #d97706; }
.city-name { font-size: 1rem; font-weight: 600; color: #111; margin-bottom: 0.5rem; }
.score-row { display: flex; align-items: baseline; gap: 6px; margin-bottom: 2px; }
.score-val { font-size: 1.8rem; font-weight: 700; }
.score-pos { color: #16a34a; }
.score-neg { color: #dc2626; }
.score-mix { color: #d97706; }
.score-label { font-size: 0.8rem; font-weight: 500; }
.score-label-pos { color: #16a34a; }
.score-label-neg { color: #dc2626; }
.score-label-mix { color: #d97706; }
.change-pos { font-size: 0.78rem; color: #16a34a; }
.change-neg { font-size: 0.78rem; color: #dc2626; }
.change-neu { font-size: 0.78rem; color: #999; }
.stats-row { display: flex; gap: 16px; margin: 0.7rem 0; border-top: 1px solid #f0f0f0; padding-top: 0.7rem; }
.stat { display: flex; flex-direction: column; }
.stat-label { font-size: 0.68rem; color: #aaa; text-transform: uppercase; letter-spacing: 0.4px; }
.stat-val { font-size: 0.9rem; font-weight: 500; color: #333; }
.dim-section { margin: 0.6rem 0; }
.dim-row { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }
.dim-label { font-size: 0.72rem; color: #888; width: 44px; }
.dim-bar-bg { flex: 1; height: 4px; background: #f0f0f0; border-radius: 2px; overflow: hidden; }
.dim-bar-fill { height: 100%; border-radius: 2px; }
.alert-pill { display: inline-block; font-size: 0.7rem; padding: 2px 8px; border-radius: 10px; background: #fef3c7; color: #92400e; font-weight: 500; margin-left: 6px; }
.alert-msg { font-size: 0.75rem; color: #92400e; background: #fffbeb; border: 1px solid #fde68a; border-radius: 5px; padding: 5px 9px; margin-top: 6px; }
.verdict-box { font-size: 0.78rem; color: #555; background: #fafafa; border-left: 2px solid #ddd; padding: 6px 10px; border-radius: 0 4px 4px 0; margin-top: 6px; font-style: italic; }

/* Section headers */
.section-header { font-size: 1rem; font-weight: 600; color: #111; margin-bottom: 1rem; padding-bottom: 0.4rem; border-bottom: 1px solid #efefef; }

/* Alert table */
.alert-row-high { background: #fef2f2; border-left: 3px solid #dc2626; padding: 8px 12px; border-radius: 0 5px 5px 0; margin-bottom: 6px; font-size: 0.82rem; }
.alert-row-medium { background: #fffbeb; border-left: 3px solid #d97706; padding: 8px 12px; border-radius: 0 5px 5px 0; margin-bottom: 6px; font-size: 0.82rem; }
.alert-row-low { background: #f0fdf4; border-left: 3px solid #16a34a; padding: 8px 12px; border-radius: 0 5px 5px 0; margin-bottom: 6px; font-size: 0.82rem; }

/* Hide Streamlit branding */
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stToolbar"] { display: none; }

/* Metric overrides */
[data-testid="stMetric"] { background: #f9f9f9; border: 1px solid #efefef; border-radius: 8px; padding: 0.8rem 1rem; }
[data-testid="stMetricLabel"] { font-size: 0.72rem !important; color: #999 !important; text-transform: uppercase; letter-spacing: 0.5px; }
[data-testid="stMetricValue"] { font-size: 1.3rem !important; font-weight: 600 !important; color: #111 !important; }
</style>
""", unsafe_allow_html=True)

# ─── DATA ─────────────────────────────────────────────────────────────────────

DB_PATH = os.getenv("PIPELINE_DB_PATH", "artifacts/pipeline.db")


@st.cache_data(ttl=300)
def load_data():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        latest = conn.execute(
            "SELECT week_start FROM city_weekly_metrics ORDER BY week_start DESC LIMIT 1"
        ).fetchone()
        if not latest:
            return None, None, None, None

        week = latest["week_start"]

        metrics = pd.read_sql(
            "SELECT * FROM city_weekly_metrics WHERE week_start = ? ORDER BY avg_sentiment DESC",
            conn, params=(week,)
        )
        alerts = pd.read_sql(
            "SELECT * FROM monitoring_alerts WHERE week_start = ?",
            conn, params=(week,)
        )
        history = pd.read_sql(
            "SELECT city, week_start, avg_sentiment, mention_count FROM city_weekly_metrics ORDER BY week_start ASC",
            conn
        )

        prev_week = conn.execute(
            "SELECT week_start FROM city_weekly_metrics WHERE week_start < ? ORDER BY week_start DESC LIMIT 1",
            (week,)
        ).fetchone()

        prev_metrics = {}
        if prev_week:
            rows = conn.execute(
                "SELECT city, avg_sentiment FROM city_weekly_metrics WHERE week_start = ?",
                (prev_week["week_start"],)
            ).fetchall()
            prev_metrics = {r["city"]: r["avg_sentiment"] for r in rows}

        conn.close()
        return metrics, alerts, history, prev_metrics

    except Exception as e:
        st.error(f"Could not load data: {e}")
        return None, None, None, None


def score_color_class(score):
    if score >= 0.15: return "score-pos"
    if score <= -0.05: return "score-neg"
    return "score-mix"


def label_color_class(score):
    if score >= 0.15: return "score-label-pos"
    if score <= -0.05: return "score-label-neg"
    return "score-label-mix"


def sentiment_label(score):
    if score >= 0.15: return "Positive"
    if score <= -0.05: return "Negative"
    return "Mixed"


def trend_str(current, previous):
    if previous is None: return ""
    diff = current - previous
    if diff > 0.05: return f'<span class="change-pos">+{diff:.2f} vs last week</span>'
    if diff < -0.05: return f'<span class="change-neg">{diff:.2f} vs last week</span>'
    return f'<span class="change-neu">Stable vs last week</span>'


def dim_bar(label, value, color):
    pct = min(float(value) * 200, 100)
    return f"""
    <div class="dim-row">
        <span class="dim-label">{label}</span>
        <div class="dim-bar-bg"><div class="dim-bar-fill" style="width:{pct:.0f}%;background:{color}"></div></div>
    </div>"""


# ─── LOAD ─────────────────────────────────────────────────────────────────────

metrics, alerts, history, prev_metrics = load_data()

# ─── HEADER ───────────────────────────────────────────────────────────────────

col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.markdown("""
    <div class="dash-header">
        <p class="dash-title">City Sentiment Monitor</p>
        <p class="dash-subtitle">Tracking how travellers talk about European cities — updated weekly</p>
    </div>
    """, unsafe_allow_html=True)
with col_refresh:
    st.write("")
    st.write("")
    if st.button("Refresh", type="secondary"):
        st.cache_data.clear()
        st.rerun()

if metrics is None or metrics.empty:
    st.info("No data yet. Run the pipeline first: `python run_pipeline.py`")
    st.stop()

week_start = metrics["week_start"].iloc[0]

# ─── SUMMARY BAR ──────────────────────────────────────────────────────────────

avg_overall = metrics["avg_sentiment"].mean()
total_mentions = metrics["mention_count"].sum()
positive_cities = len(metrics[metrics["avg_sentiment"] >= 0.15])
alert_count = len(alerts) if alerts is not None else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Overall sentiment", f"{avg_overall:+.2f}")
c2.metric("Total mentions", f"{int(total_mentions):,}")
c3.metric("Positive cities", f"{positive_cities} / {len(metrics)}")
c4.metric("Active alerts", str(alert_count))

st.write("")

# ─── CITY CARDS ───────────────────────────────────────────────────────────────

st.markdown('<p class="section-header">City breakdown</p>', unsafe_allow_html=True)

alerts_by_city = {}
if alerts is not None and not alerts.empty:
    for _, row in alerts.iterrows():
        alerts_by_city.setdefault(row["city"], []).append(row)

cols = st.columns(4)
for i, (_, row) in enumerate(metrics.iterrows()):
    city = row["city"]
    score = float(row["avg_sentiment"])
    prev = prev_metrics.get(city)
    city_alerts = alerts_by_city.get(city, [])

    alert_pill = '<span class="alert-pill">Alert</span>' if city_alerts else ""
    alert_msgs = "".join(
        f'<div class="alert-msg">{a["alert_message"]}</div>'
        for a in city_alerts
    )
    verdict = f'<div class="verdict-box">"{row["llm_verdict"]}"</div>' if row.get("llm_verdict") else ""
    card_class = "city-card has-alert" if city_alerts else "city-card"

    with cols[i % 4]:
        st.markdown(f"""
        <div class="{card_class}">
            <div class="city-name">{city}{alert_pill}</div>
            <div class="score-row">
                <span class="score-val {score_color_class(score)}">{score:+.2f}</span>
                <span class="score-label {label_color_class(score)}">{sentiment_label(score)}</span>
            </div>
            {trend_str(score, prev)}
            <div class="stats-row">
                <div class="stat"><span class="stat-label">Mentions</span><span class="stat-val">{int(row['mention_count'])}</span></div>
                <div class="stat"><span class="stat-label">Positive</span><span class="stat-val">{row['positive_ratio']:.0%}</span></div>
                <div class="stat"><span class="stat-label">Negative</span><span class="stat-val">{row['negative_ratio']:.0%}</span></div>
            </div>
            <div class="dim-section">
                {dim_bar("Crowds", row['crowding_score'], "#ef4444")}
                {dim_bar("Cost", row['cost_score'], "#f59e0b")}
                {dim_bar("Safety", row['safety_score'], "#22c55e")}
            </div>
            {verdict}
            {alert_msgs}
        </div>
        """, unsafe_allow_html=True)
        st.write("")

# ─── TREND CHART ──────────────────────────────────────────────────────────────

st.write("")
st.markdown('<p class="section-header">Sentiment trends</p>', unsafe_allow_html=True)

if history is not None and not history.empty:
    pivot = history.pivot_table(index="week_start", columns="city", values="avg_sentiment")

    selected = st.multiselect(
        "Compare cities",
        options=pivot.columns.tolist(),
        default=pivot.columns.tolist(),
        label_visibility="collapsed"
    )

    if selected:
        st.line_chart(
            pivot[selected],
            height=320,
            use_container_width=True
        )

# ─── ALERTS ───────────────────────────────────────────────────────────────────

st.write("")
st.markdown('<p class="section-header">Monitoring alerts this week</p>', unsafe_allow_html=True)

if alerts is not None and not alerts.empty:
    for _, alert in alerts.iterrows():
        severity = alert["severity"]
        css_class = f"alert-row-{severity}"
        st.markdown(
            f'<div class="{css_class}"><strong>{alert["city"]}</strong> — {alert["alert_message"]}</div>',
            unsafe_allow_html=True
        )
else:
    st.markdown(
        '<div style="font-size:0.85rem;color:#666;padding:10px 0">No alerts this week — all cities within normal ranges.</div>',
        unsafe_allow_html=True
    )

# ─── RAW TABLE ────────────────────────────────────────────────────────────────

st.write("")
with st.expander("Raw data table"):
    display_cols = ["city", "week_start", "avg_sentiment", "mention_count",
                    "positive_ratio", "negative_ratio", "crowding_score", "cost_score", "safety_score"]
    st.dataframe(
        metrics[display_cols].style.format({
            "avg_sentiment": "{:+.3f}",
            "positive_ratio": "{:.0%}",
            "negative_ratio": "{:.0%}",
            "crowding_score": "{:.3f}",
            "cost_score": "{:.3f}",
            "safety_score": "{:.3f}",
        }),
        use_container_width=True,
        hide_index=True
    )

# ─── FOOTER ───────────────────────────────────────────────────────────────────

st.write("")
st.markdown(
    f'<p style="font-size:0.75rem;color:#bbb;text-align:center;padding-top:1rem;border-top:1px solid #f0f0f0">City Sentiment Monitor &nbsp;·&nbsp; Week of {week_start} &nbsp;·&nbsp; M6 Data Engineering and MLOps &nbsp;·&nbsp; Aalborg University</p>',
    unsafe_allow_html=True
)