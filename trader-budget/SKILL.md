---
name: trader-budget
description: >-
  Budget Manager for Indian stocks. Sizes target weights into whole-share NSE
  delivery orders before anything is bought: keeps a cash buffer, caps any one
  stock (the excess is shared out to the others), counts every rupee of charges
  (brokerage, STT, stamp duty, exchange, SEBI, GST, and the DP charge on the
  later sale), drops stocks whose one share costs more than their slice, uses up
  spare rupees one share at a time, warns when charges eat a small budget, and
  writes the proposed buy orders to trader/orders.json in the exact shape of
  Groww's place_order. Nothing is placed. Use when the user says "I have
  ₹10,000", "I have 1000 rupees", "size my trades", "how many shares of each",
  "split my money", "what do charges cost", or after /trader-copycat or
  /trader-screener writes targets.
argument-hint: "[budget in rupees]"
---

# trader-budget

Turns `trader/targets.json` (weights) into whole-share orders that fit the
user's rupees. Indian brokers do not sell fractional shares, so a ₹12,000 stock
simply does not fit a ₹1,000 budget, and the tool says so instead of rounding it
into a position the user cannot buy.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py" --charges 1000                 # what a ₹1,000 order really costs
python3 "${CLAUDE_SKILL_DIR}/size.py" --budget 10000                 # the plan, nothing written
python3 "${CLAUDE_SKILL_DIR}/size.py" --budget 10000 --write         # -> trader/orders.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --budget 10000 --cap 30 --buffer 5 --price ITC=279.4 --write
```

Prices come from `trader/prices.json` (run `/trader-alerts quote` first) or
`--price SYMBOL=PRICE`. Settings come from `trader/config.json`; copy
`config.example.json` there to start.

## How it sizes

1. Drop blocked symbols and anything without a price.
2. Normalise the weights, cap each at `max_position_pct`, share the excess
   pro rata among the rest (repeat until nothing is over).
3. Keep `cash_buffer_pct` of the budget as cash.
4. For each stock, the most whole shares whose value **plus buy charges** fit
   its slice.
5. Spare rupees: add one share at a time to the stock that stays least
   overweight, as long as it fits the cash and the cap.
6. Drop any order under `min_order_inr`.
7. Report the round-trip charges percent per order and warn above
   `max_charges_pct`.

## Talking to the user

- Show the table as printed, then the one-line summary.
- If stocks were dropped because one share is more than their slice, say it
  plainly and offer: fewer stocks (`--top` on copycat), a higher cap, more
  budget, or an index ETF (NIFTYBEES costs about ₹270 a unit).
- For tiny budgets run `--charges` and show the break-even: about 3.8% on a
  ₹1,000 round trip, about 0.7% on ₹10,000, about 0.4% on ₹50,000.
- Then: "Nothing is placed. Next: /trader-risk."

## Safety

- Writes proposals only. Never calls a broker.
- Whole shares only, delivery (CNC) only, no margin.
- Not financial advice. Sizing a copy of someone's portfolio does not copy
  their results.
