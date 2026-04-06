"""
llm_summary.py — Step 7 (optional): LLM city verdicts.
Only runs if ENABLE_LLM_VERDICTS=true in .env.
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("llm_summary")
ENABLE_LLM = os.getenv("ENABLE_LLM_VERDICTS", "false").lower() == "true"
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")


def build_prompt(city: str, metrics: dict, sample_texts: list) -> str:
    samples = "\n".join(f"- {t[:200]}" for t in sample_texts[:5])
    return f"""You are analysing traveller sentiment about {city}.

Weekly metrics:
- Average sentiment: {metrics.get('avg_sentiment', 0):.2f} (range: -1 to 1)
- Mentions: {metrics.get('mention_count', 0)}
- Positive: {metrics.get('positive_ratio', 0):.0%}, Negative: {metrics.get('negative_ratio', 0):.0%}
- Crowding complaints: {metrics.get('crowding_score', 0):.2f}
- Cost complaints: {metrics.get('cost_score', 0):.2f}

Sample texts:
{samples}

Write ONE honest sentence verdict about traveller sentiment for {city} this week.
Focus on overall vibe, crowding, and value. Be direct. Return only the sentence."""


def generate_verdict(city: str, metrics: dict, sample_texts: list) -> str:
    prompt = build_prompt(city, metrics, sample_texts)
    try:
        if ANTHROPIC_KEY:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            r = client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=100,
                messages=[{"role": "user", "content": prompt}]
            )
            return r.content[0].text.strip()
        elif OPENAI_KEY:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_KEY)
            r = client.chat.completions.create(
                model="gpt-4o-mini", max_tokens=100, temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            return r.choices[0].message.content.strip()
    except Exception as e:
        log.error(f"[LLM] Error for {city}: {e}")
    return ""


def run(run_id: str, city_metrics: list, city_texts: dict) -> dict:
    if not ENABLE_LLM:
        log.info("[LLM] Disabled — set ENABLE_LLM_VERDICTS=true to enable")
        return {"run_id": run_id, "verdicts": {}}

    log.info(f"=== STEP 7: LLM SUMMARY | run_id={run_id} ===")
    verdicts = {}
    for m in city_metrics:
        city = m["city"]
        verdict = generate_verdict(city, m, city_texts.get(city, []))
        verdicts[city] = verdict
        log.info(f"[LLM] {city}: {verdict[:80]}")

    return {"run_id": run_id, "verdicts": verdicts}
