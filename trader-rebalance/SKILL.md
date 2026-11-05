---
name: trader-rebalance
description: >-
  Rebalancer for an Indian stock portfolio. Values every holding at current
  prices, works out each stock's drift from its target weight in percentage
  points, trades only the stocks outside a band (default 5 points) and only
  when the trade is worth its charges (the round trip including the Rs 20 DP
  charge on sells), keeps the cash buffer and the per-stock cap, uses whole
  shares, lists sells before buys so the cash is there, handles new money
  (--add), and writes the trades to trader/orders.json as proposals. Use when
  the user says "rebalance", "my portfolio drifted", "back to the targets", "I
  added money", "I have 5,000 more to invest", or after /trader-copycat finds
  a new month's or quarter's holdings.
---

# trader-rebalance

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/rebalance.py"                    # the drift table, nothing written
python3 "${CLAUDE_SKILL_DIR}/rebalance.py" --band 3 --write   # -> trader/orders.json
python3 "${CLAUDE_SKILL_DIR}/rebalance.py" --add 5000 --write # new money, booked as a deposit
```

Reads `trader/portfolio.json`, `trader/targets.json`, `trader/prices.json`
(run `/trader-alerts quote` first) and `trader/config.json`.

## What it does

1. Values the portfolio (cash + shares at current prices).
2. Target value per stock = (portfolio − buffer) × target weight, capped.
3. Trades a stock only if its drift is at least the band, or it is no longer a
   target (then it sells all of it).
4. Skips trades under `min_order_inr` or with charges over `max_charges_pct`.
5. Sells first; buys are trimmed to fit the cash left above the buffer.

## Talking to the user

- Show the drift table and the trades, including the skipped ones and why.
- Before any sell, run `/trader-tax sell SYMBOL QTY` and show the tax hit: a
  short-term sale at 20% can cost more than the drift. Offer to wait if a lot
  turns long term soon.
- Rebalancing a copied fund every month churns charges. Quarterly with a 5-point
  band is a sensible default for small portfolios.

## Safety

- Proposals only. Next: `/trader-risk`, then `/trader-broker`.
- Not financial advice.
