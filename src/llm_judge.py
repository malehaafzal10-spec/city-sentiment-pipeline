"""
llm_judge.py — LLM as a Judge for VADER sentiment validation.
Uses Groq API (free, fast) with Llama 3 model.

How it works:
  1. Takes a random sample of articles that VADER scored
  2. Sends each one to Groq and asks for a sentiment label
  3. Compares Groq label vs VADER label
  4. If agreement is low for a city — flags it as low confidence
  5. Disagreed articles go into human review queue in the dashboard

Runs automatically as part of run_pipeline.py
Only runs if GROQ_API_KEY is set in .env
"""

import os
import logging
import random
from datetime import date, timedelta
from collections import defaultdict
from dotenv import load_dotenv
from db import get_connection

load_dotenv()

log = logging.getLogger("llm_judge")

AGREEMENT_THRESHOLD = float(os.getenv("LLM_JUDGE_AGREEMENT_THRESHOLD", "0.70"))


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
            model="llama3-8b-8192",
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
    """
    Run LLM Judge on a random sample of scored documents for this run.

    Args:
        run_id: pipeline run identifier
        sample_size: how many articles to judge (default 30 — balances cost vs coverage)

    Returns:
        dict with overall agreement rate and per-city agreement rates
    """
    GROQ_KEY = os.getenv("GROQ_API_KEY", "")
    if not GROQ_KEY:
        log.info("[LLM Judge] No GROQ_API_KEY set in .env — skipping")
        return {"run_id": run_id, "skipped": True, "city_agreement": {}}

    log.info(f"=== LLM JUDGE (Groq / Llama 3) | run_id={run_id} ===")

    week_start = get_week_start()
    conn = get_connection()

    # Fetch scored documents joined with their cleaned text
    rows = conn.execute("""
        SELECT
            sd.doc_id,
            sd.city,
            sd.sentiment_label,
            sd.sentiment_score,
            cd.clean_text
        FROM scored_documents sd
        JOIN cleaned_documents cd ON sd.doc_id = cd.doc_id
        WHERE sd.run_id = ?
    """, (run_id,)).fetchall()

    if not rows:
        log.info("[LLM Judge] No scored documents found for this run — skipping")
        conn.close()
        return {"run_id": run_id, "city_agreement": {}}

    # Sample randomly — we don't judge every article to keep costs low
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
            "clean_text": row["clean_text"]
        })

        log.info(
            f"[LLM Judge] {row['city']:12} | "
            f"VADER: {row['sentiment_label']:8} | "
            f"Groq: {llm_label:8} | "
            f"{'✓ AGREE' if agreement else '✗ DISAGREE'}"
        )

    # Save all judge results to database
    for r in results:
        try:
            conn.execute("""
                INSERT INTO llm_judge_results
                (doc_id, city, vader_label, vader_score, llm_label,
                 agreement, week_start, run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["doc_id"], r["city"], r["vader_label"], r["vader_score"],
                r["llm_label"], r["agreement"], week_start, run_id
            ))
        except Exception as e:
            log.warning(f"[LLM Judge] DB insert error: {e}")

    # Calculate agreement rate per city
    city_results = defaultdict(list)
    for r in results:
        city_results[r["city"]].append(r["agreement"])

    city_agreement = {}

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

            # Add disagreed articles to human review queue
            disagreed = [
                r for r in results
                if r["city"] == city and r["agreement"] == 0
            ]

            for r in disagreed:
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO validation_samples
                        (doc_id, city, clean_text, vader_label, vader_score,
                         llm_label, needs_review, week_start, run_id)
                        VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """, (
                        r["doc_id"], r["city"], r["clean_text"],
                        r["vader_label"], r["vader_score"],
                        r["llm_label"], week_start, run_id
                    ))
                except Exception as e:
                    log.warning(f"[LLM Judge] Failed to add to review queue: {e}")

            log.info(
                f"[LLM Judge] Added {len(disagreed)} articles "
                f"to human review queue for {city}"
            )

    conn.commit()
    conn.close()

    # Overall agreement across all cities
    overall = sum(r["agreement"] for r in results) / len(results) if results else 0
    log.info(f"[LLM Judge] Overall agreement rate: {overall:.0%}")
    log.info(f"[LLM Judge] Cities below threshold: {[c for c, r in city_agreement.items() if r < AGREEMENT_THRESHOLD]}")

    return {
        "run_id": run_id,
        "total_judged": len(results),
        "overall_agreement": round(overall, 3),
        "city_agreement": city_agreement
    }