# City Sentiment Monitoring Pipeline

## 🗄️ Data Architecture (MongoDB)

This project implements a **Medallion Architecture** (Bronze, Silver, Gold layers) using **MongoDB** to handle our unstructured text data. The data flows through different collections within the `travel_pipeline_db` database, progressively becoming cleaner and more enriched.

### 🥉 Bronze Layer: Raw Data
**Collections:** `raw_documents` (Daily) & `raw_documents_historical` (Backfill)

This is the landing zone. It stores the exact, unfiltered data pulled straight from our sources (NewsAPI, Reddit) before any heavy processing occurs.

| Field | Type | Description |
| :--- | :--- | :--- |
| `doc_id` | String | A unique SHA-256 hash generated from the source and URL to prevent exact duplicates. |
| `source` | String | Where the data came from (e.g., `"news"`, `"reddit"`). |
| `city` | String | The destination city being searched (e.g., `"Paris"`, `"Tokyo"`). |
| `title` | String | The article's headline. |
| `description` | String | A short summary snippet provided by the API. |
| `text` | String | A rough concatenation of the title, description, and truncated API content. |
| `url` | String | The direct URL to the original article. |
| `published_at` | String | The original publication timestamp (ISO 8601). |
| `ingestion_time` | String | The exact UTC time the pipeline fetched the data. |
| `run_id` | String | The execution ID linking this document to a specific pipeline run. |

---

### 🥈 Silver Layer: Processed & Scraped
**Collection:** `processed_documents`

This collection holds our clean, filtered, and enriched dataset. Documents only enter this layer if they pass both a strict Keyword pre-filter and an LLM relevance check (Gemini/Groq). It also contains the **full scraped text** of the articles.

| Field | Type | Description |
| :--- | :--- | :--- |
| `text` | String | The **fully scraped, cleaned, deduplicated, and VADER-safe** text of the article. |
| `full_text_scraped` | Boolean | `true` if BeautifulSoup successfully scraped the webpage; `false` if it fell back to the API description. |
| `text_length` | Integer | Character count of the cleaned text. |
| `llm_relevant` | Boolean | `true` if the LLM deemed the article genuinely about travel. |
| `llm_reason` | String | The brief explanation from the LLM justifying its decision (used for traceability/auditing). |
| `model_used` | String | Tracks which LLM made the relevance decision (`"gemini"`, `"groq"`, or `"none"`). |
| `processed_time` | String | UTC timestamp of when the processor script finished handling the document. |
| *(Inherited)* | Various | Inherits `doc_id`, `source`, `city`, `title`, `url`, `published_at`, and `run_id` from the Bronze layer. |

---

### 🛠️ MLOps Tracking: Pipeline Artifacts
**Collection:** `pipeline_artifacts`

Instead of just logging to flat files, the pipeline stores "snapshots" of its execution directly in the database. This acts as our MLOps telemetry layer to track API limits, failure rates, and model performance over time.

| Field | Type | Description |
| :--- | :--- | :--- |
| `run_id` | String | The execution ID matching the ingested documents. |
| `artifact_type` | String | Identifies the pipeline stage (e.g., `"raw_ingestion"`, `"processed_scraped_docs"`). |
| `timestamp` | Datetime | Native MongoDB datetime object marking the end of the run. |
| `document_count` | Integer | Total number of documents handled in this specific batch. |
| `metrics` | Object | Telemetry dictionary containing exact counts for API successes, fallbacks, scraped pages, and drops. |
| `payload` | Array | The entire JSON payload of documents processed in that run, embedded for full state reproducibility. |

---


Next Task: 

1. Historical Data:
  1.1 process the historical on newsAPI for process number 02, 03 and 04.
  1.2 Process reddit historical data for process 03 and 04.
Process numbers are in the folder src (the ones that run daily) and the "file numbers" are s01, s02, s03 and s04.
2. Daily execution: check what artifacts are necessesary. 
3. We have to judge with HDLP if the LLM is correctly identifying the relevant articles.
4. create a public link for the dashboard unce all the historical data is processed.
5. monitoring vader and evaluate: we need to store the sample for HDLP evaluation on the DB for the file to work.
Future Ideas:
5. llm summary . py (maybe for semester project)
6. then monitor also (maybe for semester project)


M6 — Data Engineering and Machine Learning Operations in Business | AAU F2026

Tracks how travellers talk about 8 European cities using NewsAPI.
Scores sentiment weekly, detects drift, and publishes a live dashboard.

run_20260406_135639
## Quick start

```bash
# 1. Copy and fill in your API key
cp .env.example .env
# open .env and set NEWSAPI_KEY=your_key

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate   # Mac/Linux
# venv\Scripts\activate    # Windows

# 3. Install packages
pip install -r requirements.txt

# 4. Run the pipeline
python run_pipeline.py

# 5. Open the dashboard
# Open docs/index.html in your browser
```

## Run with Docker
```bash
docker compose build
docker compose up
```

## GitHub Actions (automatic weekly runs)
1. Push to GitHub
2. Add NEWSAPI_KEY as a repository secret (Settings → Secrets → Actions)
3. Enable GitHub Pages (Settings → Pages → branch: gh-pages)
4. Trigger manually: Actions tab → City Sentiment Pipeline → Run workflow

## When Reddit is approved
Set REDDIT_ENABLED=true in .env and add your credentials.
The pipeline will automatically use both sources.

## Project structure
```
src/
  db.py           — SQLite schema
  ingest.py       — NewsAPI + Reddit (when enabled)
  preprocess.py   — Clean + relevance filter
  features.py     — Keyword feature engineering
  score.py        — VADER sentiment scoring
  aggregate.py    — Weekly city metrics
  monitor.py      — Drift detection
  llm_summary.py  — Optional LLM verdicts
  dashboard.py    — HTML dashboard generation
run_pipeline.py   — Single entry point
```
