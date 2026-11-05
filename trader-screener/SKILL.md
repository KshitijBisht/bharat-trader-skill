---
name: trader-screener
description: >-
  The Stock Screener for Indian stocks. Checks a list of companies against the
  user's own rules (revenue and profit growth, margins, EPS growth, P/E,
  earnings yield, ROCE, ROE, debt to equity, promoter holding, pledge, sector,
  anything in the metrics file), says exactly which rule each company passes or
  fails and by how much, and ranks the ones that pass into a shortlist. Reads
  the metrics /trader-analyst writes from NSE filings, or any CSV export from
  Screener.in, Tickertape or a spreadsheet. Writes an equal-weight shortlist to
  trader/targets.json on request. Use when the user says "screen for stocks",
  "find me companies with", "filter my watchlist", "which of these pass",
  "shortlist", "rank these", or "low P/E high ROCE stocks".
---

# trader-screener

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
cp "${CLAUDE_SKILL_DIR}/rules.example.json" trader/rules.json      # then edit
python3 "${CLAUDE_SKILL_DIR}/screen.py"                            # trader/metrics.json + trader/rules.json
python3 "${CLAUDE_SKILL_DIR}/screen.py" ~/Downloads/screener.csv --rules trader/rules.json -v
python3 "${CLAUDE_SKILL_DIR}/screen.py" --top 5 --write            # shortlist -> trader/targets.json
```

## Rules

A rule is `{"field", "op", "value"}`, with ops `> >= < <= == != in "not in" between`.
`"missing": "pass"` lets a company through when it has no value for that field
(the default is fail). `rank` scores the companies that pass, each field
normalised 0-1, higher is better unless `"ascending": true`.

CSV headers are lower_snake_cased: Screener.in's "Return on capital employed"
becomes `return_on_capital_employed`, "Price to Earning" becomes
`price_to_earning`, "Promoter holding" becomes `promoter_holding`. Run once with
`-v` to see the exact field names.

## Building rules with the user

Ask what they care about in plain words and translate:

| they say | rule |
| --- | --- |
| "growing" | `revenue_yoy >= 10`, `net_profit_yoy >= 10` |
| "profitable" | `net_margin >= 8` or `return_on_capital_employed >= 15` |
| "not expensive" | `pe between [5, 30]` or `earnings_yield >= 4` |
| "no debt" | `debt_to_equity <= 0.3` |
| "promoters have skin in the game" | `promoter_holding >= 50`, `pledged_percentage <= 5` |

Show passes first, then each failure with the exact rule it missed. Never
silently loosen a rule to get results; offer to.

## Safety

- Writes targets, never orders. Passing a screen is not a reason to buy.
  Not financial advice.
