"""
refilter_groq.py — Re-run Groq filter on already-processed docs from backup.

Reads from the local backup JSON (artifacts/historical/processed_relevant_*.json)
Runs Groq with a proper delay to avoid rate limiting
Only keeps docs Groq confirms as relevant
Replaces the processed_documents entries with clean results

Usage:
    python refilter_groq.py

It will auto-find the latest backup file in artifacts/historical/
"""

import os
import json
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne, DeleteOne

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"

PROCESSED_COLLECTION = "processed_documents"
BACKUP_DIR = Path("artifacts/historical")

# Longer delay to stay within Groq free tier rate limit
# Free tier: 30 requests per minute = 1 request per 2 seconds to be safe
GROQ_DELAY = 2.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("refilter")


def test_mongodb_connection() -> bool:
    if not MONGO_URI:
        log.error("[MongoDB] MONGO_URI not set")
        return False
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        client.close()
        log.info("[MongoDB] Connection test passed ✓")
        return True
    except Exception as e:
        log.error(f"[MongoDB] Connection FAILED: {e}")
        log.error("[MongoDB] Make sure VPN is OFF")
        return False


def find_latest_backup() -> Path | None:
    """Find the most recent backup file in artifacts/historical/"""
    if not BACKUP_DIR.exists():
        return None
    backups = sorted(BACKUP_DIR.glob("processed_relevant_*.json"), reverse=True)
    return backups[0] if backups else None


def build_system_prompt(city: str) -> str:
    return f"""You are a strict travel content classifier.
Decide if this post is specifically about travelling to, visiting, or experiencing {city} as a travel destination.

RELEVANT — only if the post is about:
- Personal travel experiences IN {city} specifically
- Tips or questions about visiting {city}
- Hotels, food, attractions in {city}
- Asking for travel advice about {city}
- Overtourism or crowding IN {city}
- Cost of visiting {city}

NOT RELEVANT — reject if:
- About a different city or country (even if it mentions {city} briefly)
- General travel news not specific to {city}
- Sports, politics, business about {city}
- Tourism industry news about other destinations
- Academic papers not about visiting {city}
- Articles about aviation, flights in general

Be STRICT. When in doubt, say no.

Respond ONLY with valid JSON:
{{"relevant": "yes", "reason": "one sentence explanation"}}
or
{{"relevant": "no", "reason": "one sentence explanation"}}"""


def groq_classify(title: str, text: str, city: str) -> tuple:
    """
    Run Groq classification with proper rate limiting.
    Returns (is_relevant: bool, reason: str, success: bool)
    success=False means Groq call failed
    """
    if not GROQ_API_KEY:
        return True, "no_groq_key", False

    user_message = f"City: {city}\nTitle: {title}\nText: {text[:300]}"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": GROQ_MODEL,
        "temperature": 0,
        "max_tokens": 80,
        "messages": [
            {"role": "system", "content": build_system_prompt(city)},
            {"role": "user", "content": user_message},
        ],
    }

    try:
        response = requests.post(GROQ_URL, headers=headers, json=body, timeout=15)

        if response.status_code == 429:
            log.warning("[Groq] Rate limited — waiting 60 seconds...")
            time.sleep(60)
            # Retry once after waiting
            response = requests.post(GROQ_URL, headers=headers, json=body, timeout=15)

        response.raise_for_status()
        raw_text = response.json()["choices"][0]["message"]["content"].strip()

        try:
            result = json.loads(raw_text)
            is_relevant = result.get("relevant", "no") == "yes"
            reason = result.get("reason", "")
            return is_relevant, f"groq: {reason}", True
        except json.JSONDecodeError:
            log.warning(f"[Groq] Parse error: {raw_text[:80]}")
            return False, "groq_parse_error: defaulting to drop", True

    except Exception as e:
        log.warning(f"[Groq] Error: {e}")
        return False, f"groq_error: {str(e)[:60]}", False


