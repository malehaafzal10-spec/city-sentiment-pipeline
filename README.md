# City Sentiment Monitoring Pipeline

what we have DONE today:
1. monitoring vader and evaluate: the file names for this files are in the branch staying with the numbers 06 and 07.
2. cloud DB: change all the files that need to ingest data to store it on MongoDB. The changed files are the one with numbers on the folder src. 
3. Dashboard specific for artifacts that allow us to see how much data we have collected!
4. Dashboard online for everyone now, you just have to run streamlit run app.py on staying branch.

Next Task: 
1. monitoring vader and evaluate: we need to store the sample for HDLP evaluation on the DB for the file to work.
2. Create a historical data folder and copy and modify the script 01a in order to collects 1 month of data from daily newsAPI 
3. After 01 is ready, create a similar script for 02a where we have to check if the articles are relevant with an LLM.
4. We have to judge with HDLP if the LLM is correctly identifying the relevant articles.
5. modify the files on src to fetch daily data into historical data and also use historical data base for the other scripts
6. Add the dashboard to Ucloud and create a public link
7. create a historical process for reddit too. 
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
