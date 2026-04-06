"""
dashboard.py — Step 11: Generate dashboard JSON and HTML for GitHub Pages.
"""

import os
import json
import logging
from datetime import datetime, timezone

from db import get_connection

log = logging.getLogger("dashboard")
ARTIFACTS_DIR = os.getenv("PIPELINE_ARTIFACTS_DIR", "artifacts")
DASHBOARD_DIR = os.path.join(ARTIFACTS_DIR, "dashboard")


def sentiment_label(score: float) -> str:
    if score >= 0.15: return "Positive"
    if score <= -0.05: return "Negative"
    return "Mixed"


def sentiment_color(score: float) -> str:
    if score >= 0.15: return "#2e7d32"
    if score <= -0.05: return "#c62828"
    return "#e65100"


def trend_arrow(current: float, previous) -> str:
    if previous is None: return "—"
    diff = current - previous
    if diff > 0.05: return "↑"
    if diff < -0.05: return "↓"
    return "→"


def build_data(conn) -> dict:
    latest = conn.execute(
        "SELECT week_start FROM city_weekly_metrics ORDER BY week_start DESC LIMIT 1"
    ).fetchone()
    if not latest:
        return {"cities": [], "last_updated": datetime.now(timezone.utc).isoformat()}

    week = latest["week_start"]

    current_rows = conn.execute(
        "SELECT * FROM city_weekly_metrics WHERE week_start = ? ORDER BY avg_sentiment DESC", (week,)
    ).fetchall()

    alert_rows = conn.execute(
        "SELECT city, alert_type, alert_message, severity FROM monitoring_alerts WHERE week_start = ?", (week,)
    ).fetchall()
    alerts_by_city = {}
    for a in alert_rows:
        alerts_by_city.setdefault(a["city"], []).append({
            "type": a["alert_type"], "message": a["alert_message"], "severity": a["severity"]
        })

    history_rows = conn.execute(
        "SELECT city, week_start, avg_sentiment, mention_count FROM city_weekly_metrics ORDER BY week_start ASC"
    ).fetchall()
    history_by_city = {}
    for r in history_rows:
        history_by_city.setdefault(r["city"], []).append({
            "week": r["week_start"], "sentiment": r["avg_sentiment"], "mentions": r["mention_count"]
        })

    prev_row = conn.execute(
        "SELECT week_start FROM city_weekly_metrics WHERE week_start < ? ORDER BY week_start DESC LIMIT 1", (week,)
    ).fetchone()
    prev_by_city = {}
    if prev_row:
        for r in conn.execute(
            "SELECT city, avg_sentiment FROM city_weekly_metrics WHERE week_start = ?", (prev_row["week_start"],)
        ).fetchall():
            prev_by_city[r["city"]] = r["avg_sentiment"]

    cities = []
    for row in current_rows:
        city = row["city"]
        score = row["avg_sentiment"]
        prev = prev_by_city.get(city)
        cities.append({
            "name": city,
            "week_start": week,
            "avg_sentiment": score,
            "sentiment_label": sentiment_label(score),
            "sentiment_color": sentiment_color(score),
            "mention_count": row["mention_count"],
            "positive_ratio": row["positive_ratio"],
            "negative_ratio": row["negative_ratio"],
            "crowding_score": row["crowding_score"] or 0,
            "cost_score": row["cost_score"] or 0,
            "safety_score": row["safety_score"] or 0,
            "llm_verdict": row["llm_verdict"] or "",
            "trend_arrow": trend_arrow(score, prev),
            "change_vs_last_week": round(score - prev, 3) if prev is not None else None,
            "alerts": alerts_by_city.get(city, []),
            "has_alerts": len(alerts_by_city.get(city, [])) > 0,
            "history": history_by_city.get(city, [])[-8:]
        })

    return {
        "week_start": week,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "cities": cities
    }


