# Contributing

- Standard-library Python 3.9+ only for the data tools. The Groww SDK stays an
  optional import inside `trader-broker/ticket.py`.
- Every parser takes saved files (`--file` / `--files`) so it can be tested
  offline. Add a small real fixture under `tests/fixtures/<skill>/` with any new
  parser, and a test in `tests/`.
- Anything that can lead to an order goes through `/trader-risk` and the three
  gates in `/trader-broker`. Pull requests that add another path to a broker,
  or that loosen the gates, will not be merged.
- Never commit keys, tokens, PANs or a `trader/` folder.
- Run `python3 -m unittest discover -s tests` and `bash examples/walkthrough.sh` before opening a PR.

Good first contributions:
- more AMCs with auto-download in `trader-copycat/investors.json`
- more investor aliases
- the BSE fallback for NSE endpoints
- a Zerodha Kite Connect adapter behind the same gates
