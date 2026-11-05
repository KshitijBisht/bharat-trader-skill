---
name: trader-copycat
description: >-
  The Reverse Engineer for India. Rebuilds a portfolio you can copy from public
  filings: a mutual fund's full monthly portfolio disclosure (SEBI makes every
  AMC publish it; Parag Parikh Flexi Cap downloads automatically, any other
  AMC's .xlsx works), or a "superstar" investor such as Rekha Jhunjhunwala,
  Radhakishan Damani, Ashish Kacholia, Vijay Kedia, Mukul Agrawal or Dolly
  Khanna, found under every alias and family trust in each company's quarterly
  shareholding pattern (SHP XBRL on NSE, holdings of 1% or more). Shows each
  position's weight, what was new, added, trimmed or sold since the last month
  or quarter, maps ISINs to NSE symbols, and writes trader/targets.json for the
  budget skill. Use when the user says "copy Parag Parikh", "what does Rekha
  Jhunjhunwala own", "copy Damani", "reverse engineer this fund", "big bull
  portfolio", "shareholding pattern of TITAN", or "who owns more than 1% of".
argument-hint: "[fund id, .xlsx, or investor]"
---

# trader-copycat

Two public sources, two very different pictures. Say which one you are using.

| source | who | how complete | how fresh |
| --- | --- | --- | --- |
| **Mutual-fund monthly portfolio** (SEBI) | any fund (PPFAS, HDFC, SBI, Quant...) | every holding, with % of NAV | month-end, posted by the 10th |
| **Shareholding pattern (SHP)** (LODR Reg. 31) | individual investors | only stakes of **1% or more** of a company | quarter-end, posted within 21 days |

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/copycat.py" list                               # registry: investors + funds
python3 "${CLAUDE_SKILL_DIR}/copycat.py" fund PPFCF --top 10 --write        # Parag Parikh Flexi Cap, last month
python3 "${CLAUDE_SKILL_DIR}/copycat.py" fund PPFCF --month 2026-09
python3 "${CLAUDE_SKILL_DIR}/copycat.py" fund ~/Downloads/hdfc-flexi.xlsx --prev ~/Downloads/hdfc-flexi-aug.xlsx
python3 "${CLAUDE_SKILL_DIR}/copycat.py" investor rekha                     # registry's symbols to check
python3 "${CLAUDE_SKILL_DIR}/copycat.py" investor rekha --symbols TITAN CRISIL METROBRAND --write
python3 "${CLAUDE_SKILL_DIR}/copycat.py" shp TITAN                          # every named holder in TITAN
```

The investor registry with aliases lives in `investors.json` next to this file.
SHPs list a person under several names (her own, the late husband's estate,
three children's trusts, a company like Rare Enterprises); the tool sums every
alias. Add aliases there when you find new ones in an `shp` listing.

## Funds

1. `fund PPFCF` (or PPTSF) downloads this month's and last month's disclosure from
   amc.ppfas.com. Other AMCs: ask the user to download the scheme's monthly
   portfolio .xlsx from the AMC's "statutory disclosure" page (links in
   `investors.json`) and pass the path. Old `.xls` files must be re-saved as .xlsx.
2. The tool keeps listed Indian equity only and says so: foreign stocks (PPFCF
   holds Alphabet, Meta, Microsoft, Amazon), debt, REITs, arbitrage positions and
   cash are left out, and weights are renormalised to 100% of what is left.
3. `--write` -> `trader/targets.json`. `--top N` keeps the N largest.

## Investors

1. Ask which stocks to check, or use the registry's `check` list. NSE has no
   "search by holder" API; the tool reads each company's latest SHP and the one
   before it.
2. It prints shares, % of the company, value (needs prices: run
   `/trader-alerts quote` first) and the change vs last quarter. "EXITED or <1%"
   means the name disappeared: they sold out *or* fell under the 1% line.
3. `--write` weights the holdings by rupee value.

## Say this every time

- Fund portfolios are month-end snapshots published about 10 days later.
  SHPs are quarter-end and up to 21 days late. The investor may already have sold.
- SHPs only show stakes of 1% or more, so a superstar's real portfolio is bigger
  than this list.
- Copying holdings does not copy their entry prices, timing or results.

Then: "Next: /trader-budget to size it to your money."

## Safety

- Reads public filings only. Writes targets, never orders.
- Not financial advice. A famous name is not a reason to buy.