def save_backup(docs: list, suffix: str = "refiltered"):
    """Save results locally before pushing to MongoDB."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"processed_{suffix}_{timestamp}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2, ensure_ascii=False, default=str)
    log.info(f"[Backup] Saved {len(docs)} docs → {path}")
    return path


def run():
    log.info("=" * 60)
    log.info("GROQ RE-FILTER")
    log.info(f"Delay between calls: {GROQ_DELAY}s (respects rate limit)")
    log.info("=" * 60)

    # ── Step 1: Pre-flight checks ──────────────────────────────────────────────
    if not GROQ_API_KEY:
        log.error("GROQ_API_KEY not set — cannot run")
        return

    if not test_mongodb_connection():
        log.error("Fix MongoDB connection first (check VPN is OFF)")
        return

    # ── Step 2: Load backup file ───────────────────────────────────────────────
    backup_path = find_latest_backup()
    if not backup_path:
        log.error(f"No backup file found in {BACKUP_DIR}")
        log.error("Make sure historical_preprocess.py ran successfully first")
        return

    log.info(f"\nLoading backup: {backup_path}")
    with open(backup_path, encoding="utf-8") as f:
        docs = json.load(f)

    log.info(f"Loaded {len(docs)} documents to re-filter")

    # ── Step 3: Run Groq with proper delay ────────────────────────────────────
    confirmed_relevant = []
    confirmed_irrelevant = []
    groq_failed = []

    metrics = {
        "total": len(docs),
        "groq_yes": 0,
        "groq_no": 0,
        "groq_failed": 0,
        "groq_calls": 0
    }

    log.info(f"\nRunning Groq on {len(docs)} docs with {GROQ_DELAY}s delay...")
    log.info("This will take approximately {:.0f} minutes\n".format(
        len(docs) * GROQ_DELAY / 60
    ))

    for i, doc in enumerate(docs):
        title = doc.get("title", "") or ""
        text = doc.get("text", "") or ""
        city = doc.get("city", "Unknown")

        if i % 50 == 0:
            log.info(
                f"[{i}/{len(docs)}] "
                f"kept={len(confirmed_relevant)} | "
                f"dropped={len(confirmed_irrelevant)} | "
                f"failed={len(groq_failed)}"
            )

        is_relevant, reason, success = groq_classify(title, text, city)
        metrics["groq_calls"] += 1

        if not success:
            metrics["groq_failed"] += 1
            groq_failed.append(doc)
            log.warning(f"[{i}] GROQ FAILED for {city}: {title[:50]}")
        elif is_relevant:
            metrics["groq_yes"] += 1
            doc["llm_relevant"] = True
            doc["llm_reason"] = reason
            confirmed_relevant.append(doc)
            log.debug(f"[{i}] KEEP {city}: {title[:50]}")
        else:
            metrics["groq_no"] += 1
            confirmed_irrelevant.append(doc)
            log.info(f"[{i}] DROP {city}: {title[:50]} — {reason}")

        # Proper rate limit delay
        time.sleep(GROQ_DELAY)

    log.info(f"\nGroq re-filter complete:")
    log.info(f"  Confirmed relevant: {len(confirmed_relevant)}")
    log.info(f"  Confirmed irrelevant: {len(confirmed_irrelevant)}")
    log.info(f"  Groq failed: {len(groq_failed)}")

    # If Groq failed on some docs, be conservative and drop them
    if groq_failed:
        log.warning(
            f"\n{len(groq_failed)} docs had Groq failures — dropping them to be safe"
        )

    # ── Step 4: Save backup of confirmed relevant docs ─────────────────────────
    if not confirmed_relevant:
        log.warning("No documents confirmed relevant — nothing to save")
        return

    backup_path = save_backup(confirmed_relevant)
    log.info(f"[Backup] Refiltered data safe at: {backup_path}")

    # ── Step 5: Remove old groq_error docs from MongoDB ────────────────────────
    log.info(f"\n[MongoDB] Removing old groq_error documents from '{PROCESSED_COLLECTION}'...")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    # Remove all docs that were kept due to groq_error (the bad ones)
    result = db[PROCESSED_COLLECTION].delete_many({
        "run_id": "historical_bulk_backfill",
        "llm_reason": {"$regex": "groq_error"}
    })
    log.info(f"[MongoDB] Removed {result.deleted_count} groq_error documents")

    # ── Step 6: Push only confirmed relevant docs ──────────────────────────────
    log.info(f"\n[MongoDB] Pushing {len(confirmed_relevant)} confirmed relevant docs...")
    operations = [
        UpdateOne(
            {"doc_id": d["doc_id"]},
            {"$set": d},
            upsert=True
        )
        for d in confirmed_relevant
    ]
    result = db[PROCESSED_COLLECTION].bulk_write(operations)
    log.info(
        f"[MongoDB] Saved {result.upserted_count + result.modified_count} "
        f"documents to '{PROCESSED_COLLECTION}'"
    )

    # Save artifact
    db["pipeline_artifacts"].insert_one({
        "run_id": "historical_bulk_backfill_refiltered",
        "artifact_type": "groq_refilter",
        "timestamp": datetime.now(timezone.utc),
        "document_count": len(confirmed_relevant),
        "metrics": metrics
    })

    client.close()

    # ── Final summary ──────────────────────────────────────────────────────────
    log.info("\n" + "=" * 60)
    log.info("RE-FILTER COMPLETE")
    log.info(f"Input docs:          {metrics['total']}")
    log.info(f"Groq confirmed yes:  {metrics['groq_yes']}")
    log.info(f"Groq confirmed no:   {metrics['groq_no']}")
    log.info(f"Groq failed (dropped):{metrics['groq_failed']}")
    log.info(f"Final clean docs:    {len(confirmed_relevant)}")
    log.info(f"Saved to MongoDB:    {PROCESSED_COLLECTION}")
    log.info(f"Local backup:        {backup_path}")
    log.info("=" * 60)


if __name__ == "__main__":
    run()