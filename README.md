# City Sentiment Pipeline

A Python data pipeline that tracks real-time travel sentiment across thousands of cities worldwide using Reddit data, LLM relevance filtering, aspect-based sentiment scoring, and daily aggregation in MongoDB.

## 🌍 Live Apps
- **Public Explorer:** https://city-sentiment-pipeline-touristapp.streamlit.app/
- **Monitoring Dashboard:** https://city-sentiment-pipeline-dashboard.streamlit.app/

## What this project does
- Fetches daily r/travel posts from Reddit (targeting n-2 date to allow comment accumulation)
- Filters to travel-relevant content using LLM relevance classification (Groq/LLaMA)
- Fetches top 20 comments per relevant post
- Scores sentiment at aspect level (Food & Dining, Safety, Cost, Crowds, Accommodation etc.)
- Aggregates daily aspect-level scores per city and country
- Stores pipeline artifacts and run IDs for full traceability
- Provides a public-facing city explorer and an internal monitoring dashboard

## Pipeline flow

### Reddit Pipeline (R01–R05)
| Step | Script | Runs on | Description |
|------|--------|---------|-------------|
| R01 | `src/r01_fetch_reddit.py` | Windows Task Scheduler (19:00) | Fetch r/travel posts from n-2 date |
| R02 | `src/r02_save_relevant.py` | GitHub Actions (19:30 Danish) | LLM relevance filter on posts |
| R03 | `src/r03_fetch_comments.py` | Windows Task Scheduler (20:30) | Fetch top 20 comments per relevant post |
| R04 | `src/r04_analice_sentiment.py` | GitHub Actions (21:00 Danish) | LLM relevance + aspect scoring on comments |
| R05 | `src/r05_aggregate.py` | GitHub Actions (21:00 Danish) | Aggregate aspect scores per city |

### News Pipeline
| Step | Script | Description |
|------|--------|-------------|
| S01 | `src/s01a_ingest_daily_news.py` | Ingest daily news articles from NewsAPI |

## Run ID system
Every daily run is assigned a unique run ID:
- `run_YYYYMMDD_local` — data collected locally (on/before June 1 2026)
- `run-YYYYMMDD-AUTO` — data collected via automated pipeline (after June 1 2026)

## Data storage (MongoDB)
Default DB: `travel_pipeline_db`

### Reddit collections
- `r01_reddit_posts_raw_final` — raw posts fetched by R01
- `reddit_relevant` — posts that passed LLM relevance filter (R02)
- `reddit_comments_final` — comments fetched by R03
- `reddit_comments_relevant` — comments that passed LLM scoring (R04)
- `reddit_aggregated` — aspect-level aggregated scores (R05)
- `reddit_cleaned` — cleaned aggregated data

### News collections
- `raw_documents_historical` — raw news articles
- `news_alert` — news documents that triggered alerts

## Project structure
```text
city-sentiment-pipeline/
├── src/                         # Pipeline scripts (R01–R05, news, monitoring)
├── scheduler/                   # Windows Task Scheduler bat files
│   ├── run_r01.bat
│   └── run_r03.bat
├── .github/workflows/           # GitHub Actions workflows
│   ├── r02_pipeline.yml
│   ├── r04_r05_pipeline.yml
│   └── daily_news.yml
├── artifacts/                   # Local pipeline artifacts and backups
├── config/                      # Configuration files
├── public_app.py                # Public-facing city sentiment explorer
├── monitoring_dashboard.py      # Internal pipeline monitoring dashboard
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## Quick start (local)

### 1) Prerequisites
- Python 3.10+
- MongoDB Atlas instance
- `.env` file with:
```env
MONGO_URI=your_mongodb_atlas_uri
MONGO_DB_NAME=travel_pipeline_db
GROQ_API_KEY=your_groq_key
NEWSAPI_KEY=your_newsapi_key
```

### 2) Install
```bash
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
playwright install chromium
```

### 3) Run individual pipeline steps
```bash
python src/r01_fetch_reddit.py
python src/r02_save_relevant.py
python src/r03_fetch_comments.py --date YYYYMMDD
python src/r04_analice_sentiment.py
python src/r05_aggregate.py
```

### 4) Run the dashboards
```bash
streamlit run public_app.py
streamlit run monitoring_dashboard.py
```

## GitHub Actions secrets required
- `MONGO_URI`
- `MONGO_DB_NAME`
- `GROQ_API_KEY`

## Team
- Karolina Bohdan
- Faraiba Farnan
- Maleha Afzal
- Cristian Smoilis
