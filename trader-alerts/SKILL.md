---
name: trader-alerts
description: >-
  Price Alerts and the NSE clock. Fetches free delayed quotes for NSE and BSE
  stocks (Yahoo Finance .NS / .BO, falling back to NSE's official end-of-day
  bhavcopy with delivery percentage) and writes trader/prices.json for every
  other skill. Knows NSE hours in IST (pre-open 09:00-09:15, normal 09:15-15:30,
  closing session to 16:00), the 2026 trading holidays and Muhurat trading, and
  the next open. Alert rules ring once: above, below, stop, percent move from the
  previous close, and the opening bell. Use when the user says "price of ITC",
  "quote", "is the market open", "NSE holidays", "alert me when TITAN hits",
  "set a stop", "tell me if it falls 5%", "ring at the open", or before sizing
  or checking orders.
---

# trader-alerts

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/alerts.py" clock                    # open / closed / holiday, next open, IST
python3 "${CLAUDE_SKILL_DIR}/alerts.py" holidays --fetch         # NSE's official list -> trader/holidays.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote ITC TITAN NIFTYBEES
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote                    # everything you hold, target or ordered
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote --bhav             # official NSE close only
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add ITC below 260 --note "re-check thesis"
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add TITAN stop 4300
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add ITC move-pct 4
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add BELL bell
python3 "${CLAUDE_SKILL_DIR}/alerts.py" list
python3 "${CLAUDE_SKILL_DIR}/alerts.py" check                    # put this on a schedule
```

## Quotes

- Yahoo's chart endpoint is free, unofficial and about 15 minutes delayed, and
  it rate-limits hard (HTTP 429). On a 429 the tool stops asking and falls back.
- The NSE bhavcopy (`sec_bhavdata_full_DDMMYYYY.csv`) is official, posts around
  6 p.m. IST, and includes delivery percentage. It is yesterday's close until then.
- Always tell the user which source and time a price is from. The price that
  fills is the broker's.

## Alerts

`above` / `below` / `stop` ring once when crossed and re-arm when the price goes
back. `move-pct` rings once a day. `bell` rings once each trading day at 09:15.
A stop alert is **not a stop-loss order**: it tells the user, who can then take
a sell through `/trader-risk` and `/trader-broker`. (Groww supports real SL
orders; this pack does not place them on its own.)

To run on a schedule, use the agent's own scheduler or cron, e.g. every 15
minutes on trading days between 09:15 and 15:30 IST:
`*/15 9-15 * * 1-5 cd ~/my-trading && python3 path/to/alerts.py check`.

## Safety

- Reads public prices; never places orders, not even on a stop.
- Not financial advice.
