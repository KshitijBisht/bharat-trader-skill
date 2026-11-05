---
name: trader-risk
description: >-
  Risk Manager for Indian stocks. Checks every proposed order against the
  user's limits before it can reach the broker and blocks anything over them:
  blocked symbols, max order size in rupees, minimum order, max position percent
  after the fill, the cash buffer, charges that eat too much of a small order
  (round trip including the Rs 20 DP charge), whole shares only, CNC delivery
  only (intraday MIS, F&O, MTF and short selling off unless allowed), stocks
  under NSE ASM/GSM surveillance, trade-to-trade (BE series) and SME stocks,
  malformed orders, duplicates and a daily order limit. Prints PASS or BLOCK
  with the reason and records the verdicts so trader-broker only shows an order
  that passed. Use when the user says "check my orders", "is this safe", "risk
  check", "what are my limits", or after /trader-budget, /trader-rebalance or
  /trader-tax writes orders.
---

# trader-risk

The gate between a proposal and the broker. Deterministic: the same orders and
config always give the same verdicts, and `/trader-broker` refuses any order
that does not have a PASS from today (IST) for its exact fingerprint.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/check.py"                       # PASS / BLOCK every order in trader/orders.json
python3 "${CLAUDE_SKILL_DIR}/check.py" surveillance --fetch  # cache NSE's ASM + GSM lists (do daily)
```

## What it checks

| check | config key | default |
| --- | --- | --- |
| symbol on your blocked list | `blocked` | `[]` |
| order value over the max | `max_order_inr` | 5000 |
| order value under the min | `min_order_inr` | 100 |
| position after the fill over the cap | `max_position_pct` | 25 |
| cash left under the buffer | `cash_buffer_pct` | 5 |
| buy + sell charges over X% of the order | `max_charges_pct` | 2.5 |
| more orders today than allowed | `max_orders_per_day` | 10 |
| intraday (MIS) | `allow_intraday` | false |
| F&O / NRML | `allow_fno` | false |
| margin trading (MTF) | `allow_mtf` | false |
| selling more than you hold | `allow_short` | false |
| NSE ASM / GSM surveillance | `allow_surveillance` | false |
| trade-to-trade series (BE, BZ) | `allow_t2t` | false |
| SME series (SM, ST) | `allow_sme` | false |
| fractional or zero quantity, bad fields, duplicates | always | |

Sells are checked first so the cash they free counts toward the buys, the way
a real broker's margin works for delivery. Charges come from Groww's published
delivery schedule (`trader-common/inr.py`, overridable under `"charges"` in config).

## How to run it

1. `check.py surveillance --fetch` once a day (it is cheap and blocks the stocks
   NSE itself has flagged as risky).
2. `check.py`. Show the user the table as is.
3. For every BLOCK, explain the reason in one line and the honest options:
   smaller order, fewer stocks, raise a limit **in config.json themselves**. Never
   raise a limit, edit orders.json or re-run with a different config to turn a
   BLOCK into a PASS on your own.
4. If everything they want passed, hand over to `/trader-broker`.

### The ₹1,000 question

With ₹1,000, the minimum ₹5 brokerage each side plus about ₹23.60 DP charge
(₹20 + GST) on every sale means a round trip costs ~3.8% of a ₹1,000 order: the
stock must rise almost 4% just to break even. `max_charges_pct` (2.5% by
default) blocks those orders on purpose. Say so plainly. Options: paper trade it,
one order instead of five, a low-priced ETF held for long, or raise the limit
knowingly.

## Safety

- PASS is required for any order; this skill never places orders.
- Only the user changes limits. Quote the config key; do not edit it for them
  unless they ask in so many words, and never to get a specific order through.
- Verdicts expire at midnight IST; re-check the next day.
- Not financial advice.
