# 🏙️ City Sentiment Pipeline

> **Track how travellers talk about European cities — automatically.**  
> Ingests news and Reddit data, scores sentiment with VADER, detects drift, and publishes a live Streamlit dashboard.

*M6 — Data Engineering and Machine Learning Operations in Business | AAU F2026*

---

## 📌 Overview

The City Sentiment Pipeline is an end-to-end MLOps project that monitors public sentiment toward **8 European cities** using data from **NewsAPI** and **Reddit**. Articles are scraped, filtered for relevance by an LLM, scored with VADER sentiment analysis, aggregated weekly, and surfaced through an interactive dashboard.

Data flows through a **Medallion Architecture** (Bronze → Silver → Gold) stored in **MongoDB**, with full pipeline telemetry tracked as artifacts.

---

## ✨ Features

- 📰 **Multi-source ingestion** — NewsAPI (live) + Reddit (when enabled)
- 🤖 **LLM relevance filtering** — Gemini / Groq to discard non-travel articles
- 🧹 **Full-text scraping** — BeautifulSoup scrapes article body; falls back to API snippet
- 💬 **VADER sentiment scoring** — per article and aggregated weekly per city
- 📊 **Drift detection** — monitors sentiment shifts over time
- 🗄️ **Medallion Architecture** on MongoDB — Bronze / Silver / Gold layers
- 🏃 **Human-in-the-Loop (HITL)** — sample evaluation workflow for LLM quality checks
- 🐳 **Docker support** — one-command reproducible runs
- ⚙️ **GitHub Actions** — automated weekly scheduled runs + manual trigger

---

## 🗂️ Project Structure

```
city-sentiment-pipeline/
├── src/                        # Core pipeline modules (daily execution)
│   ├── db.py                   # MongoDB schema and connection helpers
│   ├── ingest.py               # NewsAPI + Reddit ingestion
│   ├── preprocess.py           # Cleaning, scraping, LLM relevance filter
│   ├── features.py             # Keyword feature engineering
│   ├── score.py                # VADER sentiment scoring
│   ├── aggregate.py            # Weekly city-level metrics
│   ├── monitor.py              # Drift detection
│   ├── llm_summary.py          # Optional LLM verdict summaries
│   └── dashboard.py            # Dashboard data preparation
├── preprocess/                 # Preprocessing utilities
├── human_in_the_loop/          # HITL evaluation scripts
├── config/                     # Configuration files
├── artifacts/                  # Local pipeline artifact snapshots
├── reports/                    # Generated reports
├── legacy/                     # Archived earlier versions
├── .github/workflows/          # GitHub Actions CI/CD
├── .streamlit/                 # Streamlit theme config
├── app.py                      # Streamlit dashboard app
├── run_pipeline.py             # Single entry point for the full pipeline
├── refilter_groq.py            # Re-run LLM filtering with Groq
├── track_artifacts.py          # MLOps artifact tracking
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## 🗄️ Data Architecture (MongoDB Medallion)

All data lives in the `travel_pipeline_db` database, progressing through three layers.

### 🥉 Bronze — Raw Ingestion

**Collections:** `raw_documents` (daily) · `raw_documents_historical` (backfill)

The landing zone. Stores unfiltered data exactly as received from NewsAPI and Reddit.

| Field | Description |
|---|---|
| `doc_id` | SHA-256 hash of source + URL — prevents exact duplicates |
| `source` | `"news"` or `"reddit"` |
| `city` | Target city (e.g. `"Paris"`, `"Tokyo"`) |
| `title` | Article headline |
| `description` | Short API-provided snippet |
| `text` | Rough concatenation of title + description + truncated content |
| `url` | Link to original article |
| `published_at` | Publication timestamp (ISO 8601) |
| `ingestion_time` | UTC time the pipeline fetched the document |
| `run_id` | Links document to a specific pipeline execution |

### 🥈 Silver — Processed & Scraped

**Collection:** `processed_documents`

Clean, filtered, and enriched documents. Only articles that pass both a keyword pre-filter **and** LLM relevance check reach this layer.

| Field | Description |
|---|---|
| `text` | Fully scraped, cleaned, deduplicated, VADER-safe article text |
| `full_text_scraped` | `true` if BeautifulSoup succeeded; `false` if fell back to API snippet |
| `text_length` | Character count of cleaned text |
| `llm_relevant` | `true` if LLM judged article genuinely travel-related |
| `llm_reason` | LLM's brief explanation (used for auditing / HITL) |
| `model_used` | Which model made the decision: `"gemini"`, `"groq"`, or `"none"` |
| `processed_time` | UTC timestamp of processing |
| *(+ inherited)* | `doc_id`, `source`, `city`, `title`, `url`, `published_at`, `run_id` |

### 🥇 Gold — Aggregated Metrics

Weekly sentiment scores, drift signals, and city-level summaries consumed by the dashboard.

### 🛠️ MLOps Tracking — Pipeline Artifacts

**Collection:** `pipeline_artifacts`

Telemetry snapshots stored in the database for every pipeline run.

| Field | Description |
|---|---|
| `run_id` | Execution ID linking to processed documents |
| `artifact_type` | Pipeline stage tag (e.g. `"raw_ingestion"`, `"processed_scraped_docs"`) |
| `timestamp` | Native MongoDB datetime |
| `document_count` | Documents handled in the batch |
| `metrics` | API successes, fallbacks, scrape counts, drops |
| `payload` | Full JSON payload of the run for reproducibility |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- MongoDB running locally or a MongoDB Atlas connection string
- A [NewsAPI](https://newsapi.org/) key

### Local Setup

```bash
# 1. Clone the repo
git clone https://github.com/malehaafzal10-spec/city-sentiment-pipeline.git
cd city-sentiment-pipeline

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate      # Mac / Linux
# venv\Scripts\activate       # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env and set:
#   NEWSAPI_KEY=your_newsapi_key
#   MONGO_URI=your_mongodb_connection_string

