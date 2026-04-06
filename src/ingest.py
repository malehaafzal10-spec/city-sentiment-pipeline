"""
ingest.py — Step 2: Fetch raw text from NewsAPI and Reddit via Apify.
Full article text is scraped only for articles that pass relevance filtering.
Reddit uses Apify Reddit Scraper Lite — no Reddit API approval needed.
"""
 
import os
import json
import time
import hashlib
import logging
from datetime import datetime, timezone
 
import requests
from newsapi import NewsApiClient
from dotenv import load_dotenv
from db import get_connection, init_db
 
load_dotenv()
 
ARTIFACTS_DIR = os.getenv("PIPELINE_ARTIFACTS_DIR", "artifacts")
 
logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("ingest")
 
IRRELEVANT_PATTERNS = [
    "airline", "luxury seat", "business class", "first class seat",
    "flight deal", "airfare", "fare sale", "seat upgrade",
    "stock market", "share price", "quarterly earnings", "revenue report",
    "ipo", "merger", "acquisition", "hedge fund",
    "premier league", "champions league", "match result", "transfer window",
    "football club", "rugby", "cricket match",
    "weather forecast", "temperature forecast",
    "local election", "city council", "municipal", "residential",
    "real estate listing", "property market", "mortgage rate",
]
 
RELEVANT_PATTERNS = [
    "tourist", "tourism", "travel", "traveller", "traveler",
    "visit", "visitor", "vacation", "holiday", "trip",
    "backpack", "sightseeing", "hotel", "hostel", "airbnb",
    "crowded", "crowds", "overtourism", "overrun",
    "expensive", "affordable", "cheap", "overpriced", "value",
    "safe", "unsafe", "pickpocket", "scam",
    "recommend", "avoid", "worth it", "overrated", "must see",
    "things to do", "best time to visit", "travel guide",
    "local tips", "hidden gem", "tourist trap",
]
 
 
def is_likely_relevant(title: str, snippet: str, city: str) -> bool:
    """Quick check on title + snippet BEFORE scraping full text."""
    combined = f"{title} {snippet}".lower()
    for pattern in IRRELEVANT_PATTERNS:
        if pattern in combined:
            return False
    for pattern in RELEVANT_PATTERNS:
        if pattern in combined:
            return True
    if city.lower() in combined:
        return True
    return False
 
 
def scrape_full_text(url: str) -> str:
    """Fetch full article text from URL using newspaper3k."""
    try:
        from newspaper import Article
        article = Article(url)
        article.download()
        article.parse()
        text = article.text.strip()
        if len(text) > 100:
            return text
        return ""
    except Exception:
        return ""
 
 
def load_config():
    with open("config/cities.json") as f:
        return json.load(f)
 
 
def make_doc_id(source: str, url: str) -> str:
    return hashlib.sha256(f"{source}:{url}".encode()).hexdigest()[:16]
 
 
def fetch_news(config: dict, run_id: str) -> list:
    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key:
        log.info("[News] No NEWSAPI_KEY set — skipping")
        return []
 
    newsapi = NewsApiClient(api_key=api_key)
    all_docs = []
    scraped_count = 0
    skipped_irrelevant = 0
 
    for city in config["cities"]:
        city_name = city["name"]
        log.info(f"[News] Fetching articles for {city_name}")
 
        for keyword in city["keywords"]:
            try:
                response = newsapi.get_everything(
                    q=keyword,
                    language="en",
                    sort_by="publishedAt",
                    page_size=20
                )
                for article in response.get("articles", []):
                    url = article.get("url", "")
                    title = article.get("title", "") or ""
                    description = article.get("description", "") or ""
                    snippet = f"{title}. {description}"
 
                    # Quick relevance check BEFORE scraping
                    if not is_likely_relevant(title, description, city_name):
                        skipped_irrelevant += 1
                        continue
 
                    # Only scrape full text for relevant articles
                    full_text = scrape_full_text(url)
                    scraped_count += 1
 
                    # Use full text if scraped, otherwise title + description
                    text = full_text if full_text else snippet.strip()
 
                    all_docs.append({
                        "doc_id": make_doc_id("news", url),
                        "source": "news",
                        "city": city_name,
                        "title": title,
                        "text": text,
                        "published_at": article.get("publishedAt", ""),
                        "url": url,
                        "ingestion_time": datetime.now(timezone.utc).isoformat(),
                        "run_id": run_id,
                        "full_text_scraped": bool(full_text)
                    })
 
            except Exception as e:
                log.warning(f"[News] Error fetching '{keyword}': {e}")
 
    log.info(
        f"[News] {len(all_docs)} relevant articles | "
        f"Full text scraped: {scraped_count} | "
        f"Skipped before scraping: {skipped_irrelevant}"
    )
    return all_docs
 
 
