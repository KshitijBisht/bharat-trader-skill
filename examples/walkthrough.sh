#!/usr/bin/env bash
# The README's ₹10,000 example, end to end, offline, in paper mode.
# Uses the real NSE and Parag Parikh files saved in tests/fixtures. Nothing leaves your machine.
#
#   bash examples/walkthrough.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
F="$ROOT/tests/fixtures"
WORK="$(mktemp -d)"
export TRADER_DIR="$WORK/trader"
export TRADER_NOW="2026-11-05T11:00"          # a trading day, market open
mkdir -p "$TRADER_DIR"
cp "$ROOT/trader-budget/config.example.json" "$TRADER_DIR/config.json"
cp "$F/trader-budget/EQUITY_L.csv" "$TRADER_DIR/EQUITY_L.csv"
step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

step "1. /trader-copycat: Parag Parikh Flexi Cap, Sept 2026 vs Aug 2026, top 5"
python3 "$ROOT/trader-copycat/copycat.py" fund "$F/trader-copycat/PPFCF-2026-09-30.xlsx" \
  --prev "$F/trader-copycat/PPFCF-2026-08-31.xlsx" --top 5 --write

step "2. /trader-alerts: prices from the NSE bhavcopy of 4 Nov 2026"
python3 - "$ROOT" "$F" <<'EOF'
import sys
root, f = sys.argv[1], sys.argv[2]
sys.path[:0] = [root + "/trader-alerts", root + "/trader-common"]
import alerts
q = alerts.parse_bhav(open(f + "/trader-alerts/sec_bhavdata_full_04112026.csv").read())
alerts.save_prices({s: q[s] for s in ("HDFCBANK", "POWERGRID", "ITC", "COALINDIA", "ICICIBANK")})
print("saved 5 closing prices")
EOF

step "3. /trader-budget: ₹10,000, 5% buffer, 25% cap, whole shares, real charges"
python3 "$ROOT/trader-budget/size.py" --budget 10000 --write

step "4. /trader-risk"
python3 "$ROOT/trader-risk/check.py"

step "5. /trader-broker: tickets, a refused 'maybe', then a yes for #3 and a paper fill"
python3 "$ROOT/trader-broker/ticket.py" show
python3 "$ROOT/trader-broker/ticket.py" approve --index 3 --reply "maybe later?" || true
python3 "$ROOT/trader-broker/ticket.py" approve --index 3 --reply "yes"
python3 "$ROOT/trader-broker/ticket.py" place --index 3
python3 "$ROOT/trader-broker/ticket.py" place --index 5 || true     # blocked by risk: refused

step "6. /trader-tax: the new lot"
python3 "$ROOT/trader-tax/lots.py" show

step "7. What ₹1,000 would cost"
python3 "$ROOT/trader-budget/size.py" --charges 1000

printf '\nWorking folder: %s\n' "$TRADER_DIR"
