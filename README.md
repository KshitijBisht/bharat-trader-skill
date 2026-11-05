# The Bharat Trader skill

11 agent skills for the Indian stock market. They copy the funds and investors
you trust, watch NSE filings and insider trades, size every trade to your rupees
with real charges, and never place an order without your yes.

The skills are free, MIT-licensed and need no signup or API key. The tools are
plain Python that read public Indian data: NSE filings and bhavcopies, SEBI
insider disclosures, AMC portfolio files and news feeds.

What the skills do:

- **Copy a fund or an investor.** One skill rebuilds Parag Parikh Flexi Cap's
  portfolio from its monthly SEBI disclosure. It can also find Rekha
  Jhunjhunwala under every family trust in a company's shareholding pattern.
- **Watch insiders.** Another reads promoter and director trades within days of
  the filing, plus every bulk and block deal on NSE.
- **Manage your budget.** One sizes your rupees into whole shares and counts
  every paisa of brokerage, STT, stamp duty, GST and DP charges. It tells you
  honestly when ₹1,000 is too small to beat them.

No trade goes through until you say yes. Nothing in this pack can place an
order on its own. Paper trading is the default, and live orders go only through
your own Groww Trading API keys.

> India port of [Jakeschincariol/trader-skill](https://github.com/Jakeschincariol/trader-skill)
> (MIT), rebuilt for NSE/BSE, rupees, Indian charges, SEBI disclosures and Indian tax.

## Install

Paste this into Claude:

```
https://github.com/KshitijBisht/bharat-trader-skill

install skill
```

Or install it as a plugin in Claude Code:

```
/plugin marketplace add KshitijBisht/bharat-trader-skill
/plugin install bharat-trader-skill@bharat-trader-skill
```

Or copy the folders. Keep `trader-common/` next to the skills, because every
tool imports it:

```bash
git clone https://github.com/KshitijBisht/bharat-trader-skill.git
cp -r bharat-trader-skill/trader-* ~/.claude/skills/        # includes trader-common
```

It works in any agent that reads `SKILL.md` files, such as Claude Code, GitHub
Copilot or Codex. Each `SKILL.md` tells the agent which script to run. With no
agent, run the scripts yourself; every one has `--help`.

The tools need Python 3.9 or newer and nothing from pip. The Groww SDK is only
needed for live orders: `pip install growwapi pyotp`.

## The eleven

| command | job | what it does |
| --- | --- | --- |
| `/trader-copycat` | Reverse Engineer | Rebuilds a mutual fund's full portfolio from its monthly SEBI disclosure, or an investor's stakes from quarterly shareholding patterns. Shows what was new, added, trimmed or sold. |
| `/trader-news` | News Monitor | Watches NSE corporate announcements and headlines for every stock you hold. Flags RED items: auditor exits, pledges, defaults, SEBI orders. |
| `/trader-budget` | Budget Manager | Sizes positions in whole shares, keeps a cash buffer and a per-stock cap, and counts every rupee of charges. |
| `/trader-insider` | Insider Tracker | Reads SEBI PIT disclosures (promoter and director trades) and NSE bulk and block deals, and alerts once per new filing. |
| `/trader-analyst` | Earnings Analyst | Pulls quarterly results from NSE XBRL: revenue, EBITDA, net profit, EPS, margins, year-on-year changes and TTM. |
| `/trader-screener` | Stock Screener | Screens companies against your own rules. Reads the analyst's metrics or a Screener.in CSV and ranks what passes. |
| `/trader-risk` | Risk Manager | Blocks anything over your limits: order size, cap, buffer, charges, ASM/GSM surveillance, SME and T2T stocks, intraday, F&O and margin. |
| `/trader-broker` | Order Executor | Turns an approved order into a Groww `place_order` ticket and records your yes. Fills it on paper, or through Groww if you set that up. |
| `/trader-tax` | Tax Optimizer | Works out STCG at 20%, and LTCG at 12.5% above ₹1.25 lakh. Handles 2018 grandfathering, loss set-off, and tax-loss and tax-gain harvesting. |
| `/trader-alerts` | Price Alerts | Fetches quotes (Yahoo `.NS`, with the NSE bhavcopy as fallback) and knows NSE hours in IST and the holidays. Rings on targets, stops, moves and the opening bell. |
| `/trader-rebalance` | Rebalancer | Brings the portfolio back to target weights, but only when the drift is worth the charges. |

## How to use it

Everything lands in a `trader/` folder in your project, and each skill reads
what the previous one wrote:

```
copycat -> budget -> risk -> broker            (copy a fund or an investor)
news / insider / alerts                         (watch, on a schedule)
analyst -> screener -> budget -> risk -> broker (pick your own)
rebalance / tax -> risk -> broker               (maintain)
```

Start by copying [`trader-budget/config.example.json`](trader-budget/config.example.json)
to `trader/config.json` and setting your budget.

### Example: copy Parag Parikh Flexi Cap with ₹10,000

This is real output, from the September 2026 disclosure and the 4 Nov 2026 NSE close.

1. **`/trader-copycat`**: "copy Parag Parikh Flexi Cap's top 5". It reads the
   fund's 30 Sep 2026 portfolio: 33 listed Indian stocks, 72.06% of NAV. The top
   five are HDFC Bank 7.75%, Power Grid 5.60%, ITC 5.49%, Coal India 5.39% and
   ICICI Bank 5.24%. Against August, it shows the fund added DLF (13.7 to 52.8
   million shares), Indus Towers and Petronet, and sold out of Great Eastern
   Shipping. It leaves out the fund's Alphabet, Meta, Microsoft and Amazon
   holdings, because those are not NSE stocks. It writes `trader/targets.json`.
2. **`/trader-alerts quote`** fetches prices: HDFCBANK ₹736.70, POWERGRID ₹262.05,
   ITC ₹280.00, COALINDIA ₹399.65, ICICIBANK ₹1,424.10.
3. **`/trader-budget`**: ₹10,000 with a 5% buffer and a 25% cap gives:

   ```
   #  symbol     target  qty  price      value      buy charges  round trip
   1  HDFCBANK   25.00%    3    ₹736.70  ₹2,210.10        ₹8.31       1.80%
   2  POWERGRID  19.34%    7    ₹262.05  ₹1,834.35        ₹8.24       2.17%
   3  ITC        18.96%    7    ₹280.00  ₹1,960.00        ₹8.26       2.03%
   4  COALINDIA  18.61%    5    ₹399.65  ₹1,998.25        ₹8.27       1.99%
   5  ICICIBANK  18.09%    1  ₹1,424.10  ₹1,424.10        ₹7.16       2.65%
   Spent ₹9,467.04 incl. charges | cash left ₹532.96
   ```
4. **`/trader-risk`** passes four orders and blocks ICICI Bank. One share is a
   ₹1,424 order, and its round-trip charges are 2.65%, over your 2.5% limit.
5. **`/trader-broker`** shows each ticket, for example "Buy 7 ITC on NSE,
   market, day, delivery (CNC), est. ₹1,960.00 + ₹8.26 charges [PAPER]". You
   type yes for that exact order, and your agent asks you once more before
   running it. In paper mode the order fills on your local ledger.
6. On a schedule:
   - **`/trader-news --new`** flags filings on your stocks.
   - **`/trader-insider new`** shows promoter trades and bulk deals in them.
   - **`/trader-alerts check`** rings on your price levels.
7. Every month, **`/trader-copycat`** diffs the new disclosure against the last
   one. Then **`/trader-rebalance`** proposes the trades to match it again, but
   only where the drift is worth the charges.

### And with ₹1,000?

```
$ python3 trader-budget/size.py --charges 1000
Round trip at the same price: ₹37.63 = 3.76% of the order.
```

Groww charges a minimum of ₹5 brokerage per side and about ₹23.60 DP charge
(₹20 + GST) every time you sell. On a ₹1,000 order, the stock has to rise
almost 4% just for you to break even. Five-stock copies don't fit at all,
because one share of HDFC Bank is already more than a ₹237 slice. Even 3 units
of NIFTYBEES (₹818) cost 4.6% in charges for a round trip. `/trader-risk`
blocks that by default, and says why.

So run the ₹1,000 experiment in **paper mode**: same tickets, same gates, no
money lost to charges. Go live once you would put in at least ₹10,000 and hold
for months, not days.

## The tools

All of them are standard-library Python. The data tools read public endpoints
politely: a browser user agent, NSE's cookie warm-up, a gap between requests and
backoff on 429.

```bash
python3 trader-copycat/copycat.py fund PPFCF --top 10           # Parag Parikh Flexi Cap, last month
python3 trader-copycat/copycat.py investor rekha                # Rekha Jhunjhunwala's 1%+ stakes
python3 trader-copycat/copycat.py shp TITAN                     # every named holder
python3 trader-news/news.py --symbols ITC TITAN --hours 48      # NSE filings + headlines
python3 trader-insider/insider.py pit --symbol ITC --market-only
python3 trader-insider/insider.py deals                         # today's bulk + block deals
python3 trader-analyst/facts.py ITC TITAN --write               # quarters, YoY, TTM -> metrics.json
python3 trader-screener/screen.py --rules trader/rules.json
python3 trader-budget/size.py --budget 10000 --write            # -> trader/orders.json
python3 trader-budget/size.py --charges 1000                    # what an order really costs
python3 trader-risk/check.py surveillance --fetch && python3 trader-risk/check.py
python3 trader-broker/ticket.py show                            # the tickets, READY or not
python3 trader-tax/lots.py harvest                              # with the ₹1.25 lakh LTCG exemption
python3 trader-alerts/alerts.py clock                           # NSE open or closed, in IST
python3 trader-rebalance/rebalance.py --band 5                  # the drift table
```

```bash
python3 -m unittest discover -s tests -v
```

The tests run offline on fixtures cut from real files:
- Parag Parikh's August and September 2026 disclosures
- Titan, Metro Brands and Infosys shareholding-pattern XBRL
- ITC Integrated Filing and Infosys legacy results XBRL
- NSE PIT, bulk-deal, announcement, holiday, ASM/GSM and bhavcopy files

## Docs

- [docs/setup-groww.md](docs/setup-groww.md): paper first, then Groww Trading API keys done safely
- [docs/charges.md](docs/charges.md): every charge on an Indian delivery trade, with worked numbers
- [docs/data-sources.md](docs/data-sources.md): every endpoint, what it gives and how it fails
- [docs/sebi-and-safety.md](docs/sebi-and-safety.md): SEBI's retail algo rules, PIT, and the three gates
- [examples/](examples/): a ready `trader/` folder, rules and a ₹10,000 walkthrough script

## Fine print

**Not financial advice.** This is software that reads public data and does
arithmetic. It doesn't know your situation and can't see the future. Copying an
investor doesn't copy their results. You can lose money. Decide for yourself,
and talk to a SEBI-registered investment adviser if you need advice.

**No trade goes through until you say yes.** Three gates apply to every order:
1. `/trader-risk` passed that exact order today.
2. You typed yes for it in the chat, and your words are logged.
3. Your agent's permission prompt asks you before the command runs.

Keep `ticket.py place` on "ask every time". No intraday, F&O, margin (MTF) or
short selling is allowed unless you turn it on.

**Paper first.** `"paper": true` is the default. Live mode needs `"paper": false`,
`--live` on the command, and your Groww keys in environment variables. Never
put keys in the chat or in files.

**Filings are late and partial.**
- Fund portfolios are month-end snapshots, published about 10 days later.
- Shareholding patterns are quarterly, up to 21 days late, and only name
  holders of 1% or more.
- Insider trades are reported within about 4 trading days.

You see what they held, not what they hold today.

**Insider disclosures are public, not inside information.** The insider skill
reads filings that SEBI requires to be published. It has no access to anything
that isn't public.

**The data comes from free public sources.** NSE's website APIs are unofficial
and change without notice. Yahoo's chart endpoint is unofficial and
rate-limited. Check anything that matters against your broker before you act on
it.

**Taxes and charges.** `/trader-tax` applies the Finance (No. 2) Act 2024 rates.
Charges follow Groww's published schedule as of 5 Nov 2026 (`trader-common/inr.py`).
Both can change, and both can be overridden in config. Neither is tax advice.

## Files

```
trader-common/     inr.py (charges, IST calendar, HTTP, Groww order shape), ledger.py, xbrl.py, xlsx.py
trader-copycat/    SKILL.md, copycat.py, investors.json
trader-news/       SKILL.md, news.py
trader-budget/     SKILL.md, size.py, config.example.json
trader-insider/    SKILL.md, insider.py
trader-analyst/    SKILL.md, facts.py
trader-screener/   SKILL.md, screen.py, rules.example.json
trader-risk/       SKILL.md, check.py
trader-broker/     SKILL.md, ticket.py
trader-tax/        SKILL.md, lots.py
trader-alerts/     SKILL.md, alerts.py
trader-rebalance/  SKILL.md, rebalance.py
docs/              setup, charges, data sources, SEBI and safety
examples/          a sample trader/ folder and a walkthrough
tests/             unittest suite + offline fixtures from real NSE / AMC files
```

MIT. Made by [Kshitij Bisht](https://github.com/KshitijBisht), building on the
original Trader skill by [Jake Schincariol](https://github.com/Jakeschincariol/trader-skill).
