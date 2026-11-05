---
name: trader-analyst
description: >-
  The Earnings Analyst for Indian companies. Reads quarterly results straight
  from the XBRL every listed company files with NSE (SEBI Integrated Filing
  from Dec 2024, the legacy results feed before that): revenue from operations,
  other income, EBITDA, profit before tax, net profit, diluted EPS, EBITDA and
  net margins, each quarter against the same quarter a year earlier, and the
  trailing twelve months. Consolidated by default, standalone on request. Flags
  big other income and exceptional items, and with a price adds P/E, earnings
  yield and market cap. Writes trader/metrics.json for the screener. Use when
  the user says "how were ITC's results", "Q2 results of TITAN", "analyse the
  earnings", "what changed this quarter", "is profit growing", "compare these
  companies", or "P/E of".
argument-hint: "[NSE symbols]"
---

# trader-analyst

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/facts.py" ITC                     # 5 quarters + TTM, consolidated
python3 "${CLAUDE_SKILL_DIR}/facts.py" ITC --standalone
python3 "${CLAUDE_SKILL_DIR}/facts.py" ITC TITAN INFY --write  # -> trader/metrics.json
```

Numbers are in ₹ crore (1 crore = 10 million). Run `/trader-alerts quote` first
if you want P/E and market cap in the metrics file.

## How to read it for the user

1. **Revenue YoY** first: is the business growing? Compare with the same quarter
   last year, never the previous quarter (Indian businesses are seasonal:
   festive Q3, monsoon, March year-end).
2. **EBITDA margin** trend: pricing power and cost control.
3. **Net profit and EPS YoY**: does growth reach shareholders? If EPS lags
   profit, shares were issued.
4. Read the notes the tool prints: other income over 15% of income, or
   exceptional items, mean the headline profit flatters the core business.
5. If the filing's own notes say a period is "not comparable" (an acquisition,
   a merger, a tax change), say so. Example: ITC's Q2 FY27 revenue jumped ~44%
   largely because of an excise-duty change and an acquisition, while profit fell.

EBITDA is computed as PBT + finance costs + depreciation − other income −
exceptional items. Banks and NBFCs file a different format: revenue is interest
earned and EBITDA does not apply; use net profit, NII and NPA instead.

## Safety

- Reads public filings. Writes metrics, never orders. Not financial advice.
