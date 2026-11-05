#!/usr/bin/env python3
"""Rebalancer: bring holdings back to target weights, whole shares, only when it is worth it.

Reads trader/portfolio.json, trader/targets.json, trader/prices.json, trader/config.json.
Writes proposals (sells first) to trader/orders.json with --write. Nothing is placed.

A stock is traded only when its weight is outside the band (default 5 percentage
points) AND the trade clears the minimum order AND its charges stay under
max_charges_pct of the trade: on a small Indian portfolio a Rs 20 DP charge on a
Rs 500 trim costs more than the drift.

  python3 rebalance.py                  # the drift table
  python3 rebalance.py --band 3 --write
  python3 rebalance.py --add 5000       # you added Rs 5,000 of cash
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trader-common"))
import inr as T  # noqa: E402
import ledger as L  # noqa: E402


def plan(portfolio, targets, px, cfg, band=5.0, add_cash=0.0):
    exchange = cfg.get("exchange", "NSE")
    pos = {s: int(T.num(v.get("qty"), 0)) for s, v in (portfolio.get("positions") or {}).items()}
    cash = T.num(portfolio.get("cash"), 0) + add_cash
    tw = {}
    for t in targets:
        tw[t["symbol"].upper()] = tw.get(t["symbol"].upper(), 0) + float(t["weight"])
    tot_w = sum(tw.values()) or 1
    tw = {k: v / tot_w for k, v in tw.items()}
    syms = sorted(set(pos) | set(tw))
    missing = [s for s in syms if not px.get(s)]
    if missing:
        return {"error": "no price for " + ", ".join(missing)}
    value = cash + sum(pos.get(s, 0) * px[s] for s in syms)
    buffer = value * float(cfg["cash_buffer_pct"]) / 100
    investable = value - buffer
    cap = float(cfg["max_position_pct"]) / 100
    rows = []
    for s in syms:
        cur_v = pos.get(s, 0) * px[s]
        want = min(tw.get(s, 0.0), cap)
        rows.append({"symbol": s, "qty": pos.get(s, 0), "price": px[s], "value": cur_v,
                     "weight": 100 * cur_v / value if value else 0, "target": 100 * want,
                     "drift": (100 * cur_v / value if value else 0) - 100 * want,
                     "target_value": investable * want})
    trades = []
    for r in rows:
        if abs(r["drift"]) < band and r["target"] > 0:
            continue
        delta_v = r["target_value"] - r["value"]
        q = int(abs(delta_v) // r["price"])
        if delta_v < 0:
            q = min(r["qty"], q if r["target"] > 0 else r["qty"])
            side = "SELL"
        else:
            side = "BUY"
        if q <= 0:
            continue
        tv = q * r["price"]
        ch = T.charges(side, tv, exchange, cfg)["total"]
        skip = None
        if tv < float(cfg["min_order_inr"]):
            skip = "under min order"
        elif r["target"] > 0:
            # a buy pays again when it is sold; judge it on the round trip, as trader-risk does
            pct = T.round_trip_pct(tv, exchange, cfg) if side == "BUY" else 100 * ch / tv
            if pct > float(cfg["max_charges_pct"]):
                skip = "charges %.1f%% of the trade%s" % (pct, " (round trip)" if side == "BUY" else "")
        trades.append({"symbol": r["symbol"], "side": side, "qty": q, "price": r["price"], "value": round(tv, 2),
                       "charges": ch, "skip": skip})
    # buys must fit the cash after sells and the buffer
    spare = cash + sum(t["value"] - t["charges"] for t in trades if t["side"] == "SELL" and not t["skip"]) - buffer
    for t in sorted([t for t in trades if t["side"] == "BUY" and not t["skip"]], key=lambda t: -t["value"]):
        while t["qty"] > 0 and t["value"] + t["charges"] > spare:
            t["qty"] -= 1
            t["value"] = round(t["qty"] * t["price"], 2)
            t["charges"] = T.charges("BUY", t["value"], exchange, cfg)["total"] if t["qty"] else 0
        if t["qty"] == 0:
            t["skip"] = "not enough cash above the buffer"
        spare -= t["value"] + t["charges"]
    trades.sort(key=lambda t: (t["side"] != "SELL", -t["value"]))
    return {"value": round(value, 2), "cash": round(cash, 2), "buffer": round(buffer, 2), "rows": rows, "trades": trades}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--band", type=float, default=5.0, help="percentage points")
    ap.add_argument("--add", type=float, default=0.0,
                    help="new cash added, rupees (also booked to trader/portfolio.json with --write)")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    cfg = T.config()
    tg = T.load_json(T.path("targets.json"))
    if not tg:
        T.die("No trader/targets.json. Run /trader-copycat or /trader-screener first.")
    p = L.load()
    res = plan(p, tg.get("targets", []), T.prices(), cfg, a.band, a.add)
    if res.get("error"):
        T.die(res["error"] + ". Run trader-alerts quote first.")
    print("Portfolio %s (cash %s, buffer %s), band %g pts" % (T.inr(res["value"]), T.inr(res["cash"]),
                                                           T.inr(res["buffer"]), a.band))
    rows = [[r["symbol"], r["qty"], T.inr(r["value"]), "%.1f%%" % r["weight"], "%.1f%%" % r["target"],
             "%+.1f" % r["drift"], "TRADE" if abs(r["drift"]) >= a.band or r["target"] == 0 else ""] for r in res["rows"]]
    print(T.table(rows, ["symbol", "qty", "value", "weight", "target", "drift pts", ""]))
    live = [t for t in res["trades"] if not t["skip"]]
    for t in res["trades"]:
        print("  %s %-4s %d %s @ %s = %s (charges %s)%s" % ("->" if not t["skip"] else "  ", t["side"], t["qty"],
                                                           t["symbol"], T.inr(t["price"]), T.inr(t["value"]),
                                                           T.inr(t["charges"]), "  SKIPPED: " + t["skip"] if t["skip"] else ""))
    if not live:
        print("Nothing to trade: every stock is inside the band or not worth the charges.")
    if a.write and a.add:
        p["cash"] = round(T.num(p.get("cash"), 0) + a.add, 2)
        L.save(p)
        print("booked a deposit of %s; cash is now %s" % (T.inr(a.add), T.inr(p["cash"])))
    if a.write and live:
        orders = []
        for i, t in enumerate(live, 1):
            o = T.groww_order(t["symbol"], t["qty"], t["side"], cfg)
            orders.append({"index": i, "status": "proposed", "source": "trader-rebalance", "order": o,
                           "fingerprint": T.fingerprint(o), "est_price": t["price"], "est_value": t["value"],
                           "est_charges": t["charges"], "note": "rebalance"})
        T.save_json(T.path("orders.json"), {"generated": T.now_ist().isoformat(timespec="seconds"),
                                            "paper": bool(cfg.get("paper", True)), "orders": orders})
        print("-> %s (%d proposals, sells first). Next: /trader-risk." % (T.path("orders.json"), len(orders)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
