"""
track_artifacts.py — MLOps HTML Report Generator
Fetches the latest pipeline run from MongoDB and generates a standalone 
HTML report summarizing metrics, sentiment scores, and aggregations.
"""

import os
import json
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
ARTIFACTS_COLLECTION = "pipeline_artifacts"

def generate_table_rows(data_list):
    """Helper to generate HTML table rows from a list of dictionaries."""
    if not data_list:
        return "<tr><td>No payload data available.</td></tr>"
    
    # Flatten keys for the table header (ignore deep nesting for simple table views)
    headers = list(data_list[0].keys())
    header_html = "<tr>" + "".join([f"<th>{h}</th>" for h in headers]) + "</tr>"
    
    rows_html = ""
    for item in data_list:
        row = "<tr>"
        for h in headers:
            val = item.get(h, "")
            # If the value is a dictionary (like vader_breakdown), stringify it
            if isinstance(val, dict):
                val = json.dumps(val)
            # Truncate extremely long text strings for readability
            elif isinstance(val, str) and len(val) > 80:
                val = val[:80] + "... [Truncated]"
            row += f"<td>{val}</td>"
        row += "</tr>"
        
    return header_html + rows_html

def get_first_item_json(payload):
    """Extracts the first item of a payload and formats it as pretty JSON for schema preview."""
    if payload and isinstance(payload, list) and len(payload) > 0:
        preview_item = payload[0].copy()
        # Truncate long text fields so the JSON preview doesn't flood the screen
        for key in ["text", "description", "content"]:
            if key in preview_item and isinstance(preview_item[key], str) and len(preview_item[key]) > 100:
                preview_item[key] = preview_item[key][:100] + "... [TRUNCATED FOR PREVIEW]"
        return json.dumps(preview_item, indent=4)
    return "{\n  // No payload available\n}"

