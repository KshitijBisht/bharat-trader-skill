---
name: trader-tax
description: >-
  Tax Optimizer for Indian listed shares. Tracks cost-basis lots (FIFO, the way
  demat shares are delivered), shows each lot's holding period and whether it is
  short term (12 months or less, STCG 20% under section 111A) or long term (LTCG
  12.5% under 112A above the Rs 1.25 lakh yearly exemption), applies the
  31 Jan 2018 grandfathering rule, works out what a sale would realize and the
  extra tax before you sell, sums the financial year (April-March) with loss
  set-off and carry-forward, and finds tax-loss and tax-gain harvesting ideas
  and lots about to turn long term. Writes harvest sells only as proposals. Not
  tax advice. Use when the user says "what are my gains", "capital gains",
  "LTCG", "STCG", "tax on selling", "tax-loss harvesting", "use my 1.25 lakh
  exemption", "cost basis", or "when does it become long term".
---

# trader-tax

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/lots.py" show                     # every open lot: days held, ST/LT, gain
python3 "${CLAUDE_SKILL_DIR}/lots.py" sell ITC 12              # what that sale realizes and the extra tax
python3 "${CLAUDE_SKILL_DIR}/lots.py" realized --fy FY2026-27  # the year so far, set-off, carry forward
python3 "${CLAUDE_SKILL_DIR}/lots.py" harvest --min-loss 500 [--write]
```

Lots come from `trader/portfolio.json`. Paper fills and `ticket.py fill` add
them; for shares bought elsewhere, add lots by hand (`symbol`, `qty`, `price`,
`cost` including charges, `date`, and `fmv_2018` for pre-2018 shares: the
highest price on 31 Jan 2018).

## The rules it applies (listed shares, STT paid, sales from 23 July 2024)

| | short term | long term |
| --- | --- | --- |
| holding | 12 months or less | more than 12 months |
| rate | 20% (s. 111A) | 12.5% above ₹1,25,000 a year (s. 112A) |
| losses offset | ST and LT gains | LT gains only |
| carry forward | 8 years, if the ITR is filed on time | same |

Plus 4% cess. Surcharge, rebate u/s 87A and the user's slab are **not** modelled.
STT is not deductible. Buy charges add to cost; sell charges reduce proceeds.
The financial year runs April to March. Rates are in `TAX` at the top of
`lots.py` and can be overridden under `"tax"` in config.json when budgets change.

## Harvesting

- **LOSS**: sell a losing lot to book a loss against this year's gains. India
  has no wash-sale rule, so the user can buy back, but a same-day sell-and-buy
  nets off as intraday; leave at least a day.
- **GAIN**: book long-term gains up to the ₹1.25 lakh exemption, tax free, and
  rebuy to raise the cost basis.
- **WAIT**: a lot turns long term within 60 days; selling now costs 20% instead
  of 12.5%.
- Every round trip pays charges (see `/trader-budget --charges`); on small lots
  they can exceed the tax saved. Say so.

## Safety

- Proposals only (`--write` -> trader/orders.json, then `/trader-risk`, then
  `/trader-broker`). Never sells on its own.
- Not tax advice. For anything beyond arithmetic, a chartered accountant.
