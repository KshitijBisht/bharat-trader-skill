# What an Indian delivery trade really costs

Every number in this pack comes from `GROWW_DELIVERY` in
[`trader-common/inr.py`](../trader-common/inr.py), which copies Groww's published
schedule (https://groww.in/pricing, checked 5 Nov 2026). Override any line
under `"charges"` in `trader/config.json`. For example, a ₹0 brokerage broker:

```json
"charges": {"brokerage_pct": 0, "brokerage_min": 0, "brokerage_max": 0, "dp_sell": 15.93}
```

## Equity delivery (CNC)

| charge | buy | sell | notes |
| --- | --- | --- | --- |
| Brokerage | 0.1%, min ₹5, max ₹20 | same | per executed order |
| STT | 0.1% | 0.1% | rounded to the rupee; not deductible for capital-gains tax |
| Stamp duty | 0.015% | none | buy side only |
| Exchange transaction | NSE 0.00297%, BSE 0.00375% | same | most BSE groups |
| SEBI turnover fee | 0.0001% | same | ₹10 per crore |
| IPFT (NSE) | 0.0001% | same | |
| DP charge | none | ₹20 per scrip per day | ₹3.50 CDSL + ₹16.50 Groww; free under ₹100 |
| GST | 18% | 18% | on brokerage, exchange, SEBI, IPFT and DP |

## Worked numbers

```
$ python3 trader-budget/size.py --charges 1000
charge     buy    sell
brokerage  ₹5.00   ₹5.00
stt        ₹1.00   ₹1.00
stamp      ₹0.15   ₹0.00
exchange   ₹0.03   ₹0.03
dp         ₹0.00  ₹20.00
gst        ₹0.91   ₹4.51
total      ₹7.09  ₹30.54
Round trip at the same price: ₹37.63 = 3.76% of the order.
```

| order value | round trip | break-even move |
| --- | --- | --- |
| ₹1,000 | ₹37.63 | 3.76% |
| ₹10,000 | ₹69.46 | 0.69% |
| ₹50,000 | ₹182.06 | 0.36% |

Two things dominate small orders:
- **The ₹5 minimum brokerage.** It applies to any order under ₹5,000.
- **The fixed ₹23.60 DP charge on every sale.** That's ₹20 plus GST.

That is why `/trader-risk` blocks orders whose round trip costs more than
`max_charges_pct` (2.5% by default). It is also why a ₹1,000 experiment belongs
in paper mode.

## Not modelled

- Intraday (MIS), F&O, MTF interest, and pledge charges. The pack trades
  delivery only.
- Auto square-off and delayed-payment penalties.
- Groww's UPI-mandate brokerage. If you pay from a UPI mandate balance instead
  of your Groww balance, brokerage is 1% with no cap. Fund your account first.
- NRI rates.
- Your actual contract note. When live, book real fills with
  `ticket.py fill ... --charges X` so the ledger matches.
