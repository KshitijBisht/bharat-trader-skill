# Examples

- [`walkthrough.sh`](walkthrough.sh) runs the README's ₹10,000 example end to
  end, offline and in paper mode. It uses the real files in `tests/fixtures`:
  ```bash
  bash examples/walkthrough.sh
  ```
- [`trader/`](trader/) is a sample working folder. Copy it into your project
  to try any skill straight away:
  ```bash
  cp -r examples/trader ./trader
  python3 trader-tax/lots.py show          # three lots, one bought before 2018
  python3 trader-tax/lots.py harvest
  python3 trader-rebalance/rebalance.py
  python3 trader-screener/screen.py        # needs trader/metrics.json: run trader-analyst first
  ```

| file | written by | read by |
| --- | --- | --- |
| `config.json` | you (from `trader-budget/config.example.json`) | every skill |
| `targets.json` | copycat, screener | budget, rebalance, news, insider |
| `prices.json` | alerts | budget, risk, broker, tax, rebalance, analyst |
| `orders.json` | budget, rebalance, tax | risk, broker |
| `risk.json` | risk | broker |
| `portfolio.json` | broker (fills), you | risk, tax, rebalance, news, insider |
| `metrics.json` | analyst | screener |
| `rules.json` | you | screener |
| `broker-log.json` | broker | broker, risk (orders per day) |
| `alerts.json`, `news-seen.json`, `insider-seen.json`, `surveillance.json`, `holidays.json`, `EQUITY_L.csv` | the skills | the skills (state and caches) |

`portfolio.json` keeps FIFO lots with charges included in cost. For shares
bought outside the pack, add a lot by hand:

```json
{"symbol": "INFY", "qty": 3, "price": 1500.0, "cost": 4505.0, "date": "2016-05-10", "fmv_2018": 1100.0}
```

`fmv_2018` is the highest price on 31 Jan 2018. Only shares bought before
1 Feb 2018 need it (grandfathering).
