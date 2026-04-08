#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# run_historical_backfill.sh
# Runs the historical news backfill in 4 chunks of ~6 days each.
# Each chunk uses ~48 requests (8 cities × 6 days), staying under the
# NewsAPI free tier limit of 50 requests per 12 hours.
#
# Usage:
#   chmod +x run_historical_backfill.sh   (only needed once)
#   ./run_historical_backfill.sh
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT="preprocess/01a_ingest_historical_news.py"

# Colour helpers
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No colour

run_chunk() {
    local chunk=$1
    local from=$2
    local to=$3

    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN} CHUNK ${chunk}/4 — ${from} → ${to}${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    python $SCRIPT --from-date "$from" --to-date "$to"

    if [ $? -ne 0 ]; then
        echo ""
        echo -e "${RED}✗ Chunk ${chunk} failed. Fix the error and re-run from this chunk.${NC}"
        exit 1
    fi

    echo ""
    echo -e "${GREEN}✓ Chunk ${chunk} complete.${NC}"
}

pause_and_confirm() {
    local next_chunk=$1
    local from=$2
    local to=$3

    echo ""
    echo -e "${YELLOW}⚠️  Wait at least 12 hours before running chunk ${next_chunk}.${NC}"
    echo -e "${YELLOW}   Next chunk: ${from} → ${to}${NC}"
    echo ""
    read -p "Press ENTER when ready to continue, or Ctrl+C to stop and resume later... "
}

# ─── Main ────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}   HISTORICAL NEWS BACKFILL — 2026-03-07 → 2026-04-08  ${NC}"
echo -e "${GREEN}   4 chunks × ~48 requests — free tier safe            ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"

# Chunk 1 — run immediately
run_chunk 1 "2026-03-07" "2026-03-13"
pause_and_confirm 2 "2026-03-13" "2026-03-19"

# Chunk 2
run_chunk 2 "2026-03-13" "2026-03-19"
pause_and_confirm 3 "2026-03-19" "2026-03-25"

# Chunk 3
run_chunk 3 "2026-03-19" "2026-03-25"
pause_and_confirm 4 "2026-03-25" "2026-04-08"

# Chunk 4
run_chunk 4 "2026-03-25" "2026-04-08"

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}   ✓ BACKFILL COMPLETE — all chunks finished!           ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""