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
.card-city-name {
    font-size: 1rem;
    font-weight: 700;
    color: #111;
    margin: 0 0 4px 0;
}
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
.verdict-box {
    font-size: 0.75rem;
    color: #666;
    background: #fafaf8;
    border-left: 2px solid #ddd;
    padding: 5px 10px;
    margin-top: 8px;
    font-style: italic;
    line-height: 1.5;
}
.recommendation-yes {
    font-size: 0.75rem;
    color: #14532d;
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-radius: 5px;
    padding: 6px 10px;
    margin-top: 8px;
    line-height: 1.5;
}
.recommendation-no {
    font-size: 0.75rem;
    color: #7f1d1d;
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 5px;
    padding: 6px 10px;
    margin-top: 8px;
    line-height: 1.5;
}
.recommendation-maybe {
    font-size: 0.75rem;
    color: #78350f;
    background: #fffbeb;
    border: 1px solid #fde68a;
    border-radius: 5px;
    padding: 6px 10px;
    margin-top: 8px;
    line-height: 1.5;
}
.section-title {
    font-size: 0.85rem;
    font-weight: 600;
    color: #999;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin: 1.8rem 0 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #e8e8e3;
}
.alert-row {
    padding: 9px 14px;
    border-radius: 6px;
    margin-bottom: 6px;
    font-size: 0.82rem;
    line-height: 1.5;
}
.alert-high { background: #fef2f2; border-left: 3px solid #dc2626; }
.alert-medium { background: #fffbeb; border-left: 3px solid #d97706; }
.alert-low { background: #f0fdf4; border-left: 3px solid #16a34a; }
</style>
""", unsafe_allow_html=True)

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
            "SELECT city, week_start, avg_sentiment FROM city_weekly_metrics ORDER BY week_start ASC",
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


@st.cache_data(ttl=3600)
def get_visit_recommendation(city: str, avg_sentiment: float, crowding_score: float,
                               cost_score: float, positive_ratio: float,
                               negative_ratio: float, mention_count: int) -> dict:
    """
    Use Groq to generate a one-line visit recommendation for a city.
    Cached for 1 hour so we don't call the API on every page load.
    Returns dict with 'recommendation' text and 'verdict' (yes/no/maybe)
    """
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
Be specific and honest. Examples:
"Yes — travellers are loving it this week, low crowds and great value."
"No — overcrowding complaints at record high, avoid peak hours."
"Maybe — beautiful city but costs are rising sharply this month."

Reply with only that one sentence, nothing else."""

        response = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0.3
        )

        text = response.choices[0].message.content.strip()

        # Determine verdict from response
        if text.lower().startswith("yes"):
            verdict = "yes"
        elif text.lower().startswith("no"):
            verdict = "no"
        else:
            verdict = "maybe"

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
    """Convert technical alert messages into readable English."""
    import re

    # Sentiment drop: "Sentiment dropped 0.31 (+0.45 → +0.14)"
    match = re.search(r"dropped ([\d.]+) \(([+\-\d.]+) → ([+\-\d.]+)\)", message)
    if match:
        drop = float(match.group(1))
        prev = match.group(2)
        curr = match.group(3)
        return f"Sentiment dropped sharply this week ({prev} → {curr}). Traveller mood has worsened."

    # Low volume: "Only 3 mentions this week (min: 5)"
    match = re.search(r"Only (\d+) mentions", message)
    if match:
        count = match.group(1)
        return f"Only {count} traveller mentions this week — not enough data to be confident in the score."

    # Rolling deviation
    if "deviates" in message.lower() or "rolling" in message.lower():
        return "This week's sentiment is unusually different from the past 4-week average."

    # Distribution skew
    if "positive ratio" in message.lower():
        return "Unusually high proportion of positive mentions — scores may be less reliable this week."

    if "negative ratio" in message.lower():
        return "Unusually high proportion of negative mentions — something may have happened this week."

    # Default — return as-is if no pattern matched
    return message


# ─── LOAD ─────────────────────────────────────────────────────────────────────

metrics, alerts, history, prev_metrics = load_data()

# ─── HEADER ───────────────────────────────────────────────────────────────────

h1, h2 = st.columns([5, 1])
with h1:
    st.markdown("## City Sentiment Monitor")
    st.caption("Tracking how travellers talk about European cities — updated weekly")
with h2:
    st.write("")
    if st.button("Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

if metrics is None or metrics.empty:
    st.info("No data yet — run `python run_pipeline.py` first")
    st.stop()

week_start = metrics["week_start"].iloc[0]
st.caption(f"Week of {week_start}")
st.divider()

# ─── SUMMARY METRICS ──────────────────────────────────────────────────────────

c1, c2, c3, c4 = st.columns(4)
avg_overall = metrics["avg_sentiment"].mean()
total_mentions = int(metrics["mention_count"].sum())
positive_cities = len(metrics[metrics["avg_sentiment"] >= 0.15])
alert_count = len(alerts) if alerts is not None else 0

c1.metric("Overall sentiment", f"{avg_overall:+.2f}")
c2.metric("Total mentions", f"{total_mentions:,}")
c3.metric("Positive cities", f"{positive_cities} / {len(metrics)}")
c4.metric("Active alerts", str(alert_count))

# ─── CITY CARDS ───────────────────────────────────────────────────────────────

st.markdown('<div class="section-title">City breakdown</div>', unsafe_allow_html=True)

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
    img_url = CITY_IMAGES.get(city, "")

    alert_tag = '<span class="alert-tag">Alert</span>' if city_alerts else ""

    # Format alert messages as readable English
    alert_html = "".join(
        f'<div class="alert-box">{format_alert_message(str(a["alert_message"]))}</div>'
        for a in city_alerts
    )

    verdict_html = f'<div class="verdict-box">"{row["llm_verdict"]}"</div>' if row.get("llm_verdict") else ""
    card_class = "city-card-alert" if city_alerts else "city-card"

    dims = (
        dim_bar_html("Crowds", row["crowding_score"], "#ef4444") +
        dim_bar_html("Cost", row["cost_score"], "#f59e0b") +
        dim_bar_html("Safety", row["safety_score"], "#22c55e")
    )

    # Get visit recommendation from Groq
    rec = get_visit_recommendation(
        city=city,
        avg_sentiment=score,
        crowding_score=float(row["crowding_score"]),
        cost_score=float(row["cost_score"]),
        positive_ratio=float(row["positive_ratio"]),
        negative_ratio=float(row["negative_ratio"]),
        mention_count=int(row["mention_count"])
    )

    rec_css = f"recommendation-{rec['verdict']}"
    rec_html = f'<div class="{rec_css}">{rec["recommendation"]}</div>' if rec["recommendation"] else ""

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
        <span class="card-stat-val">{int(row['mention_count'])}</span>
      </div>
      <div class="card-stat">
        <span class="card-stat-label">Positive</span>
        <span class="card-stat-val">{row['positive_ratio']:.0%}</span>
      </div>
      <div class="card-stat">
        <span class="card-stat-label">Negative</span>
        <span class="card-stat-val">{row['negative_ratio']:.0%}</span>
      </div>
    </div>
    {dims}
    {rec_html}
    {verdict_html}
    {alert_html}
  </div>
</div>
""", unsafe_allow_html=True)

# ─── TREND CHART ──────────────────────────────────────────────────────────────

st.markdown('<div class="section-title">Sentiment trends over time</div>', unsafe_allow_html=True)

if history is not None and not history.empty:
    pivot = history.pivot_table(index="week_start", columns="city", values="avg_sentiment")
    selected = st.multiselect(
        "Cities",
        options=pivot.columns.tolist(),
        default=pivot.columns.tolist(),
        label_visibility="collapsed"
    )
    if selected:
        st.line_chart(pivot[selected], height=300, use_container_width=True)

# ─── ALERTS ───────────────────────────────────────────────────────────────────

st.markdown('<div class="section-title">Monitoring alerts</div>', unsafe_allow_html=True)

if alerts is not None and not alerts.empty:
    for _, alert in alerts.iterrows():
        sev = alert["severity"]
        readable_msg = format_alert_message(str(alert["alert_message"]))
        st.markdown(
            f'<div class="alert-row alert-{sev}"><strong>{alert["city"]}</strong> — {readable_msg}</div>',
            unsafe_allow_html=True
        )
else:
    st.markdown(
        '<p style="font-size:0.85rem;color:#999;padding:8px 0">No alerts this week — all cities within normal ranges.</p>',
        unsafe_allow_html=True
    )

# ─── RAW TABLE ────────────────────────────────────────────────────────────────

st.write("")
with st.expander("Weekly aggregated metrics"):
    cols_show = ["city", "week_start", "avg_sentiment", "mention_count",
                 "positive_ratio", "negative_ratio", "crowding_score", "cost_score", "safety_score"]
    st.dataframe(
        metrics[cols_show].style.format({
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

# ─── VALIDATION TAB ───────────────────────────────────────────────────────────

st.write("")
st.markdown('<div class="section-title">Model evaluation & human review</div>',
            unsafe_allow_html=True)

tab1, tab2 = st.tabs(["LLM Judge results", "Human review queue"])

with tab1:
    st.markdown("#### VADER vs LLM agreement this week")
    st.caption(
        "LLM Judge checks a random sample of VADER scores each run. "
        "Low agreement means VADER may be struggling on that city."
    )

    try:
        conn = sqlite3.connect(DB_PATH)
        judge_rows = pd.read_sql("""
            SELECT city,
                   COUNT(*) as total_judged,
                   SUM(agreement) as agreed,
                   ROUND(AVG(agreement) * 100, 1) as agreement_pct
            FROM llm_judge_results
            WHERE week_start = (
                SELECT MAX(week_start) FROM llm_judge_results
            )
            GROUP BY city
            ORDER BY agreement_pct ASC
        """, conn)
        conn.close()

        if judge_rows.empty:
            st.info("No LLM Judge results yet. Add GROQ_API_KEY to .env and run the pipeline.")
        else:
            for _, row in judge_rows.iterrows():
                pct = row["agreement_pct"]
                color = "#16a34a" if pct >= 70 else "#d97706" if pct >= 50 else "#dc2626"
                confidence = "High confidence" if pct >= 70 else "Medium confidence" if pct >= 50 else "Low confidence"
                st.markdown(f"""
                <div style="display:flex;justify-content:space-between;align-items:center;
                            padding:10px 14px;border-radius:6px;margin-bottom:6px;
                            background:#fafafa;border:1px solid #efefef">
                    <span style="font-weight:600;font-size:0.9rem">{row['city']}</span>
                    <span style="font-size:0.8rem;color:#999">{int(row['agreed'])}/{int(row['total_judged'])} agreed</span>
                    <span style="font-weight:600;color:{color};font-size:0.9rem">{pct:.0f}% — {confidence}</span>
                </div>
                """, unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Could not load judge results: {e}")

with tab2:
    st.markdown("#### Articles flagged for human review")
    st.caption(
        "These articles had VADER and LLM disagreeing. "
        "Mark each one with the correct label."
    )

    try:
        conn = sqlite3.connect(DB_PATH)
        samples = pd.read_sql("""
            SELECT id, city, clean_text, vader_label, vader_score,
                   llm_label, human_label, needs_review
            FROM validation_samples
            WHERE needs_review = 1
            ORDER BY city ASC
            LIMIT 20
        """, conn)
        conn.close()

        if samples.empty:
            st.success(
                "No articles need review right now. "
                "Articles will appear here when LLM Judge finds disagreements."
            )
        else:
            st.info(f"{len(samples)} articles need review")

            for _, row in samples.iterrows():
                with st.expander(
                    f"{row['city']} — VADER: {row['vader_label']} "
                    f"({row['vader_score']:+.2f}) | LLM: {row['llm_label']}"
                ):
                    st.write(row["clean_text"][:400])
                    st.caption("VADER and LLM disagreed. What is the correct label?")

                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        if st.button("Positive", key=f"pos_{row['id']}"):
                            conn = sqlite3.connect(DB_PATH)
                            correct = 1 if row["vader_label"] == "positive" else 0
                            conn.execute("UPDATE validation_samples SET human_label='positive', correct=?, needs_review=0 WHERE id=?", (correct, row["id"]))
                            conn.commit(); conn.close(); st.rerun()
                    with col2:
                        if st.button("Negative", key=f"neg_{row['id']}"):
                            conn = sqlite3.connect(DB_PATH)
                            correct = 1 if row["vader_label"] == "negative" else 0
                            conn.execute("UPDATE validation_samples SET human_label='negative', correct=?, needs_review=0 WHERE id=?", (correct, row["id"]))
                            conn.commit(); conn.close(); st.rerun()
                    with col3:
                        if st.button("Neutral", key=f"neu_{row['id']}"):
                            conn = sqlite3.connect(DB_PATH)
                            correct = 1 if row["vader_label"] == "neutral" else 0
                            conn.execute("UPDATE validation_samples SET human_label='neutral', correct=?, needs_review=0 WHERE id=?", (correct, row["id"]))
                            conn.commit(); conn.close(); st.rerun()
                    with col4:
                        if st.button("Skip", key=f"skip_{row['id']}"):
                            conn = sqlite3.connect(DB_PATH)
                            conn.execute("UPDATE validation_samples SET needs_review=0 WHERE id=?", (row["id"],))
                            conn.commit(); conn.close(); st.rerun()

    except Exception as e:
        st.error(f"Could not load validation samples: {e}")

    st.markdown("#### VADER accuracy from human reviews")
    try:
        conn = sqlite3.connect(DB_PATH)
        accuracy = pd.read_sql("""
            SELECT week_start,
                   COUNT(*) as total_reviewed,
                   SUM(correct) as correct_count,
                   ROUND(AVG(correct) * 100, 1) as accuracy_pct
            FROM validation_samples
            WHERE human_label IS NOT NULL
            GROUP BY week_start
            ORDER BY week_start ASC
        """, conn)
        conn.close()

        if accuracy.empty:
            st.info("No accuracy data yet — review some articles above first.")
        else:
            c1, c2, c3 = st.columns(3)
            latest = accuracy.iloc[-1]
            c1.metric("Latest accuracy", f"{latest['accuracy_pct']:.1f}%")
            c2.metric("Articles reviewed", int(latest["total_reviewed"]))
            c3.metric("Correct predictions", int(latest["correct_count"]))
            if len(accuracy) > 1:
                st.line_chart(accuracy.set_index("week_start")["accuracy_pct"], height=200)
    except Exception as e:
        st.error(f"Could not load accuracy: {e}")

# ─── FOOTER ───────────────────────────────────────────────────────────────────

st.divider()
st.caption(f"City Sentiment Monitor · Week of {week_start} · M6 Data Engineering and MLOps · Aalborg University")