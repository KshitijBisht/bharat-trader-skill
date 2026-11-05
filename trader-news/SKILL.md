---
name: trader-news
description: >-
  The News Monitor for Indian stocks. Watches NSE corporate announcements (SEBI
  LODR Reg. 30 disclosures: results, board meetings, mergers, buybacks,
  dividends, credit ratings, auditor and KMP resignations, pledges, orders) and
  Google News / Economic Times / Moneycontrol headlines for every stock the user
  holds, targets or watches. Shows only what is new since the last check, newest
  first, filings separate from headlines, flags each item (RED, RESULTS, DEAL,
  PEOPLE, MONEY, RATING, ORDER) and hides routine noise like newspaper ads and
  trading-window notices. Use when the user says "any news on my stocks",
  "what's happening with ITC", "monitor the news", "watch my portfolio", "did
  anything happen to TITAN", "latest filings", or "market news today".
---

# trader-news

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/news.py" --symbols ITC TITAN --hours 48
python3 "${CLAUDE_SKILL_DIR}/news.py" --new                 # holdings + targets + watchlist, unseen only
python3 "${CLAUDE_SKILL_DIR}/news.py" --market --hours 12   # plus ET Markets and Moneycontrol feeds
python3 "${CLAUDE_SKILL_DIR}/news.py" --symbols ITC --all --links
```

**Exchange filings come first** because they are the primary source: the
company itself telling NSE, usually within 30 minutes of a board decision.
Headlines are someone's reading of it.

## Flags

| flag | means |
| --- | --- |
| RED | auditor resignation, default, insolvency (IBC/NCLT), fraud, SEBI order, raids, pledge or invocation, suspension, going-concern doubt |
| RESULTS | quarterly results; follow up with `/trader-analyst SYMBOL` |
| DEAL | merger, acquisition, demerger, buyback, open offer, stake sale |
| PEOPLE | CEO / MD / CFO / KMP appointment or resignation |
| MONEY | dividend, bonus, split, rights issue, record date, QIP, preferential issue |
| RATING | credit rating action |
| ORDER | order wins and contracts |

Routine filings (newspaper publications, trading-window closures, duplicate
share certificates, Reg. 74(5) certificates, analyst-meet notices, ESOP
allotments) are hidden unless `--all`.

## Talking to the user

- Lead with RED items and anything about a stock they hold, then the rest.
- For a RED item, open the filing PDF (`--links`) and summarise what it says.
  Do not repeat a headline's spin.
- Do not turn news into a trade on your own. If the user wants to act, the
  path is `/trader-budget` or `/trader-rebalance`, then `/trader-risk`, then
  `/trader-broker`.

## Safety

- Public sources only. Writes no orders. Not financial advice.
