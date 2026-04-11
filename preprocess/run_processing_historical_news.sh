#!/bin/bash

# ─────────────────────────────────────────────────────────────────────────────
# run_preprocessing_historical_news.sh
# Runs the LLM relevance filter + scraping for 2026-03-11 → 2026-04-06
# week by week. Pauses after each week so you can check logs before continuing.
# Safe to re-run — already processed docs are skipped automatically.
#
# Usage:
#   chmod +x preprocess/run_preprocessing_historical_news.sh
#   ./preprocess/run_preprocessing_historical_news.sh
#
# To resume from a specific week, comment out the earlier weeks.
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT="preprocess/02a_store_relevant_docs_historical.py"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

process_week() {
    local week=$1
    local total=$2
    local from=$3
    local to=$4

    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN} WEEK ${week}/${total} — ${from} → ${to}${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    python $SCRIPT --start-date "$from" --end-date "$to"

    if [ $? -ne 0 ]; then
        echo -e "${RED}✗ Week ${week} failed. Fix the error and re-run from this week.${NC}"
        exit 1
    fi

    echo -e "${GREEN}✓ Week ${week} complete.${NC}"
}

pause() {
    local next_week=$1
    local from=$2
    local to=$3
    echo ""
    echo -e "${YELLOW}⏸  Week ${next_week} ready to run (${from} → ${to}).${NC}"
    echo -e "${YELLOW}   Check your logs, then press ENTER to continue or Ctrl+C to stop.${NC}"
    read -p ""
}

# ─── Main ────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}   HISTORICAL PROCESSING — 2026-03-11 → 2026-04-06    ${NC}"
echo -e "${GREEN}   4 weeks — already processed docs are skipped        ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"

process_week 1 4 "2026-03-11" "2026-03-17"
pause 2 "2026-03-18" "2026-03-24"

process_week 2 4 "2026-03-18" "2026-03-24"
pause 3 "2026-03-25" "2026-03-31"

process_week 3 4 "2026-03-25" "2026-03-31"
pause 4 "2026-04-01" "2026-04-06"

process_week 4 4 "2026-04-01" "2026-04-06"

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}   ✓ ALL DONE — historical data fully processed!       ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""