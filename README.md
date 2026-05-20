# City Sentiment Pipeline

A Python data pipeline that tracks travel sentiment for major European cities using news content, LLM relevance filtering, VADER sentiment scoring, and weekly feature aggregation in MongoDB.

## https://city-travel-sentiment-live-dashboard.streamlit.app/

## What this project does

- Ingests daily city-related news articles
- Filters to travel-relevant content (keyword pre-filter + LLM classification)
- Scores sentiment with VADER
- Builds weekly city-level aggregates (sentiment, crowding/cost/safety signals)
- Stores pipeline artifacts and metrics for traceability
- Provides Streamlit dashboards for monitoring and exploration

## Target cities

Configured in `config/cities.json`:

- Paris
- Rome
- Barcelona
- Lisbon
- Amsterdam
- Prague
- Athens
- London

## Pipeline flow

Main orchestrator: `run_pipeline.py`

Executed steps (in order):

1. `src/s01a_ingest_daily_news.py`
2. `src/s02_store_relevant_docs.py`
3. `src/s03_score.py`
4. `src/s04_create_features.py`

Optional monitoring dashboard exists in `src/dashboard_db_data.py`.

## Data storage (MongoDB)

Default DB: `travel_pipeline_db`

Primary collections used by the core pipeline:

- `raw_documents_historical`
- `processed_documents`
- `scored_documents`
- `document_features`
- `city_weekly_features`
- `pipeline_artifacts`

You can view our data monitoring dashboard here: https://city-sentiment-data-dashboard.streamlit.app/

Additional collections used by dashboard/monitoring flows include:

- `monitoring_alerts`
- `user_feedback`

## Project structure

```text
city-sentiment-pipeline/
├── src/                         # Pipeline steps and utility scripts
├── preprocess/                  # Historical/backfill preprocessing scripts
├── human_in_the_loop/           # Manual evaluation workflows and outputs
├── config/cities.json           # City + keyword configuration
├── app.py                       # Main Streamlit city sentiment app
├── run_pipeline.py              # Pipeline orchestrator entrypoint
├── requirements.txt             # Python dependencies
├── Dockerfile
└── docker-compose.yml
```

## Quick start (local)

### 1) Prerequisites

- Python 3.10+
- MongoDB instance (local or Atlas)
- .env file with API keys needed:
  MONGO_URI: Database Access URI
  MONGO_DB_NAME: Database User
  NEWSAPI_KEY: NewsAPI Key
  GEMINI_API_KEY: GEMINI API KEY 
  GROQ_API_KEY: GROQ API KEY 
  HF_TOKEN: Hugging face token
  HF_REPO_ID: Hugging face repo ID

### 2) Install

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3) Configure environment

Create a `.env` file in the repository root.

Minimum:

```env
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=travel_pipeline_db
NEWSAPI_KEY=<your_newsapi_key>
```

Optional (for LLM relevance filtering):

```env
GROQ_API_KEY=<your_groq_key>
GEMINI_API_KEY=<your_gemini_key>
#--- rest API KEY here ---
```

### 4) Run the pipeline

```bash
python run_pipeline.py
```

### 5) Run the dashboard

```bash
streamlit run app.py
```

## Docker
### 1) Prerequisites


- .env file with API keys needed:
  MONGO_URI: Database Access URI
  MONGO_DB_NAME: Database User
  NEWSAPI_KEY: NewsAPI Key
  GEMINI_API_KEY: GEMINI API KEY 
  GROQ_API_KEY: GROQ API KEY 
  HF_TOKEN: Hugging face token
  HF_REPO_ID: Hugging face repo ID
  
`docker-compose.yml` defines a `pipeline` service that runs the orchestrator.

```bash
docker compose build
docker compose up
```

## GitHub Actions

Workflows are available in `.github/workflows/`:

- `daily_news.yml`
- `pipeline.yml`

To run in GitHub Actions, set required repository secrets (for example `MONGO_URI`, `NEWSAPI_KEY`, and optional LLM keys).

## Notes

- The orchestrator currently runs the 4 core steps listed above.
- Historical/backfill scripts are in `preprocess/` and can be run separately.

## Team

- Karolina Bohdan
- Faraiba Farnan
- Maleha Afzal
- Cristian Smoilis
