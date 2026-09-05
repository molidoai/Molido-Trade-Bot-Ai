#!/bin/bash
# Measure what the bot actually does.
#
# Both registry edges were validated on H1. The live bot trades M15 (and M5),
# so nothing on record describes the configuration that is actually running.
# This measures that configuration.
#
# Structured to keep the statistics honest. PART ONE is three pre-specified
# cells -- the exact symbol/strategy pairs live right now. Three hypotheses
# fixed before any result is seen, so a pass means something. PART TWO is an
# exploratory sweep for new symbols; with that many cells a pass is a
# candidate, never a conclusion, and must be re-measured out of sample before
# it is allowed anywhere near the live book.
#
# rr=3.0 / sl=1.5 ATR to match the registry's H1 evidence exactly, so any
# difference is the timeframe and not the parameters.
set -u
BAR="bar: >=30 OOS trades, PF>1.0, >half folds profitable -- fixed before any result"

cell () {  # symbol strategy label
  echo "#### $3 :: $2 on $1 ####"
  docker run --rm --name molido-m15 --cpus=2.5 --memory=1400m \
    -v molido_runtime_data:/app/data:ro \
    -v /opt/molido/baseline_row.py:/tmp/baseline_row.py:ro \
    -e ENS_SYMBOLS="$1" -e ENS_TF=M15 -e ENS_BARS=12000 \
    -e ENS_TRAIN=1500 -e ENS_TEST=500 \
    -e BASE_STRATEGIES="$2" -e BASE_RR=3.0 -e BASE_SL=1.5 \
    molido-trading-engine python3 -u /tmp/baseline_row.py 2>&1 | grep -E "^  "
  echo
}

echo "================ $BAR ================"
echo
echo "================ PART ONE: the three cells that are live now ================"
cell EURUSD RSIMeanReversion  "LIVE"
cell GBPUSD DonchianBreakout  "LIVE (refused on H1 -- does M15 change the answer?)"
cell XAUUSD TrendFollowing    "LIVE"

echo "================ PART TWO: exploratory -- candidates only ================"
for s in USDJPY AUDUSD USDCAD USDCHF NZDUSD EURJPY GBPJPY EURGBP; do
  for st in TrendFollowing RSIMeanReversion DonchianBreakout; do
    cell "$s" "$st" "EXPLORATORY"
  done
done
echo "================ DONE ================"
