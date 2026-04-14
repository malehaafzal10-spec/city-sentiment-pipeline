#!/bin/bash

# ─────────────────────────────────────────────────────────────────────────────
# run_historical_backfill_v2.sh
# Fetches historical news 2026-03-11 → 2026-04-06 in chunks of 4 days.
# Each chunk uses 96 requests (8 cities × 3 keywords × 4 days) — just under
# the NewsAPI free tier limit of 100 requests/day.
#
# Usage:
#   chmod +x preprocess/run_historical_backfill_v2.sh
#   ./preprocess/run_historical_backfill_v2.sh
#
# To resume from a specific chunk, comment out the earlier chunks.
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT="preprocess/01b_fetch_test_day.py"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

fetch_date() {
    local date=$1
    echo -e "${GREEN}  Fetching ${date}...${NC}"
    python $SCRIPT --date "$date"
    if [ $? -ne 0 ]; then
        echo -e "${RED}✗ Failed on ${date}. Fix the error and re-run from this chunk.${NC}"
        exit 1
    fi
}

pause() {
    local next_chunk=$1
    local next_date=$2
    echo ""
    echo -e "${YELLOW}⚠️  ~96 NewsAPI requests used. Wait 24 hours before running chunk ${next_chunk}.${NC}"
    echo -e "${YELLOW}   Next chunk starts: ${next_date}${NC}"
    echo ""
    read -p "Press ENTER when ready, or Ctrl+C to stop and resume later... "
}

# ─── Main ────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}   HISTORICAL BACKFILL v2 — 2026-03-12 → 2026-04-06   ${NC}"
echo -e "${GREEN}   7 chunks × 4 days × 24 requests = ~96 req/chunk     ${NC}"
echo -e "${GREEN}   Per-keyword strategy — matches daily pipeline        ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"

# ── Chunk 1 — 2026-03-12 → 2026-03-14 ───────────────────────────────────────
echo -e "\n${GREEN}━━━ CHUNK 1/7 — 2026-03-12 → 2026-03-14 ━━━${NC}"
fetch_date "2026-03-12"
fetch_date "2026-03-13"
fetch_date "2026-03-14"
echo -e "${GREEN}✓ Chunk 1 complete.${NC}"
pause 2 "2026-03-15"

# ── Chunk 2 — 2026-03-15 → 2026-03-18 ───────────────────────────────────────
echo -e "\n${GREEN}━━━ CHUNK 2/7 — 2026-03-15 → 2026-03-18 ━━━${NC}"
fetch_date "2026-03-15"
fetch_date "2026-03-16"
fetch_date "2026-03-17"
fetch_date "2026-03-18"
echo -e "${GREEN}✓ Chunk 2 complete.${NC}"
pause 3 "2026-03-19"

# ── Chunk 3 — 2026-03-19 → 2026-03-22 ───────────────────────────────────────
echo -e "\n${GREEN}━━━ CHUNK 3/7 — 2026-03-19 → 2026-03-22 ━━━${NC}"
fetch_date "2026-03-19"
fetch_date "2026-03-20"
fetch_date "2026-03-21"
fetch_date "2026-03-22"
echo -e "${GREEN}✓ Chunk 3 complete.${NC}"
pause 4 "2026-03-23"

# ── Chunk 4 — 2026-03-23 → 2026-03-26 ───────────────────────────────────────
echo -e "\n${GREEN}━━━ CHUNK 4/7 — 2026-03-23 → 2026-03-26 ━━━${NC}"
fetch_date "2026-03-23"
fetch_date "2026-03-24"
fetch_date "2026-03-25"
fetch_date "2026-03-26"
echo -e "${GREEN}✓ Chunk 4 complete.${NC}"
pause 5 "2026-03-27"

# ── Chunk 5 — 2026-03-27 → 2026-03-30 ───────────────────────────────────────
echo -e "\n${GREEN}━━━ CHUNK 5/7 — 2026-03-27 → 2026-03-30 ━━━${NC}"
fetch_date "2026-03-27"
fetch_date "2026-03-28"
fetch_date "2026-03-29"
fetch_date "2026-03-30"
echo -e "${GREEN}✓ Chunk 5 complete.${NC}"
pause 6 "2026-03-31"

# ── Chunk 6 — 2026-03-31 → 2026-04-03 ───────────────────────────────────────
echo -e "\n${GREEN}━━━ CHUNK 6/7 — 2026-03-31 → 2026-04-03 ━━━${NC}"
fetch_date "2026-03-31"
fetch_date "2026-04-01"
fetch_date "2026-04-02"
fetch_date "2026-04-03"
echo -e "${GREEN}✓ Chunk 6 complete.${NC}"
pause 7 "2026-04-04"

# ── Chunk 7 — 2026-04-04 → 2026-04-06 ───────────────────────────────────────
echo -e "\n${GREEN}━━━ CHUNK 7/7 — 2026-04-04 → 2026-04-06 ━━━${NC}"
fetch_date "2026-04-04"
fetch_date "2026-04-05"
fetch_date "2026-04-06"
echo -e "${GREEN}✓ Chunk 7 complete.${NC}"

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}   ✓ BACKFILL COMPLETE — all chunks finished!           ${NC}"
echo -e "${GREEN}                                                        ${NC}"
echo -e "${GREEN}   Now process and filter all fetched data:             ${NC}"
echo -e "${GREEN}   python preprocess/02a_store_relevant_docs_historical.py \\${NC}"
echo -e "${GREEN}     --start-date 2026-03-11 --end-date 2026-04-06      ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""