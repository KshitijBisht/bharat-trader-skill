# Paper first, then Groww

## 1. Paper trading (everyone starts here)

```bash
mkdir -p ~/my-trading/trader && cd ~/my-trading
cp /path/to/bharat-trader-skill/trader-budget/config.example.json trader/config.json
# edit "budget": 1000 (or whatever you want to practise with)
```

That's all. `"paper": true` is the default. Every skill works:
`ticket.py place` fills orders on `trader/portfolio.json` at the last quoted
price, with Groww's charges taken off. Run it for a month. Compare the result
with a plain Nifty 50 ETF bought on day one.

## 2. Live orders through the Groww Trading API

You do this on your own machine. Your agent must never see your keys,
passwords, PIN, OTP or TOTP codes. If one ever lands in a chat, revoke it on
the API keys page right away.

1. **Subscribe.** Go to Groww app or web, then Profile, then Trading APIs. The
   API is a paid subscription; check Groww for the current price.
2. **Create a key.** Open https://groww.in/trade-api/api-keys. Either:
   - choose **Generate TOTP token**, which has no expiry, and scan the QR code
     into an authenticator app. Save the TOTP *secret* in your shell profile.
   - or choose **Generate API key**, which you must approve on that page every
     day before use.
3. **Install the SDK** in the Python you run the skills with:
   ```bash
   pip install growwapi pyotp
   ```
4. **Set environment variables** in `~/.zshrc` or `~/.bashrc`, never in the repo:
   ```bash
   export GROWW_API_KEY="your TOTP token or API key"
   export GROWW_TOTP_SECRET="your TOTP secret"     # TOTP flow
   # or
   export GROWW_API_SECRET="your API secret"       # key + daily approval flow
   ```
5. **Turn paper off** in `trader/config.json`: `"paper": false`.
6. **Place an order:** `ticket.py place --index 1 --live`. You will be asked twice:
   once by the skill, for your typed yes, and once by your agent's permission
   prompt. Then:
   - check the order in the Groww app.
   - book the actual fill so the ledger matches:
     `ticket.py fill --symbol ITC --side BUY --qty 7 --price 279.85 --charges 8.26`.

`ticket.py` calls exactly one SDK method, `GrowwAPI.place_order`. It passes
`segment="CASH"`, `product="CNC"` and `validity="DAY"`. It does not modify or
cancel orders, read holdings, or touch F&O.

### Limits worth knowing

- Groww rate limits: orders 10/s and 250/min; quotes 10/s; access tokens 150 a day.
- SEBI's retail algo framework (circular of 4 Feb 2025, phased in by brokers)
  covers API orders from retail clients:
  - orders go through the broker's registered API.
  - above a small orders-per-second threshold, a static IP and algo
    registration are needed.
  - Groww tells you what applies.

  This pack sends one order per human yes, far below any threshold.
- Outside 09:15 to 15:30 IST, Groww accepts after-market orders (AMO). A MARKET
  AMO fills at the next open, which can gap. Prefer LIMIT.

## Other brokers

Only Groww is wired in. For Zerodha (Kite Connect), Upstox, Dhan or Angel One:
1. Use `ticket.py show --json` to get the exact order. The field mapping is
   in `trader-broker/SKILL.md`.
2. Place the order yourself in the broker's app.
3. Book it with `ticket.py fill`.

Pull requests adding another broker behind the same three gates are welcome.