# 5. Run the full pipeline
python run_pipeline.py

# 6. Launch the dashboard
streamlit run app.py
```

### Docker

```bash
docker compose build
docker compose up
```

---

## ⚙️ GitHub Actions (Automated Weekly Runs)

1. Push the repo to GitHub.
2. Add `NEWSAPI_KEY` (and optionally `MONGO_URI`) as **repository secrets** under *Settings → Secrets → Actions*.
3. Enable **GitHub Pages** under *Settings → Pages → branch: gh-pages* for the dashboard.
4. Trigger manually: *Actions tab → City Sentiment Pipeline → Run workflow*

The workflow runs on a weekly schedule automatically after the first manual trigger.

---

## 📡 Reddit Integration

Reddit ingestion is disabled by default pending API approval.

To enable it, set the following in your `.env`:

```env
REDDIT_ENABLED=true
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=your_user_agent
```

The pipeline will automatically blend Reddit posts with NewsAPI articles once credentials are present.

---

## 🧪 Human-in-the-Loop (HITL) Evaluation

The `human_in_the_loop/` folder contains scripts for sampling LLM-labelled articles and manually verifying relevance decisions. Evaluation samples are stored back to MongoDB so the workflow is fully traceable and repeatable.

To run an evaluation session:

```bash
python human_in_the_loop/evaluate.py
```

---

## 🧰 Tech Stack

| Layer | Technology |
|---|---|
| Ingestion | NewsAPI, PRAW (Reddit) |
| Scraping | BeautifulSoup4, Requests |
| LLM Filtering | Google Gemini, Groq |
| Sentiment | VADER (NLTK) |
| Database | MongoDB |
| Dashboard | Streamlit |
| Containerisation | Docker, Docker Compose |
| CI/CD | GitHub Actions |
| Language | Python 3.10+ |

---

## 📄 License

This project was developed as part of the **M6 — Data Engineering and MLOps in Business** module at **Aalborg University (AAU), Spring 2026**.

---

## Contributors:

- **Karolina Bohdan** 
- **Faraiba Farnan**
- **Maleha Afzal**
- **Cristian Smoilis**

*Built with ☕ and a lot of sentiment.*