def generate_report():
    if not MONGO_URI:
        print("❌ Error: MONGO_URI is missing. Cannot connect to MongoDB.")
        return

    print(f"🔌 Connecting to MongoDB: {DB_NAME}...")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    # 1. Fetch the latest standard run_id (Ignoring historical backfills)
    latest_artifact = db[ARTIFACTS_COLLECTION].find_one(
        {"run_id": {"$regex": "^run_\\d{8}$"}}, 
        sort=[("timestamp", -1)]
    )
    
    if not latest_artifact:
        print("❌ No standard run artifacts found in the database. Run the pipeline first.")
        client.close()
        return
        
    run_id = latest_artifact.get("run_id", "run_unknown")
    print(f"🔎 Compiling report for standard run: {run_id}")

    # Fetch artifacts
    artifacts = {}
    for a_type in ["raw_ingestion", "processed_scraped_docs", "sentiment_scores", "feature_aggregates"]:
        artifacts[a_type] = db[ARTIFACTS_COLLECTION].find_one({"run_id": run_id, "artifact_type": a_type}) or {}

    # --- Extract Data ---
    
    # Section 1: Raw Ingestion
    raw_docs = artifacts["raw_ingestion"].get("document_count", 0)

    # Section 2: Processed Docs
    proc_metrics = artifacts["processed_scraped_docs"].get("metrics", {})
    proc_labels_json = json.dumps(list(proc_metrics.keys()))
    proc_data_json = json.dumps(list(proc_metrics.values()))
    
    proc_payload = artifacts["processed_scraped_docs"].get("payload", [])
    proc_first_json = get_first_item_json(proc_payload)
    proc_table = generate_table_rows(proc_payload[:10])

    # Section 3: Sentiment Scores
    sentiment_docs = artifacts["sentiment_scores"].get("document_count", 0)
    sentiment_metrics = artifacts["sentiment_scores"].get("metrics", {})
    
    sentiment_payload = artifacts["sentiment_scores"].get("payload", [])
    sentiment_first_json = get_first_item_json(sentiment_payload)
    sentiment_table = generate_table_rows(sentiment_payload[:10])

    # Section 4: Feature Aggregates
    agg_metrics = artifacts["feature_aggregates"].get("metrics", {})
    total_cities = agg_metrics.get("total_cities_aggregated", 0)
    
    agg_payload = artifacts["feature_aggregates"].get("payload", [])
    agg_first_json = get_first_item_json(agg_payload)
    agg_table = generate_table_rows(agg_payload[:10])

    client.close()

    # --- HTML Construction ---
    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Pipeline Run Report: {run_id}</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; color: #333; margin: 0; padding: 20px; }}
            .container {{ max-width: 1100px; margin: auto; background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
            h1 {{ border-bottom: 2px solid #0056b3; padding-bottom: 10px; color: #0056b3; }}
            h2 {{ color: #444; margin-top: 30px; border-bottom: 1px solid #ddd; padding-bottom: 5px; }}
            .metric-box {{ background: #e9ecef; padding: 15px; border-radius: 5px; font-size: 1.2em; font-weight: bold; display: inline-block; margin-bottom: 15px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 0.9em; }}
            th, td {{ padding: 10px; border: 1px solid #ddd; text-align: left; }}
            th {{ background-color: #0056b3; color: white; }}
            tr:nth-child(even) {{ background-color: #f8f9fa; }}
            .chart-container {{ width: 100%; max-width: 800px; margin: 20px 0; }}
            pre {{ background: #272822; color: #f8f8f2; padding: 15px; border-radius: 5px; overflow-x: auto; font-size: 0.9em; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📊 Tourist Spot Pipeline Report</h1>
            <p><strong>Run ID:</strong> {run_id}</p>
            <p><strong>Generated At:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>

            <h2>1. Artifact: RAW_INGESTION</h2>
            <div class="metric-box">Total Documents Fetched: {raw_docs}</div>

            <h2>2. Artifact: PROCESSED_SCRAPED_DOCS</h2>
            <div class="chart-container">
                <canvas id="metricsChart"></canvas>
            </div>
            <p><strong>Payload Preview (First Item Schema):</strong></p>
            <pre><code>{proc_first_json}</code></pre>
            <p><strong>Payload Data (Max 10):</strong></p>
            <div style="overflow-x:auto;">
                <table>{proc_table}</table>
            </div>

            <h2>3. Artifact: SENTIMENT_SCORES</h2>
            <div class="metric-box">Total Documents Scored: {sentiment_docs}</div>
            <p><strong>Sentiment Distribution Metrics:</strong></p>
            <pre style="background: #eee; color: #333;"><code>{json.dumps(sentiment_metrics, indent=4)}</code></pre>
            
            <p><strong>Payload Preview (First Item Schema):</strong></p>
            <pre><code>{sentiment_first_json}</code></pre>
            
            <p><strong>Payload Data (Max 10):</strong></p>
            <div style="overflow-x:auto;">
                <table>{sentiment_table}</table>
            </div>

            <h2>4. Artifact: FEATURE_AGGREGATES</h2>
            <div class="metric-box">Total Cities Aggregated: {total_cities}</div>
            
            <p><strong>Payload Preview (First Item Schema):</strong></p>
            <pre><code>{agg_first_json}</code></pre>
            
            <p><strong>Payload Data (Max 10):</strong></p>
            <div style="overflow-x:auto;">
                <table>{agg_table}</table>
            </div>
        </div>

        <script>
            // Render the Bar Chart using Chart.js
            const ctx = document.getElementById('metricsChart').getContext('2d');
            new Chart(ctx, {{
                type: 'bar',
                data: {{
                    labels: {proc_labels_json},
                    datasets: [{{
                        label: 'Processed Filter Metrics',
                        data: {proc_data_json},
                        backgroundColor: 'rgba(54, 162, 235, 0.7)',
                        borderColor: 'rgba(54, 162, 235, 1)',
                        borderWidth: 1
                    }}]
                }},
                options: {{
                    responsive: true,
                    scales: {{ y: {{ beginAtZero: true }} }},
                    plugins: {{ legend: {{ display: false }} }}
                }}
            }});
        </script>
    </body>
    </html>
    """

    # --- Save the Report ---
    os.makedirs("reports", exist_ok=True)
    report_path = os.path.join("reports", f"report_{run_id}.html")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_template)
        
    print(f"✅ Report successfully generated: {report_path}")

if __name__ == "__main__":
    print("Initializing Report Generation...")
    generate_report()