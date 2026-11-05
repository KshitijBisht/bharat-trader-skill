# Changelog

## 1.0.0 (2026-11-05)

First release. An Indian port of the Trader skill pack:

- copycat: mutual-fund monthly disclosures (Parag Parikh auto-download, any AMC .xlsx) and investor stakes from SHP XBRL
- insider: SEBI PIT disclosures, NSE bulk and block deals, once-per-filing alerts
- news: NSE corporate announcements plus Google News / ET / Moneycontrol, with flags
- analyst: Integrated Filing and legacy results XBRL, YoY, TTM, P/E
- screener: rules over analyst metrics or a Screener.in CSV
- budget: whole shares, cap, buffer, Groww delivery charges
- risk: limits, charges, ASM/GSM, T2T and SME, no MIS/F&O/MTF/short by default
- broker: three gates, paper ledger by default, optional Groww Trading API
- tax: STCG 20%, LTCG 12.5% above ₹1.25 lakh, grandfathering, set-off, harvesting
- alerts: NSE clock and holidays in IST, Yahoo .NS with bhavcopy fallback, rules that ring once
- rebalance: band and charges aware, sells first
