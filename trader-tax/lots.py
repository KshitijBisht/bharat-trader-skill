#!/usr/bin/env python3
"""Tax Optimizer: Indian capital gains on listed shares, lot by lot. Not tax advice.

The rules it applies (listed equity shares where STT was paid, after 23 July 2024):
  * Held more than 12 months -> long term (LTCG, section 112A): 12.5% on gains above
    Rs 1,25,000 per financial year (April-March).
  * Held 12 months or less -> short term (STCG, section 111A): 20%.
  * Shares bought before 1 Feb 2018 are grandfathered: cost = higher of actual cost and
    the lower of (FMV on 31 Jan 2018, sale price). Give the FMV per lot.
  * Losses: short-term losses offset short- or long-term gains; long-term losses only
    long-term gains. Unused losses carry forward 8 years if you file your ITR on time.
  * No wash-sale rule in India, but a sell-and-rebuy done only to dodge tax can be
    questioned (GAAR / sham transaction). Rebuying the next trading day is common.
  * Plus 4% health and education cess on the tax; surcharge depends on income.
  * Charges: buy-side charges add to cost, sell-side charges reduce proceeds; STT
    itself is NOT deductible for these sections.

  python3 lots.py show                        # every open lot: held days, term, unrealized gain
  python3 lots.py sell ITC 6                  # what selling 6 ITC today would realize (FIFO)
  python3 lots.py realized [--fy FY2026-27]   # booked gains this FY and the estimated tax
  python3 lots.py harvest                     # tax-loss and tax-gain harvesting ideas
  python3 lots.py harvest --write             # ... as sell proposals in trader/orders.json
"""

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trader-common"))
import inr as T  # noqa: E402
import ledger as L  # noqa: E402

TAX = {
    "stcg_rate": 20.0,
    "ltcg_rate": 12.5,
    "ltcg_exemption": 125000.0,
    "cess_pct": 4.0,
    "long_term_after_months": 12,
    "grandfather_date": "2018-01-31",
    "rules_as_of": "Finance (No. 2) Act 2024, sales on or after 2024-07-23",
}


def tax_cfg(cfg):
    t = dict(TAX)
    t.update(cfg.get("tax") or {})
    return t


