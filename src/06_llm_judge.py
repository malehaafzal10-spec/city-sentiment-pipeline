"""
06_llm_judge.py — Step 6: LLM as a Judge for VADER sentiment validation.
Uses Groq API (Llama 3) to cross-validate VADER scores on a random sample.

Disagreed articles are pushed to the 'validation_samples' MongoDB collection 
for human review, which powers the VADER evaluation metrics.
"""

import os
import logging
import random
from datetime import date, timedelta, datetime, timezone
from collections import defaultdict

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")

# Collections
PROCESSED_COLLECTION = "processed_documents"
SCORED_COLLECTION = "scored_documents"
JUDGE_COLLECTION = "llm_judge_results"
VALIDATION_COLLECTION = "validation_samples"
ARTIFACTS_COLLECTION = "pipeline_artifacts"

AGREEMENT_THRESHOLD = float(os.getenv("LLM_JUDGE_AGREEMENT_THRESHOLD", "0.70"))

logging.basicConfig(
    level=getattr(logging, os.getenv("PIPELINE_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("llm_judge")


def get_week_start() -> str:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


def ask_llm(text: str, city: str) -> str:
    """
    Send article text to Groq and get a sentiment label back.
    Returns: 'positive', 'negative', or 'neutral'
    """
    from groq import Groq

    GROQ_KEY = os.getenv("GROQ_API_KEY", "")
    if not GROQ_KEY:
        return "unknown"

    prompt = f"""You are a sentiment analyser for travel content.

Read this text about {city} and decide if it expresses positive,
negative, or neutral sentiment about visiting {city} as a tourist.

Text: {text[:500]}

Reply with exactly one word only: positive, negative, or neutral"""

    try:
        client = Groq(api_key=GROQ_KEY)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0
        )
        label = response.choices[0].message.content.strip().lower()

        # Clean up response in case LLM adds extra words
        for valid in ["positive", "negative", "neutral"]:
            if valid in label:
                return valid

        return "neutral"  # default if response is unclear

    except Exception as e:
        log.warning(f"[LLM Judge] Groq API error: {e}")
        return "unknown"


def run(run_id: str, sample_size: int = 30) -> dict:
    GROQ_KEY = os.getenv("GROQ_API_KEY", "")
    if not GROQ_KEY:
        log.info("[LLM Judge] No GROQ_API_KEY set in .env — skipping")
        return {"run_id": run_id, "skipped": True, "city_agreement": {}}

    if not MONGO_URI:
        log.error("[DB] MONGO_URI missing.")
        return {"run_id": run_id, "skipped": True}

    log.info(f"=== STEP 6: LLM JUDGE (Groq / Llama 3) | run_id={run_id} ===")

    week_start = get_week_start()
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    # 1. Fetch text from processed_documents
    processed_cursor = db[PROCESSED_COLLECTION].find({"run_id": run_id}, {"doc_id": 1, "text": 1})
    text_map = {doc["doc_id"]: doc.get("text", "") for doc in processed_cursor}

    # 2. Fetch scores from scored_documents and join with text
    scored_cursor = db[SCORED_COLLECTION].find({"run_id": run_id})
    rows = []
    
    for doc in scored_cursor:
        doc_id = doc.get("doc_id")
        if doc_id in text_map:
            rows.append({
                "doc_id": doc_id,
                "city": doc.get("city"),
                "sentiment_label": doc.get("sentiment_label"),
                "sentiment_score": doc.get("sentiment_score"),
                "clean_text": text_map[doc_id]
            })

    if not rows:
        log.info("[LLM Judge] No scored documents found for this run — skipping")
        client.close()
        return {"run_id": run_id, "city_agreement": {}}

    # 3. Sample randomly
    sample = random.sample(list(rows), min(sample_size, len(rows)))
    log.info(f"[LLM Judge] Judging {len(sample)} articles (sampled from {len(rows)} total)")

    results = []
    for row in sample:
        llm_label = ask_llm(row["clean_text"], row["city"])
        agreement = 1 if llm_label == row["sentiment_label"] else 0

        results.append({
            "doc_id": row["doc_id"],
            "city": row["city"],
            "vader_label": row["sentiment_label"],
            "vader_score": row["sentiment_score"],
            "llm_label": llm_label,
            "agreement": agreement,
            "clean_text": row["clean_text"],
            "week_start": week_start,
            "run_id": run_id,
            "judged_at": datetime.now(timezone.utc).isoformat()
        })

        log.info(
            f"[LLM Judge] {row['city']:12} | "
            f"VADER: {row['sentiment_label']:8} | "
            f"Groq: {llm_label:8} | "
            f"{'✓ AGREE' if agreement else '✗ DISAGREE'}"
        )

    # 4. Save judge results to database
    try:
        judge_ops = [UpdateOne({"doc_id": r["doc_id"]}, {"$set": r}, upsert=True) for r in results]
        db[JUDGE_COLLECTION].bulk_write(judge_ops)
    except Exception as e:
        log.warning(f"[LLM Judge] DB insert error: {e}")

    # 5. Calculate agreement rate per city
    city_results = defaultdict(list)
    for r in results:
        city_results[r["city"]].append(r["agreement"])

    city_agreement = {}
    disagreed_docs = []

    for city, agreements in city_results.items():
        rate = sum(agreements) / len(agreements)
        city_agreement[city] = round(rate, 3)

        log.info(f"[LLM Judge] {city} agreement rate: {rate:.0%} ({sum(agreements)}/{len(agreements)})")

        # If agreement is below threshold — flag for human review
        if rate < AGREEMENT_THRESHOLD:
            log.warning(
                f"[LLM Judge] LOW CONFIDENCE: {city} — "
                f"{rate:.0%} agreement (threshold: {AGREEMENT_THRESHOLD:.0%})"
            )

            # Extract disagreed articles for this city
            city_disagreements = [r for r in results if r["city"] == city and r["agreement"] == 0]
            for r in city_disagreements:
                # Format for validation_samples collection
                disagreed_docs.append({
                    "doc_id": r["doc_id"],
                    "city": r["city"],
                    "clean_text": r["clean_text"],
                    "vader_label": r["vader_label"],
                    "vader_score": r["vader_score"],
                    "llm_label": r["llm_label"],
                    "needs_review": True,
                    "human_label": None, # Blank, waiting for human
                    "week_start": week_start,
                    "run_id": run_id,
                    "added_to_queue_at": datetime.now(timezone.utc).isoformat()
                })

            log.info(f"[LLM Judge] Added {len(city_disagreements)} articles to human review queue for {city}")

    # 6. Insert disagreed articles into validation queue
    if disagreed_docs:
        try:
            val_ops = [UpdateOne({"doc_id": d["doc_id"]}, {"$set": d}, upsert=True) for d in disagreed_docs]
            db[VALIDATION_COLLECTION].bulk_write(val_ops)
        except Exception as e:
            log.warning(f"[LLM Judge] Failed to add to review queue: {e}")

    # 7. Overall metrics & Artifact saving
    overall = sum(r["agreement"] for r in results) / len(results) if results else 0
    log.info(f"[LLM Judge] Overall agreement rate: {overall:.0%}")
    
    try:
        db[ARTIFACTS_COLLECTION].insert_one({
            "run_id": run_id,
            "artifact_type": "llm_judge_results",
            "timestamp": datetime.now(timezone.utc),
            "total_judged": len(results),
            "metrics": {
                "overall_agreement": overall,
                "city_agreement": city_agreement
            },
            "payload": results
        })
    except Exception as e:
        log.error(f"[Artifacts] Failed to save artifact: {e}")
    finally:
        client.close()

    return {
        "run_id": run_id,
        "total_judged": len(results),
        "overall_agreement": round(overall, 3),
        "city_agreement": city_agreement
    }

if __name__ == "__main__":
    test_run_id = input("Enter the run_id to judge: ")
    if test_run_id.strip():
        run(test_run_id.strip())