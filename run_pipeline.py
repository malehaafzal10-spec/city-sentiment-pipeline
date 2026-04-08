"""
run_pipeline.py — Single entry point for the full City Sentiment pipeline.
 
Usage:
  python run_pipeline.py                        # full run (news + reddit)
  python run_pipeline.py --news-only            # news only (daily run)
  python run_pipeline.py --skip-llm             # skip LLM verdicts
  python run_pipeline.py --dashboard            # regenerate dashboard only
"""
 
import os
import sys
import json
import logging
from datetime import datetime, timezone
 
from dotenv import load_dotenv
 
load_dotenv()
 
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
 
logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("pipeline")
 
 
def add_file_logger(run_id: str) -> str:
    log_dir = os.path.join(os.getenv("PIPELINE_ARTIFACTS_DIR", "artifacts"), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"run_{run_id}.log")
    fh = logging.FileHandler(log_path)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s"))
    logging.getLogger().addHandler(fh)
    return log_path
 
 
def run_pipeline(skip_llm: bool = False, news_only: bool = False) -> dict:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_path = add_file_logger(run_id)
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
        from db import init_db
        init_db()
 
        # Step 2: Ingest
        if news_only:
            log.info("[1/7] Ingesting news data only (daily run)")
        else:
            log.info("[1/7] Ingesting data from all sources (full run)")
 
        from ingest import run as ingest_run
        r = ingest_run(run_id, news_only=news_only)
        results["steps"]["ingest"] = r
        log.info(f"      ✓ {r['total_docs']} documents fetched")
 
        # Step 4: Preprocess
        log.info("[2/7] Preprocessing and filtering")
        from preprocess import run as preprocess_run
        r = preprocess_run(run_id)
        results["steps"]["preprocess"] = r
        log.info(f"      ✓ {r['cleaned_count']} documents kept after filtering")
 
        # Step 5: Features
        log.info("[3/7] Feature engineering")
        from features import run as features_run
        r = features_run(run_id)
        results["steps"]["features"] = {"doc_count": r["doc_features_count"]}
        log.info(f"      ✓ Features extracted for {r['doc_features_count']} documents")
 
        # Step 6: Score
        log.info("[4/7] Sentiment scoring")
        from score import run as score_run
        r = score_run(run_id)
        results["steps"]["score"] = r
        log.info(f"      ✓ {r['scored_count']} documents scored")
 
        # Step 7: Aggregate
        log.info("[5/7] Weekly aggregation")
        from aggregate import run as agg_run
        agg_result = agg_run(run_id)
        city_metrics = agg_result["city_metrics"]
        results["steps"]["aggregate"] = {"cities": len(city_metrics)}
        log.info(f"      ✓ Metrics for {len(city_metrics)} cities")
 
        # Step 8: LLM verdicts (skipped on daily runs)
        verdicts = {}
        if not skip_llm and not news_only:
            log.info("[6/7] LLM verdicts (optional)")
            from llm_summary import run as llm_run
            from db import get_connection
            conn = get_connection()
            city_texts = {}
            for m in city_metrics:
                rows = conn.execute(
                    "SELECT clean_text FROM cleaned_documents WHERE city = ? AND run_id = ? LIMIT 10",
                    (m["city"], run_id)
                ).fetchall()
                city_texts[m["city"]] = [r["clean_text"] for r in rows]
            conn.close()
            llm_result = llm_run(run_id, city_metrics, city_texts)
            verdicts = llm_result.get("verdicts", {})
            if verdicts:
                agg_result = agg_run(run_id, verdicts)
                city_metrics = agg_result["city_metrics"]
            log.info(f"      ✓ {len(verdicts)} verdicts generated")
        else:
            if news_only:
                log.info("[6/7] Skipping LLM verdicts — daily news run")
            else:
                log.info("[6/7] Skipping LLM verdicts — --skip-llm flag")
        
        # LLM Judge — automated VADER validation
        from llm_judge import run as judge_run
        judge_result = judge_run(run_id)
        if not judge_result.get("skipped"):
            results["steps"]["llm_judge"] = {
                "total_judged": judge_result.get("total_judged", 0),
                "overall_agreement": judge_result.get("overall_agreement", 0),
                "city_agreement": judge_result.get("city_agreement", {})
            }
            log.info(f"      ✓ LLM Judge: {judge_result.get('overall_agreement', 0):.0%} overall agreement")
 
       # Step 9: Monitor
        log.info("[7/8] Monitoring and drift detection")
        from monitor import run as monitor_run
        mon_result = monitor_run(run_id, city_metrics)
        results["steps"]["monitor"] = {"alerts": mon_result["total_alerts"]}
        log.info(f"      ✓ {mon_result['total_alerts']} alerts generated")
 
        # Evaluate — model quality metrics
        log.info("[8/8] Model evaluation")
        from evaluate import run as evaluate_run
        eval_result = evaluate_run(run_id)
        results["steps"]["evaluate"] = eval_result
        if "error" not in eval_result:
            log.info(f"      ✓ Accuracy={eval_result['accuracy']:.0%} Macro F1={eval_result['macro_f1']:.0%}")
        else:
            log.info(f"      — {eval_result['error']}")
 
        # Step 10: Dashboard
        log.info("[8/8] Generating dashboard")
        from dashboard import run as dash_run
        dash_result = dash_run(run_id)
        results["steps"]["dashboard"] = dash_result
        log.info(f"      ✓ Dashboard → docs/index.html")
 
        results["success"] = True
        log.info("=" * 60)
        if news_only:
            log.info(f"DAILY NEWS RUN COMPLETE ✓ — run_id={run_id}")
        else:
            log.info(f"FULL PIPELINE COMPLETE ✓ — run_id={run_id}")
        log.info("Open docs/index.html or run: streamlit run app.py")
        log.info("=" * 60)
 
    except Exception as e:
        log.error(f"PIPELINE FAILED: {e}", exc_info=True)
        results["error"] = str(e)
 
    summary_dir = os.path.join(os.getenv("PIPELINE_ARTIFACTS_DIR", "artifacts"), "logs")
    os.makedirs(summary_dir, exist_ok=True)
    with open(os.path.join(summary_dir, f"summary_{run_id}.json"), "w") as f:
        json.dump(results, f, indent=2)
 
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