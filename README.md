# City Sentiment Monitoring Pipeline
M6 — Data Engineering and Machine Learning Operations in Business | AAU F2026

Tracks how travellers talk about 8 European cities using NewsAPI.
Scores sentiment weekly, detects drift, and publishes a live dashboard.

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