def is_long(buy, sell, t):
    b = dt.date.fromisoformat(buy[:10])
    s = dt.date.fromisoformat(sell[:10])
    months = t["long_term_after_months"]
    y, m = b.year + (b.month - 1 + months) // 12, (b.month - 1 + months) % 12 + 1
    day = min(b.day, [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return s > dt.date(y, m, day)          # "more than 12 months"


def grandfathered_cost(lot_cost, qty, buy_date, sale_price, fmv, t):
    if fmv is None or buy_date > t["grandfather_date"]:
        return lot_cost
    return max(lot_cost, qty * min(float(fmv), float(sale_price)))


def lot_view(lot, price, today, t):
    long_ = is_long(lot["date"], today, t)
    value = lot["qty"] * price
    sell_ch = T.charges("SELL", value)["total"] if value else 0
    cost = grandfathered_cost(lot["cost"], lot["qty"], lot["date"], price, lot.get("fmv_2018"), t)
    held = (dt.date.fromisoformat(today) - dt.date.fromisoformat(lot["date"][:10])).days
    lt_on = None
    if not long_:
        b = dt.date.fromisoformat(lot["date"][:10])
        for add in range(360, 380):
            if is_long(lot["date"], (b + dt.timedelta(days=add)).isoformat(), t):
                lt_on = (b + dt.timedelta(days=add)).isoformat()
                break
    return {"symbol": lot["symbol"], "qty": lot["qty"], "date": lot["date"], "held_days": held,
            "term": "LT" if long_ else "ST", "long_term_from": lt_on, "cost": round(cost, 2),
            "value": round(value, 2), "net_value": round(value - sell_ch, 2),
            "gain": round(value - sell_ch - cost, 2)}


def tax_on(st_gain, lt_gain, t, exemption_left=None):
    """Tax on one FY's net gains after set-off. Gains/losses are net numbers per bucket."""
    ex = t["ltcg_exemption"] if exemption_left is None else exemption_left
    st, lt = st_gain, lt_gain
    carry = {"st_loss": 0.0, "lt_loss": 0.0}
    if st < 0:                              # short-term loss can eat long-term gains
        use = min(-st, max(lt, 0))
        lt -= use
        st += use
        carry["st_loss"] = -st
        st = 0.0
    if lt < 0:                              # long-term loss stays long-term
        carry["lt_loss"] = -lt
        lt = 0.0
    taxable_lt = max(0.0, lt - ex)
    tax = st * t["stcg_rate"] / 100 + taxable_lt * t["ltcg_rate"] / 100
    tax *= 1 + t["cess_pct"] / 100
    return {"st_net": round(st, 2), "lt_net": round(lt, 2), "lt_exempt_used": round(min(lt, ex), 2),
            "taxable_lt": round(taxable_lt, 2), "tax": round(tax, 2), "carry_forward": carry}


def realized_by_fy(p, fy, t):
    st = lt = 0.0
    rows = []
    for r in p.get("realized", []):
        if T.financial_year(r["sell_date"]) != fy:
            continue
        long_ = is_long(r["buy_date"], r["sell_date"], t)
        cost = grandfathered_cost(r["cost"], r["qty"], r["buy_date"], r["sell_price"], r.get("fmv_2018"), t)
        g = r["proceeds"] - cost
        if long_:
            lt += g
        else:
            st += g
        rows.append(dict(r, term="LT" if long_ else "ST", taxable_gain=round(g, 2)))
    return rows, st, lt


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    s = sub.add_parser("sell")
    s.add_argument("symbol")
    s.add_argument("qty", type=int)
    s.add_argument("--price", type=float)
    s = sub.add_parser("realized")
    s.add_argument("--fy")
    s = sub.add_parser("harvest")
    s.add_argument("--min-loss", type=float, default=500, help="rupees")
    s.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    cfg = T.config()
    t = tax_cfg(cfg)
    p = L.load()
    px = T.prices()
    today = T.now_ist().date().isoformat()
    fy = getattr(a, "fy", None) or T.financial_year(today)

    if a.cmd == "show":
        rows, miss = [], set()
        for lot in p["lots"]:
            price = px.get(lot["symbol"])
            if not price:
                miss.add(lot["symbol"])
                continue
            v = lot_view(lot, price, today, t)
            rows.append([v["symbol"], v["qty"], v["date"], v["held_days"], v["term"], v["long_term_from"] or "",
                         T.inr(v["cost"]), T.inr(v["net_value"]), T.inr(v["gain"])])
        print(T.table(rows, ["symbol", "qty", "bought", "days", "term", "LT from", "cost", "value after sell charges",
                             "gain"]) if rows else "No open lots in trader/portfolio.json.")
        if miss:
            print("no price for %s: run trader-alerts quote" % ", ".join(sorted(miss)))
        return 0

    if a.cmd == "sell":
        sym = a.symbol.upper()
        price = a.price or px.get(sym)
        if not price:
            T.die("No price for %s. Pass --price or run trader-alerts quote." % sym)
        lots = [l for l in p["lots"] if l["symbol"] == sym]
        if sum(l["qty"] for l in lots) < a.qty:
            T.die("You hold %d %s." % (sum(l["qty"] for l in lots), sym))
        value = a.qty * price
        ch = T.charges("SELL", value)
        left, st, lt = a.qty, 0.0, 0.0
        rows = []
        for lot in lots:                       # FIFO, as depositories deliver
            if left == 0:
                break
            take = min(left, lot["qty"])
            part = dict(lot, qty=take, cost=lot["cost"] * take / lot["qty"])
            cost = grandfathered_cost(part["cost"], take, lot["date"], price, lot.get("fmv_2018"), t)
            proceeds = (value - ch["total"]) * take / a.qty
            g = proceeds - cost
            term = "LT" if is_long(lot["date"], today, t) else "ST"
            st, lt = (st + g, lt) if term == "ST" else (st, lt + g)
            rows.append([lot["date"], take, term, T.inr(cost), T.inr(proceeds), T.inr(g)])
            left -= take
        print("Selling %d %s @ %s (FIFO), sell charges %s:" % (a.qty, sym, T.inr(price), T.inr(ch["total"])))
        print(T.table(rows, ["lot bought", "qty", "term", "cost", "proceeds", "gain"]))
        _, st0, lt0 = realized_by_fy(p, fy, t)
        before = tax_on(st0, lt0, t)
        after = tax_on(st0 + st, lt0 + lt, t)
        print("%s so far: ST %s, LT %s. This sale adds ST %s, LT %s. Estimated extra tax: %s (incl. %s%% cess)."
              % (fy, T.inr(st0), T.inr(lt0), T.inr(st), T.inr(lt), T.inr(after["tax"] - before["tax"]), t["cess_pct"]))
        return 0

    if a.cmd == "realized":
        rows, st, lt = realized_by_fy(p, fy, t)
        out = [[r["symbol"], r["qty"], r["buy_date"], r["sell_date"], r["term"], T.inr(r["cost"]), T.inr(r["proceeds"]),
                T.inr(r["taxable_gain"])] for r in rows]
        print(T.table(out, ["symbol", "qty", "bought", "sold", "term", "cost", "proceeds", "gain"]) if out
              else "No sales in %s." % fy)
        x = tax_on(st, lt, t)
        print("%s: short-term %s, long-term %s (exemption used %s of %s). Estimated tax %s. Carry forward: ST loss %s, "
              "LT loss %s." % (fy, T.inr(x["st_net"]), T.inr(x["lt_net"]), T.inr(x["lt_exempt_used"]),
                               T.inr(t["ltcg_exemption"]), T.inr(x["tax"]), T.inr(x["carry_forward"]["st_loss"]),
                               T.inr(x["carry_forward"]["lt_loss"])))
        print("Rules as of %s. Not tax advice: surcharge, rebates and your slab are not modelled." % t["rules_as_of"])
        return 0

    if a.cmd == "harvest":
        _, st0, lt0 = realized_by_fy(p, fy, t)
        exempt_left = max(0.0, t["ltcg_exemption"] - max(0.0, lt0 + min(st0, 0)))
        ideas, proposals = [], []
        by_sym = {}
        for lot in p["lots"]:
            price = px.get(lot["symbol"])
            if price:
                by_sym.setdefault(lot["symbol"], []).append(lot_view(lot, price, today, t))
        for sym, views in sorted(by_sym.items()):
            for v in views:
                if v["gain"] <= -a.min_loss:
                    ideas.append(("LOSS", v, "book a %s %s loss to offset gains; you may rebuy (no wash-sale rule, "
                                             "but avoid same-day round trips)" % (v["term"], T.inr(-v["gain"]))))
                elif v["term"] == "LT" and v["gain"] > 0 and exempt_left > 0:
                    use = min(v["gain"], exempt_left)
                    ideas.append(("GAIN", v, "book %s of tax-free LTCG (exemption left %s) and rebuy to reset cost"
                                             % (T.inr(use), T.inr(exempt_left))))
                    exempt_left -= use
                elif v["term"] == "ST" and v["gain"] > 0 and v["long_term_from"]:
                    days = (dt.date.fromisoformat(v["long_term_from"]) - dt.date.fromisoformat(today)).days
                    if days <= 60:
                        ideas.append(("WAIT", v, "turns long-term on %s (%d days): selling now pays %s%% instead of %s%%"
                                                 % (v["long_term_from"], days, t["stcg_rate"], t["ltcg_rate"])))
        for kind, v, why in ideas:
            print("%-4s %-10s %3d sh bought %s: %s" % (kind, v["symbol"], v["qty"], v["date"], why))
            if kind in ("LOSS", "GAIN"):
                proposals.append(v)
        if not ideas:
            print("No harvesting ideas (min loss %s). %s: ST %s, LT %s realized." % (T.inr(a.min_loss), fy, T.inr(st0),
                                                                                    T.inr(lt0)))
        print("Not tax advice. Losses only carry forward if you file your ITR by the due date.")
        if a.write and proposals:
            orders, i = [], 1
            for v in proposals:
                o = T.groww_order(v["symbol"], v["qty"], "SELL", cfg)
                orders.append({"index": i, "status": "proposed", "source": "trader-tax", "order": o,
                               "fingerprint": T.fingerprint(o), "est_price": px[v["symbol"]],
                               "est_value": v["value"], "est_charges": T.charges("SELL", v["value"])["total"],
                               "note": "harvest %s, gain %s" % (v["term"], T.inr(v["gain"]))})
                i += 1
            T.save_json(T.path("orders.json"), {"generated": T.now_ist().isoformat(timespec="seconds"),
                                                "paper": bool(cfg.get("paper", True)), "orders": orders})
            print("-> %s (%d sell proposals). Next: /trader-risk." % (T.path("orders.json"), len(orders)))
        return 0


if __name__ == "__main__":
    sys.exit(main())
