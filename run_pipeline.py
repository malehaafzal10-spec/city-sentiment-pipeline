"""
run_pipeline.py — Single entry point for the full City Sentiment pipeline.

Usage:
  python run_pipeline.py                        # full run (news + reddit)
  python run_pipeline.py --news-only            # news only (daily run)
  python run_pipeline.py --skip-llm             # skip LLM city verdicts
  python run_pipeline.py --dashboard            # regenerate dashboard only

Pipeline steps:
  1a. Ingest news        — 01a_ingest_daily_news.py
  1b. Ingest reddit      — 01b_ingest_weekly_reddit.py (full run only)
  2.  Store relevant     — 02a_store_relevant_docs.py (keyword + LLM filter + scrape)
  3.  Score              — 03_score.py (VADER)
  4.  Features           — 04_create_features.py (keyword dimensions + city aggregates)
  5.  Evaluate           — 05_evaluate_vader.py (F1, accuracy from human labels)
  6.  LLM Judge          — 06_llm_judge.py (Groq vs VADER cross-validation)
  7.  Monitor            — 07_monitor.py (drift detection + alerts)
  8.  LLM Verdicts       — llm_summary.py (optional city verdicts)
  9.  Dashboard          — dashboard.py (static HTML for GitHub Pages)
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

# Add src/ to path so all modules can be imported directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("pipeline")


def add_file_logger(run_id: str) -> str:
    """Also log to a file for artifact storage."""
    log_dir = os.path.join(os.getenv("PIPELINE_ARTIFACTS_DIR", "artifacts"), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"run_{run_id}.log")
    fh = logging.FileHandler(log_path)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s"))
    logging.getLogger().addHandler(fh)
    return log_path


def run_pipeline(skip_llm: bool = False, news_only: bool = False) -> dict:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    add_file_logger(run_id)

    results = {
        "run_id": run_id,
        "steps": {},
        "success": False,
        "mode": "news_only" if news_only else "full"
    }

    log.info("=" * 60)
    if news_only:
        log.info(f"CITY SENTIMENT PIPELINE — DAILY NEWS RUN | run_id={run_id}")
    else:
        log.info(f"CITY SENTIMENT PIPELINE — FULL RUN | run_id={run_id}")
    log.info("=" * 60)

    try:

        # ── STEP 1: INGEST ────────────────────────────────────────────────────
        # Import using importlib because filenames start with numbers
        from importlib import import_module

        if news_only:
            log.info("[1/8] Ingesting news articles (daily run)")
            news_mod = import_module("01a_ingest_daily_news")
            r = news_mod.run(run_id)
            results["steps"]["ingest"] = r
            log.info(f"      ✓ {r['total_docs']} news articles fetched")
        else:
            log.info("[1/8] Ingesting all sources — news + reddit (full run)")
            news_mod = import_module("01a_ingest_daily_news")
            r_news = news_mod.run(run_id)

            reddit_mod = import_module("01b_ingest_weekly_reddit")
            r_reddit = reddit_mod.run(run_id)

            total = r_news["total_docs"] + r_reddit["total_docs"]
            results["steps"]["ingest"] = {
                "run_id": run_id,
                "total_docs": total,
                "news_docs": r_news["total_docs"],
                "reddit_docs": r_reddit["total_docs"]
            }
            log.info(
                f"      ✓ {total} total documents fetched "
                f"(news={r_news['total_docs']}, reddit={r_reddit['total_docs']})"
            )

        # ── STEP 2: FILTER, SCRAPE, STORE ─────────────────────────────────────
        # Keyword pre-filter + Groq LLM relevance filter + BeautifulSoup scraping
        log.info("[2/8] Filtering relevance, scraping full text, storing processed docs")
        store_mod = import_module("02a_store_relevant_docs")
        r = store_mod.process_documents(run_id)
        results["steps"]["preprocess"] = r
        log.info(
            f"      ✓ {r['cleaned_count']} relevant documents stored "
            f"(groq_calls={r.get('metrics', {}).get('groq_calls', 0)}, "
            f"llm_dropped={r.get('metrics', {}).get('skipped_llm', 0)})"
        )

        # ── STEP 3: VADER SCORING ─────────────────────────────────────────────
        log.info("[3/8] Sentiment scoring with VADER")
        from importlib import import_module as _im
        score_mod = _im("03_score")
        r = score_mod.run(run_id)
        results["steps"]["score"] = r
        log.info(f"      ✓ {r['scored_count']} documents scored")

        # ── STEP 4: FEATURE ENGINEERING ───────────────────────────────────────
        # Keyword dimensions (crowding/cost/safety) + city-week aggregates
        log.info("[4/8] Feature engineering and city-week aggregation")
        features_mod = import_module("04_create_features")
        r = features_mod.run(run_id)
        results["steps"]["features"] = {
            "doc_features_count": r["doc_features_count"],
            "cities": len(r["city_aggregates"])
        }
        city_aggregates = r["city_aggregates"]
        log.info(
            f"      ✓ Features for {r['doc_features_count']} docs, "
            f"{len(city_aggregates)} city aggregates"
        )

        # ── STEP 5: EVALUATE VADER ────────────────────────────────────────────
        # F1, accuracy, precision, recall from human-labelled validation_samples
        log.info("[5/8] Model evaluation (F1 / accuracy)")
        evaluate_mod = import_module("05_evaluate_vader")
        eval_result = evaluate_mod.run(run_id)
        results["steps"]["evaluate"] = eval_result
        if "error" not in eval_result:
            log.info(
                f"      ✓ Accuracy={eval_result.get('accuracy', 0):.0%} "
                f"Macro F1={eval_result.get('macro_f1', 0):.0%} "
                f"(n={eval_result.get('total_samples', 0)})"
            )
        else:
            log.info(f"      — {eval_result['error']}")

        # ── STEP 6: LLM JUDGE ─────────────────────────────────────────────────
        # Groq cross-validates VADER scores on a random sample
        # Disagreed articles → validation_samples for human review
        log.info("[6/8] LLM Judge — Groq vs VADER cross-validation")
        judge_mod = import_module("06_llm_judge")
        judge_result = judge_mod.run(run_id)
        if not judge_result.get("skipped"):
            results["steps"]["llm_judge"] = {
                "total_judged": judge_result.get("total_judged", 0),
                "overall_agreement": judge_result.get("overall_agreement", 0),
                "city_agreement": judge_result.get("city_agreement", {})
            }
            log.info(
                f"      ✓ Judged {judge_result.get('total_judged', 0)} articles — "
                f"{judge_result.get('overall_agreement', 0):.0%} overall agreement"
            )
        else:
            log.info("      — LLM Judge skipped (no GROQ_API_KEY)")

        # ── STEP 7: MONITORING ────────────────────────────────────────────────
        # Drift detection, volume alerts, rolling average deviation
        log.info("[7/8] Monitoring and drift detection")
        monitor_mod = import_module("07_monitor")
        mon_result = monitor_mod.run(run_id)
        results["steps"]["monitor"] = {"alerts": mon_result["total_alerts"]}
        log.info(f"      ✓ {mon_result['total_alerts']} alerts generated")

        # ── STEP 8: LLM CITY VERDICTS (optional, skip on daily runs) ──────────
        if not skip_llm and not news_only:
            log.info("[+] LLM city verdicts (optional)")
            from llm_summary import run as llm_run
            from pymongo import MongoClient

            MONGO_URI = os.getenv("MONGO_URI")
            DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

            city_texts = {}
            if MONGO_URI:
                client = MongoClient(MONGO_URI)
                db = client[DB_NAME]
                for agg in city_aggregates:
                    city = agg["city"]
                    docs = list(db["processed_documents"].find(
                        {"city": city, "run_id": run_id},
                        {"text": 1}
                    ).limit(10))
                    city_texts[city] = [d.get("text", "") for d in docs]
                client.close()

            llm_result = llm_run(run_id, city_aggregates, city_texts)
            verdicts = llm_result.get("verdicts", {})
            results["steps"]["llm_verdicts"] = {"count": len(verdicts)}
            log.info(f"      ✓ {len(verdicts)} city verdicts generated")
        else:
            if news_only:
                log.info("[+] Skipping LLM city verdicts — daily run")
            else:
                log.info("[+] Skipping LLM city verdicts — --skip-llm flag")

        # ── DASHBOARD ─────────────────────────────────────────────────────────
        log.info("[+] Generating static dashboard for GitHub Pages")
        from dashboard import run as dash_run
        dash_result = dash_run(run_id)
        results["steps"]["dashboard"] = dash_result
        log.info(f"      ✓ Dashboard → docs/index.html ({dash_result.get('cities_count', 0)} cities)")

        results["success"] = True
        log.info("=" * 60)
        if news_only:
            log.info(f"DAILY NEWS RUN COMPLETE ✓ | run_id={run_id}")
        else:
            log.info(f"FULL PIPELINE COMPLETE ✓ | run_id={run_id}")
        log.info("Run dashboard: streamlit run app.py")
        log.info("=" * 60)

    except Exception as e:
        log.error(f"PIPELINE FAILED: {e}", exc_info=True)
        results["error"] = str(e)

    # Save run summary to artifacts
    summary_dir = os.path.join(os.getenv("PIPELINE_ARTIFACTS_DIR", "artifacts"), "logs")
    os.makedirs(summary_dir, exist_ok=True)
    with open(os.path.join(summary_dir, f"summary_{run_id}.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)

    return results


if __name__ == "__main__":
    if "--dashboard" in sys.argv:
        sys.path.insert(0, "src")
        from dashboard import run as dash_run
        dash_run()
        sys.exit(0)

    news_only = "--news-only" in sys.argv
    skip_llm = "--skip-llm" in sys.argv

    result = run_pipeline(skip_llm=skip_llm, news_only=news_only)
    sys.exit(0 if result["success"] else 1)