def fetch_reddit_apify(config: dict, run_id: str) -> list:
    APIFY_TOKEN = os.getenv("APIFY_TOKEN")
    if not APIFY_TOKEN:
        log.info("[Reddit/Apify] No APIFY_TOKEN set — skipping")
        return []
 
    all_docs = []
 
    for city in config["cities"]:
        city_name = city["name"]
        log.info(f"[Reddit/Apify] Fetching posts for {city_name}")
 
        try:
            response = requests.post(
                f"https://api.apify.com/v2/acts/trudax~reddit-scraper-lite/runs?token={APIFY_TOKEN}",
                json={
                    "searches": [
                        f"{city_name} travel",
                        f"visit {city_name}"
                    ],
                    "searchPosts": True,
                    "searchComments": False,
                    "maxItems": 25,
                    "sort": "new"
                },
                timeout=30
            )
 
            run_data = response.json()
            apify_run_id = run_data.get("data", {}).get("id")
 
            if not apify_run_id:
                log.warning(f"[Reddit/Apify] Could not start run for {city_name}: {run_data}")
                continue
 
            log.info(f"[Reddit/Apify] Waiting for results for {city_name}...")
            succeeded = False
            for _ in range(45):
                time.sleep(2)
                status_resp = requests.get(
                    f"https://api.apify.com/v2/actor-runs/{apify_run_id}?token={APIFY_TOKEN}",
                    timeout=10
                )
                status = status_resp.json().get("data", {}).get("status", "")
                if status == "SUCCEEDED":
                    succeeded = True
                    break
                elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
                    log.warning(f"[Reddit/Apify] Run {status} for {city_name}")
                    break
 
            if not succeeded:
                log.warning(f"[Reddit/Apify] Skipping {city_name} — run did not succeed")
                continue
 
            items_resp = requests.get(
                f"https://api.apify.com/v2/actor-runs/{apify_run_id}/dataset/items?token={APIFY_TOKEN}",
                timeout=30
            )
            items = items_resp.json()
 
            if not isinstance(items, list):
                continue
 
            for item in items:
                url = item.get("url", "") or item.get("id", "") or ""
                title = item.get("title", "") or ""
                # Reddit already gives full text — no scraping needed
                text = item.get("body", "") or item.get("selftext", "") or title
 
                all_docs.append({
                    "doc_id": make_doc_id("reddit", url),
                    "source": "reddit",
                    "city": city_name,
                    "title": title,
                    "text": text,
                    "published_at": item.get("createdAt", "") or item.get("created", ""),
                    "url": url,
                    "ingestion_time": datetime.now(timezone.utc).isoformat(),
                    "run_id": run_id,
                    "full_text_scraped": False
                })
 
            log.info(f"[Reddit/Apify] Got {len(items)} posts for {city_name}")
 
        except Exception as e:
            log.warning(f"[Reddit/Apify] Error for {city_name}: {e}")
 
    log.info(f"[Reddit/Apify] Total: {len(all_docs)} posts")
    return all_docs
 
 
def save_raw_artifacts(news_docs: list, reddit_docs: list, run_id: str):
    """Save only relevant articles with full text as artifacts."""
    raw_dir = os.path.join(ARTIFACTS_DIR, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y_%m_%d")
 
    if news_docs:
        path = os.path.join(raw_dir, f"news_{date_str}.json")
        with open(path, "w") as f:
            json.dump(news_docs, f, indent=2)
        log.info(f"[Artifacts] Saved {len(news_docs)} relevant news articles → {path}")
 
    if reddit_docs:
        path = os.path.join(raw_dir, f"reddit_{date_str}.json")
        with open(path, "w") as f:
            json.dump(reddit_docs, f, indent=2)
        log.info(f"[Artifacts] Saved {len(reddit_docs)} reddit posts → {path}")
 
 
def save_to_db(docs: list):
    conn = get_connection()
    inserted = skipped = 0
    for doc in docs:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO raw_documents
                (doc_id, source, city, title, text, published_at, url, ingestion_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc["doc_id"], doc["source"], doc["city"],
                doc["title"], doc["text"], doc["published_at"],
                doc["url"], doc["ingestion_time"]
            ))
            if conn.execute("SELECT changes()").fetchone()[0] > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            log.warning(f"[DB] Failed to insert {doc.get('doc_id')}: {e}")
    conn.commit()
    conn.close()
    log.info(f"[DB] Inserted {inserted} new, skipped {skipped} duplicates")
 
 
def run(run_id: str, news_only: bool = False) -> dict:
    log.info(f"=== STEP 2: INGEST | run_id={run_id} | mode={'news_only' if news_only else 'full'} ===")
    init_db()
    config = load_config()
 
    news_docs = fetch_news(config, run_id)
 
    if news_only:
        log.info("[Ingest] News-only mode — skipping Reddit/Apify")
        reddit_docs = []
    else:
        reddit_docs = fetch_reddit_apify(config, run_id)
 
    all_docs = news_docs + reddit_docs
    save_raw_artifacts(news_docs, reddit_docs, run_id)
    save_to_db(all_docs)
 
    log.info(f"[Ingest] Complete — {len(all_docs)} total documents")
    return {"run_id": run_id, "total_docs": len(all_docs)}
 
 
if __name__ == "__main__":
    run(datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))