---
name: trader-insider
description: >-
  The Insider Tracker for India, the closest thing to a "Pelosi tracker": reads
  SEBI PIT disclosures on NSE (promoters, directors, KMP and their relatives
  must report trades over Rs 10 lakh a quarter within two trading days), and the
  day's bulk and block deals (any client trading 0.5% or more of a company, or a
  Rs 10 crore+ block). Separates open-market buys and sells (the signal) from
  ESOP allotments, gifts, pledges and inter-se transfers (mostly noise), shows
  how many days each disclosure took, flags trades in stocks the user holds,
  and alerts once per new filing. Use when the user says "are insiders buying",
  "promoter buying in ITC", "insider trades", "bulk deals today", "block deals",
  "what is Kacholia buying", "track promoter selling", or "anything new from
  insiders".
---

# trader-insider

India has no stock-trade disclosure for MPs, so there is no exact "Pelosi"
equivalent. What *is* public, fast and free:

- **PIT disclosures** (SEBI Prohibition of Insider Trading Regulations 2015,
  Reg. 7(2)): company insiders report trades over ₹10 lakh in a calendar quarter
  within 2 trading days; the company passes them to the exchange within 2 more.
- **Bulk deals**: one client trading 0.5% or more of a company's shares in a day.
- **Block deals**: single trades of 5 lakh shares or ₹10 crore+ in the block window.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/insider.py" pit --symbol ITC --market-only   # one company, open-market only
python3 "${CLAUDE_SKILL_DIR}/insider.py" pit --days 7 --market-only --min-value 10000000   # all, >= ₹1 cr
python3 "${CLAUDE_SKILL_DIR}/insider.py" deals                            # latest bulk + block deals
python3 "${CLAUDE_SKILL_DIR}/insider.py" deals --client kacholia          # one name's bulk deals
python3 "${CLAUDE_SKILL_DIR}/insider.py" new                              # only new since last run, your stocks
```

`new` watches everything in `trader/portfolio.json`, `trader/targets.json` and
`"watchlist"` in config.json, and remembers what it showed in
`trader/insider-seen.json`. It is the one to put on a schedule (e.g. every
evening after 7 p.m. IST, when the day's deals and filings are in).

## Reading the results

- **Open-market purchase by a promoter or director** is the strongest signal:
  they paid market price with their own money. Clusters (several insiders in
  a few weeks) matter more than one.
- **Market sale** has many innocent reasons (tax, a house, diversification).
- **ESOP**, **Off Market**, **Inter-se transfer**, **Gift**, **Pledge creation /
  invocation** are not conviction trades. Pledge *invocation* is a red flag
  of its own: a lender sold the promoter's shares.
- Bulk deals by HFT / prop firms (AlphaGrep, NK Securities, Microcurves, Graviton,
  Junomoneta...) are market-making, not investing. Say so.
- "days" is filing date minus trade date. Over 4 trading days is late.

## Safety

- Public disclosures only. Trading on unpublished price-sensitive information
  is illegal under SEBI PIT; this skill has no access to any.
- Writes no orders. Not financial advice: an insider buying is a fact, not a tip.
