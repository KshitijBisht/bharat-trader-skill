# SEBI and safety

## The three gates

An order reaches your Groww account, or the paper ledger, only after three
gates, every time:

1. **Rules.** `/trader-risk` passed that exact order today. "Exact" means the
   fingerprint of symbol, quantity, side, type, product and exchange must
   match. Verdicts expire at midnight IST.
2. **You, in words.** You typed an explicit yes for that one order. The reply
   is stored verbatim in `trader/broker-log.json`. "ok?", "maybe", "sure I
   guess?" and "yes to all" are not accepted.
3. **You, in the agent.** Your agent asks permission before running
   `ticket.py place`. Keep that command on "ask every time".

Nothing else in the pack can place an order. Budget, rebalance and tax write
proposals to `trader/orders.json` and stop.

## What the pack refuses by default

| | config switch |
| --- | --- |
| intraday (MIS) | `allow_intraday` |
| futures and options | `allow_fno` |
| margin trading facility | `allow_mtf` |
| short selling | `allow_short` |
| ASM / GSM surveillance stocks | `allow_surveillance` |
| trade-to-trade (BE/BZ) series | `allow_t2t` |
| SME platform stocks | `allow_sme` |

SEBI's own study of FY22 to FY24 found that 9 in 10 individual F&O traders
lost money. The pack keeps F&O off unless you switch it on in config yourself.

## SEBI rules this pack touches

- **Retail algo trading** (SEBI circular of 4 Feb 2025, phased in by brokers).
  Retail clients may send API orders only through a broker's registered API.
  Orders above a set frequency need a static IP and exchange-registered algo
  IDs. This pack sends one order per human approval, so it is a
  decision-support tool, not an autonomous algo. Follow whatever Groww asks
  of you.
- **Insider trading (PIT Regulations, 2015).** `/trader-insider` reads what
  insiders must disclose publicly. Trading on unpublished price-sensitive
  information is illegal; nothing here has any.
- **Investment advice (IA Regulations, 2013).** Only SEBI-registered advisers
  may give personalised investment advice for a fee. These skills do
  arithmetic on public data; they don't advise. When the user asks "should I
  buy?", the agent should say it can't advise, then show the facts and the risks.
- **Finfluencer rules (2024).** Don't present this pack's output as
  recommendations to others.

## Keys

- Groww keys live only in `GROWW_API_KEY`, `GROWW_TOTP_SECRET` and
  `GROWW_API_SECRET` environment variables.
- `.gitignore` excludes `trader/` and `.env`.
- Agents must never ask for, accept, echo or store keys, passwords, PINs,
  OTPs or TOTP codes.