def generate_html(data: dict) -> str:
    updated = datetime.fromisoformat(data["last_updated"]).strftime("%d %B %Y, %H:%M UTC")
    cards = ""

    for city in data["cities"]:
        score = city["avg_sentiment"]
        color = city["sentiment_color"]

        alert_badge = '<span style="background:#fff3e0;color:#bf360c;font-size:11px;padding:3px 8px;border-radius:10px;font-weight:500">Alert</span>' if city["has_alerts"] else '<span style="background:#e8f5e9;color:#1b5e20;font-size:11px;padding:3px 8px;border-radius:10px;font-weight:500">Clear</span>'

        alert_msgs = "".join(
            f'<p style="font-size:11px;padding:5px 8px;border-radius:4px;background:#fff3e0;color:#bf360c;margin:4px 0">{a["message"]}</p>'
            for a in city["alerts"]
        )

        verdict_html = f'<p style="font-style:italic;font-size:12px;color:#555;padding:8px 10px;background:#f9f9f9;border-left:3px solid #ccc;border-radius:0 4px 4px 0;margin:8px 0">"{city["llm_verdict"]}"</p>' if city["llm_verdict"] else ""

        change_html = ""
        if city["change_vs_last_week"] is not None:
            sign = "+" if city["change_vs_last_week"] >= 0 else ""
            chg_color = "#2e7d32" if city["change_vs_last_week"] >= 0 else "#c62828"
            change_html = f'<span style="font-size:11px;color:{chg_color}">{sign}{city["change_vs_last_week"]:.2f} vs last week</span>'

        hist_labels = json.dumps([h["week"] for h in city["history"]])
        hist_scores = json.dumps([h["sentiment"] for h in city["history"]])
        chart_id = f"chart-{city['name'].lower().replace(' ', '-')}"

        border_left = "border-left:4px solid #f57c00;" if city["has_alerts"] else ""

        cards += f"""
        <div style="background:white;border-radius:12px;border:1px solid #e0e0e0;{border_left}padding:18px;display:flex;flex-direction:column;gap:6px">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <h2 style="font-size:15px;font-weight:600;margin:0">{city["name"]}</h2>
                {alert_badge}
            </div>
            <div style="display:flex;align-items:baseline;gap:8px">
                <span style="font-size:26px;font-weight:700;color:{color}">{score:+.2f}</span>
                <span style="font-size:16px">{city["trend_arrow"]}</span>
                <span style="font-size:12px;font-weight:600;color:{color}">{city["sentiment_label"]}</span>
            </div>
            {change_html}
            <div style="display:flex;gap:16px;margin:4px 0">
                <div><div style="font-size:10px;color:#999;text-transform:uppercase">Mentions</div><div style="font-size:14px;font-weight:600">{city["mention_count"]}</div></div>
                <div><div style="font-size:10px;color:#999;text-transform:uppercase">Positive</div><div style="font-size:14px;font-weight:600">{city["positive_ratio"]:.0%}</div></div>
                <div><div style="font-size:10px;color:#999;text-transform:uppercase">Negative</div><div style="font-size:14px;font-weight:600">{city["negative_ratio"]:.0%}</div></div>
            </div>
            <div style="display:flex;flex-direction:column;gap:4px">
                <div style="display:flex;align-items:center;gap:8px"><span style="font-size:11px;color:#777;width:44px">Crowds</span><div style="flex:1;height:5px;background:#eee;border-radius:3px"><div style="width:{min(city['crowding_score']*200,100):.0f}%;height:100%;background:#e57373;border-radius:3px"></div></div></div>
                <div style="display:flex;align-items:center;gap:8px"><span style="font-size:11px;color:#777;width:44px">Cost</span><div style="flex:1;height:5px;background:#eee;border-radius:3px"><div style="width:{min(city['cost_score']*200,100):.0f}%;height:100%;background:#ffb74d;border-radius:3px"></div></div></div>
                <div style="display:flex;align-items:center;gap:8px"><span style="font-size:11px;color:#777;width:44px">Safety</span><div style="flex:1;height:5px;background:#eee;border-radius:3px"><div style="width:{min(city['safety_score']*200,100):.0f}%;height:100%;background:#81c784;border-radius:3px"></div></div></div>
            </div>
            {verdict_html}
            {alert_msgs}
            <canvas id="{chart_id}" height="70"></canvas>
            <script>
            new Chart(document.getElementById('{chart_id}'), {{
                type:'line',
                data:{{labels:{hist_labels},datasets:[{{data:{hist_scores},borderColor:'{color}',backgroundColor:'{color}22',tension:0.3,pointRadius:3,fill:true}}]}},
                options:{{plugins:{{legend:{{display:false}}}},scales:{{y:{{min:-1,max:1,ticks:{{font:{{size:9}}}}}},x:{{ticks:{{font:{{size:9}},maxRotation:30}}}}}}}}
            }});
            </script>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>City Sentiment Monitor</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f5f5;color:#333}}
header{{background:#1a237e;color:white;padding:20px 28px}}
header h1{{font-size:20px;font-weight:600}}
header p{{font-size:12px;opacity:.75;margin-top:4px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;padding:20px 28px;max-width:1400px;margin:0 auto}}
footer{{text-align:center;padding:20px;font-size:11px;color:#999}}
</style>
</head>
<body>
<header>
<h1>City Sentiment Monitor</h1>
<p>How travellers talk about European cities — updated weekly &nbsp;|&nbsp; Week of {data["week_start"]} &nbsp;|&nbsp; Last updated: {updated}</p>
</header>
<div class="grid">{cards}</div>
<footer>M6 — Data Engineering and Machine Learning Operations in Business &nbsp;|&nbsp; Aalborg University</footer>
</body>
</html>"""


def run(run_id: str = None) -> dict:
    log.info(f"=== STEP 11: DASHBOARD | run_id={run_id} ===")
    os.makedirs(DASHBOARD_DIR, exist_ok=True)

    conn = get_connection()
    data = build_data(conn)
    conn.close()

    json_path = os.path.join(DASHBOARD_DIR, "dashboard_data.json")
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)

    html = generate_html(data)
    html_path = os.path.join(DASHBOARD_DIR, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Copy to docs/ for GitHub Pages
    docs_dir = "docs"
    os.makedirs(docs_dir, exist_ok=True)
    with open(os.path.join(docs_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(docs_dir, "dashboard_data.json"), "w") as f:
        json.dump(data, f, indent=2)

    log.info(f"[Dashboard] Generated for {len(data['cities'])} cities → docs/index.html")
    return {"run_id": run_id, "cities_count": len(data["cities"])}


if __name__ == "__main__":
    run()
