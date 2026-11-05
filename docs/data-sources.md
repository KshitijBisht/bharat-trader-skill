# Data sources

Every source is public and free. NSE's JSON endpoints are what the
nseindia.com website itself uses. They are not a documented API: they need a
browser-like user agent and a cookie from the home page, and they change
without notice. `trader-common/inr.py` handles the user agent, the cookie
warm-up, a gap between requests, and retries on 429 and 5xx errors.

| skill | source | endpoint | notes |
| --- | --- | --- | --- |
| copycat (funds) | AMC monthly portfolio disclosure (SEBI) | e.g. `amc.ppfas.com/downloads/portfolio-disclosure/<yyyy>/PPFCF_PPFAS_Monthly_Portfolio_Report_<Month>_<dd>_<yyyy>.xlsx` | posted by the 10th; .xlsx read with the standard library |
| copycat (investors) | Shareholding pattern master | `nseindia.com/api/corporate-share-holdings-master?index=equities&symbol=X` | lists quarterly SHP XBRL files on `nsearchives.nseindia.com` |
| copycat | NSE equity list | `nsearchives.nseindia.com/content/equities/EQUITY_L.csv` | ISIN to symbol, series, lot |
| insider | SEBI PIT disclosures | `nseindia.com/api/corporates-pit?index=equities&symbol=X` (or `&from_date=&to_date=`) | Reg. 7(2) trades by promoters, directors and KMP |
| insider | Bulk and block deals | `nseindia.com/api/snapshot-capital-market-largedeal` | the last trading day |
| news | Corporate announcements | `nseindia.com/api/corporate-announcements?index=equities&symbol=X` | LODR Reg. 30 filings with PDF links |
| news | Google News RSS | `news.google.com/rss/search?q=...&hl=en-IN&gl=IN&ceid=IN:en` | personal, non-commercial use |
| news | ET Markets, Moneycontrol RSS | see `MARKET_FEEDS` in `news.py` | |
| analyst | Integrated Filing (Financials) | `nseindia.com/api/integrated-filing-results?index=equities&symbol=X` | from the Dec 2024 quarter on |
| analyst | Legacy financial results | `nseindia.com/api/corporates-financial-results?index=equities&symbol=X&period=Quarterly` | before 2025 |
| alerts | Yahoo Finance chart | `query1.finance.yahoo.com/v8/finance/chart/ITC.NS` | unofficial, delayed, rate-limited (429) |
| alerts | NSE bhavcopy | `nsearchives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv` | official end-of-day prices, with delivery % |
| alerts | Trading holidays | `nseindia.com/api/holiday-master?type=trading` | 2026 is built in |
| risk | ASM / GSM surveillance | `nseindia.com/api/reportASM`, `nseindia.com/api/reportGSM` | refresh daily |

All XBRL (SHP, results, PIT) uses BSE/NSE taxonomies (`in-bse-shp`,
`in-bse-fin`). `trader-common/xbrl.py` reads facts by context. Shareholder
names sit on a `D_...` duration context, and their numbers on the matching
instant context.

## When a source breaks

- NSE returns 401, 403 or HTML: wait a minute and retry. The client refreshes
  its cookie once by itself. If NSE blocks you for hours, use saved files:
  every parser takes `--file` / `--files`.
- Yahoo 429: `alerts.py` stops asking and uses the latest bhavcopy, which gives
  yesterday's close until about 6 p.m. IST.
- An AMC changes its file layout: `copycat.py fund` looks for a header row with
  an `ISIN` column and a "% to net assets" column. Open an issue with the file.
