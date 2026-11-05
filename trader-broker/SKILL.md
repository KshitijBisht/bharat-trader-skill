---
name: trader-broker
description: >-
  Order Executor for Indian stocks. Turns an APPROVED order into a plain ticket
  plus the exact arguments of Groww's place_order (NSE/BSE, CASH segment, CNC
  delivery), records the user's explicit yes word for word, then fills it on the
  local paper ledger (the default) or, only if the user has set up their own
  Groww Trading API keys in environment variables and turned paper off, sends it
  to Groww. Never places anything without risk PASS + the user's typed yes + the
  agent's own permission prompt. Covers Groww Trading API setup (API key and
  TOTP, never in chat), after-market orders, booking real fills from the
  contract note, and Zerodha / Upstox / Dhan equivalents. Use when the user says
  "place the orders", "buy it", "execute", "send it to Groww", "connect Groww",
  "set up paper trading", or after /trader-risk passes.
argument-hint: "[order number]"
---

# trader-broker

The only skill in this pack that can lead to a real order, so it is the
strictest. An order is filled (paper) or sent (Groww) only after three separate
gates, every time, for every order:

1. **trader-risk passed this exact order today** (matched by fingerprint, IST date).
2. **The user typed an explicit yes for this one order** in the chat.
3. **The user approved the command** in your agent's permission prompt. Keep
   `ticket.py place` on "ask every time"; never add it to an always-allow list.

Two yeses from the user, one PASS from the rules. No yes, no order.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show [--json]           # every ticket, READY or not
python3 "${CLAUDE_SKILL_DIR}/ticket.py" approve --index 1 --reply "yes"
python3 "${CLAUDE_SKILL_DIR}/ticket.py" place --index 1         # paper fill at the last price
python3 "${CLAUDE_SKILL_DIR}/ticket.py" place --index 1 --live  # Groww; needs paper=false + env keys
python3 "${CLAUDE_SKILL_DIR}/ticket.py" result --index 1 --status EXECUTED --broker-id GMK...
python3 "${CLAUDE_SKILL_DIR}/ticket.py" fill --symbol ITC --side BUY --qty 6 --price 409.85 --charges 8.21
python3 "${CLAUDE_SKILL_DIR}/ticket.py" log
```

`ticket.py` refuses an order that is not READY, refuses a reply that is not an
explicit yes, and refuses `--live` while `"paper": true`. The user's latest
reply counts: a "no" after a "yes" cancels it. A buy that risk only passed
because a sell above it frees the cash shows `WAITING FOR SELLS` until those
sells are placed. It never reads keys
from files or the chat, only from environment variables.

## The flow, every time

1. Run `ticket.py show`. For each order, quote the ticket line exactly, e.g.
   `Buy 6 ITC on NSE, market, day, delivery (CNC), est. ₹2,460.00 + ₹8.35 charges [PAPER]`.
2. If any ticket says `NEEDS RISK CHECK` or `BLOCKED`, stop and send the user
   to `/trader-risk`. Never edit orders.json to get round a block.
3. Ask about **one order at a time**: "Place order #2: Buy 6 ITC ...? Reply yes
   to place it." Do not batch ("yes to all" is not accepted; ask again per order).
4. Pass the user's reply **word for word** to `approve --reply`. Do not
   paraphrase it into a yes. "ok I guess", "sure?", "maybe" and anything with a
   question mark are not a yes; the script rejects them and logs the decline.
5. Run `place --index N` (add `--live` only in live mode). The user approves the
   command in the permission prompt.
6. Paper: the fill is booked at the last price in trader/prices.json with the
   modelled charges. Live: report Groww's `groww_order_id` and `order_status`, then
   ask the user to confirm the fill from the Groww app or contract note and book
   it with `fill` (actual price and charges) so the ledger matches reality.

Outside market hours (09:15-15:30 IST, NSE trading days) Groww queues orders as
after-market orders (AMO). Say so on the ticket. A MARKET AMO fills at the next
open price, which can gap far from today's close; suggest a LIMIT price instead.

## Paper mode (the default)

Everything runs locally. `trader/portfolio.json` is the ledger: cash, FIFO lots
with charges in their cost, realized gains for `/trader-tax`. Start with
`"budget"` in config.json as cash. Paper mode is the right way to run the ₹1,000
experiment: same tickets, same gates, no money at risk.

## Live mode: Groww Trading API (the user does this, not you)

The user sets it up on their own machine. Never ask for or accept keys, TOTP
codes, passwords, PINs or OTPs in the chat. If they paste one, tell them to
revoke it on the Groww API keys page now.

1. Subscribe to the Trading API: groww.in, Profile, Trading APIs
   (paid monthly; see Groww for the current price).
2. On https://groww.in/trade-api/api-keys choose **Generate TOTP token** (no daily
   expiry) or **Generate API key** (needs approval on that page every day).
3. Install the SDK in the same Python: `pip install growwapi pyotp`.
4. In their shell profile (not in any file in this repo):
   ```bash
   export GROWW_API_KEY="..."         # the TOTP token or API key
   export GROWW_TOTP_SECRET="..."     # TOTP flow, or:
   export GROWW_API_SECRET="..."      # API key + secret flow
   ```
5. Set `"paper": false` in `trader/config.json`.

SEBI's retail algo framework (in force from 2025) lets brokers allow API orders
from retail clients with registration, a static IP for higher order rates, and
per-order client approval below the algo threshold. This pack places one order
per explicit human yes, which is the "decision support" pattern, not an
autonomous algo. If Groww asks for a static IP or algo registration, the user
follows Groww's instructions; you do not work around them.

## Other brokers

Tickets use Groww's field names. The same order maps 1:1 to:

| Groww `place_order` | Zerodha Kite Connect | Upstox v2 | Dhan |
| --- | --- | --- | --- |
| trading_symbol | tradingsymbol | instrument_token (look up) | securityId (look up) |
| exchange NSE/BSE | exchange NSE/BSE | NSE_EQ/BSE_EQ in token | exchangeSegment NSE_EQ |
| segment CASH | (implied by exchange) | (in token) | (in segment) |
| product CNC | product CNC | product D | productType CNC |
| order_type MARKET/LIMIT/SL/SL_M | MARKET/LIMIT/SL/SL-M | MARKET/LIMIT/SL/SL-M | MARKET/LIMIT/STOP_LOSS/... |
| transaction_type BUY/SELL | BUY/SELL | BUY/SELL | BUY/SELL |
| validity DAY | validity DAY | validity DAY | validity DAY |

Only Groww is wired into `ticket.py`. For another broker, show the ticket and
let the user place it in their app, then book it with `fill`.

## Safety

- Paper is the default. `--live` is refused unless config says `"paper": false`.
- No order without a PASS from `/trader-risk` today for that exact order.
- No order without the user's own explicit yes for that order, recorded verbatim.
- Never place, modify or cancel orders from any other skill or script.
- No intraday (MIS), F&O, MTF, short selling or margin unless the user turned
  them on in config and `/trader-risk` passed it.
- Keys only in environment variables; never in chat, files, logs or commits.
- Not financial advice. You can lose money. The user decides.
