#!/usr/bin/env python3
"""Budget Manager: size target weights into whole-share NSE/BSE delivery orders.

Reads  trader/targets.json  {"targets": [{"symbol": "TITAN", "weight": 30.5}, ...]}
       trader/prices.json   (trader-alerts writes it) or --price SYMBOL=PRICE
       trader/config.json   budget, cash_buffer_pct, max_position_pct, min_order_inr ...
Writes trader/orders.json   proposals in the exact shape of Groww's place_order.
Nothing is placed.

  python3 size.py --budget 10000                 # show the plan
  python3 size.py --budget 10000 --write         # and write trader/orders.json
  python3 size.py --charges 1000                 # what a Rs 1,000 round trip costs
"""

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trader-common"))
import inr as T  # noqa: E402


def cap_weights(weights, cap):
    """Cap each weight at `cap` (fractions summing to 1) and share the excess out pro rata."""
    w = dict(weights)
    if cap <= 0 or cap * len(w) < 1 - 1e-9:
        # cap too tight to invest everything: everyone is capped, the rest stays cash
        return {k: min(v, cap) for k, v in w.items()} if cap > 0 else w
    for _ in range(50):
        over = {k: v for k, v in w.items() if v > cap + 1e-12}
        if not over:
            break
        excess = sum(v - cap for v in over.values())
        free = {k: v for k, v in w.items() if v < cap - 1e-12}
        for k in over:
            w[k] = cap
        tot = sum(free.values())
        if tot <= 0:
            break
        for k, v in free.items():
            w[k] = v + excess * v / tot
    return w


def shares_for(alloc, price, lot, exchange, cfg):
    """Most whole shares (multiples of lot) whose value plus buy charges fits in alloc."""
    if price <= 0:
        return 0
    q = int(alloc // price)
    q -= q % lot
    while q > 0 and q * price + T.charges("BUY", q * price, exchange, cfg)["total"] > alloc + 1e-9:
        q -= lot
    return max(q, 0)


def plan(targets, px, cfg, budget=None, lots=None):
    budget = float(budget if budget is not None else cfg["budget"])
    exchange = cfg.get("exchange", "NSE")
    buffer = budget * float(cfg["cash_buffer_pct"]) / 100
    investable = budget - buffer
    lots = lots or {}

    raw = {}
    missing = []
    for t in targets:
        sym = t["symbol"].upper()
        if sym in [b.upper() for b in cfg.get("blocked", [])]:
            continue
        if not px.get(sym):
            missing.append(sym)
            continue
        raw[sym] = raw.get(sym, 0) + float(t["weight"])
    tot = sum(raw.values())
    if tot <= 0:
        return {"error": "no targets with a price", "missing": missing}
    weights = cap_weights({k: v / tot for k, v in raw.items()}, float(cfg["max_position_pct"]) / 100)

    rows = []
    for sym, w in sorted(weights.items(), key=lambda kv: -kv[1]):
        alloc = investable * w
        lot = int(lots.get(sym, 1) or 1)
        q = shares_for(alloc, px[sym], lot, exchange, cfg)
        rows.append({"symbol": sym, "weight": w, "alloc": alloc, "price": px[sym], "lot": lot, "qty": q})

    # whole shares leave rupees over: keep adding one lot to the stock that ends up least
    # overweight relative to its target, as long as it fits the cash and the per-stock cap
    cap_value = budget * float(cfg["max_position_pct"]) / 100
    for _ in range(10000):
        spent = sum(_cost(r, exchange, cfg) for r in rows)
        spare = investable - spent
        best = None
        for r in rows:
            nq = r["qty"] + r["lot"]
            add = _cost(dict(r, qty=nq), exchange, cfg) - _cost(r, exchange, cfg)
            if add > spare + 1e-9 or nq * r["price"] > cap_value + 1e-9:
                continue
            ratio = nq * r["price"] / r["alloc"] if r["alloc"] > 0 else float("inf")
            if best is None or ratio < best[0]:
                best = (ratio, r)
        if best is None:
            break
        best[1]["qty"] += best[1]["lot"]

    min_order = float(cfg["min_order_inr"])
    orders, dropped = [], []
    for r in rows:
        value = r["qty"] * r["price"]
        if r["qty"] <= 0:
            dropped.append((r["symbol"], "one share costs %s, more than its %s slice"
                            % (T.inr(r["price"]), T.inr(r["alloc"]))))
            continue
        if value < min_order:
            dropped.append((r["symbol"], "%s is under the minimum order %s" % (T.inr(value), T.inr(min_order))))
            continue
        ch = T.charges("BUY", value, exchange, cfg)
        orders.append({
            "symbol": r["symbol"], "target_pct": round(100 * r["weight"], 2), "qty": r["qty"],
            "est_price": r["price"], "est_value": round(value, 2), "est_charges": ch["total"],
            "round_trip_charges_pct": T.round_trip_pct(value, exchange, cfg),
        })
    spent = sum(o["est_value"] + o["est_charges"] for o in orders)
    return {"budget": budget, "buffer": round(buffer, 2), "investable": round(investable, 2),
            "orders": orders, "dropped": dropped, "missing": missing,
            "spent": round(spent, 2), "cash_left": round(budget - spent, 2),
            "idle": round(investable - spent, 2)}


def _cost(r, exchange, cfg):
    v = r["qty"] * r["price"]
    return v + (T.charges("BUY", v, exchange, cfg)["total"] if v > 0 else 0)


def to_orders_file(p, cfg):
    out = []
    for i, o in enumerate(p["orders"], 1):
        order = T.groww_order(o["symbol"], o["qty"], "BUY", cfg)
        out.append({"index": i, "status": "proposed", "source": "trader-budget", "order": order,
                    "fingerprint": T.fingerprint(order), "est_price": o["est_price"],
                    "est_value": o["est_value"], "est_charges": o["est_charges"],
                    "note": "target %.2f%%" % o["target_pct"]})
    return {"generated": T.now_ist().isoformat(timespec="seconds"), "paper": bool(cfg.get("paper", True)),
            "budget": p["budget"], "cash_left": p["cash_left"], "orders": out}


def print_plan(p, cfg):
    if p.get("error"):
        T.die("%s. Missing prices for: %s. Run trader-alerts quote first or pass --price SYM=PRICE."
              % (p["error"], ", ".join(p.get("missing", [])) or "-"))
    print("Budget %s | buffer %s (%s%%) | cap %s%% per stock | whole shares | %s %s"
          % (T.inr(p["budget"]), T.inr(p["buffer"]), cfg["cash_buffer_pct"], cfg["max_position_pct"],
             cfg.get("exchange", "NSE"), cfg.get("product", "CNC")))
    rows = [[i, o["symbol"], "%.2f%%" % o["target_pct"], o["qty"], T.inr(o["est_price"]),
             T.inr(o["est_value"]), T.inr(o["est_charges"]), "%.2f%%" % o["round_trip_charges_pct"]]
            for i, o in enumerate(p["orders"], 1)]
    print(T.table(rows, ["#", "symbol", "target", "qty", "price", "value", "buy charges", "round trip"]))
    print("Spent %s incl. charges | cash left %s (buffer %s + idle %s)"
          % (T.inr(p["spent"]), T.inr(p["cash_left"]), T.inr(p["buffer"]), T.inr(p["idle"])))
    for sym, why in p["dropped"]:
        print("  dropped %s: %s" % (sym, why))
    if p["missing"]:
        print("  no price for: %s" % ", ".join(p["missing"]))
    if not p["orders"]:
        cap_value = p["budget"] * float(cfg["max_position_pct"]) / 100
        print("Nothing fits: with whole shares and a %s%% cap, no stock above %s can be bought. "
              "Try fewer stocks, a higher --cap, or a low-priced index ETF such as NIFTYBEES."
              % (cfg["max_position_pct"], T.inr(cap_value)))
    worst = [o for o in p["orders"] if o["round_trip_charges_pct"] > float(cfg["max_charges_pct"])]
    if worst:
        print("WARNING: charges eat more than %s%% of a round trip on %s. Small orders on Indian "
              "delivery pay a Rs 5 minimum brokerage per side and about Rs 23.6 DP charge per sale."
              % (cfg["max_charges_pct"], ", ".join(o["symbol"] for o in worst)))
    print("Nothing is placed. Next: /trader-risk.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--budget", type=float)
    ap.add_argument("--buffer", type=float, help="cash buffer percent")
    ap.add_argument("--cap", type=float, help="max percent in one stock")
    ap.add_argument("--min-order", type=float)
    ap.add_argument("--targets", default=None)
    ap.add_argument("--prices", default=None)
    ap.add_argument("--price", action="append", default=[], help="SYMBOL=PRICE, repeatable")
    ap.add_argument("--config", default=None)
    ap.add_argument("--write", action="store_true", help="write trader/orders.json")
    ap.add_argument("--charges", type=float, metavar="VALUE", help="print charges for an order value")
    a = ap.parse_args(argv)

    cfg = T.config(a.config)
    if a.charges is not None:
        ex = cfg.get("exchange", "NSE")
        b, s = T.charges("BUY", a.charges, ex, cfg), T.charges("SELL", a.charges, ex, cfg)
        rows = [[k, T.inr(b[k]), T.inr(s[k])] for k in b]
        print("Delivery (CNC) charges on %s, %s, schedule verified %s:" % (T.inr(a.charges), ex,
                                                                          T.charge_schedule(cfg)["last_verified"]))
        print(T.table(rows, ["charge", "buy", "sell"]))
        print("Round trip at the same price: %s = %.2f%% of the order. The stock has to rise this much "
              "just to break even." % (T.inr(b["total"] + s["total"]), T.round_trip_pct(a.charges, ex, cfg)))
        return 0
    if a.budget is not None:
        cfg["budget"] = a.budget
    if a.buffer is not None:
        cfg["cash_buffer_pct"] = a.buffer
    if a.cap is not None:
        cfg["max_position_pct"] = a.cap
    if a.min_order is not None:
        cfg["min_order_inr"] = a.min_order

    tf = T.load_json(a.targets or T.path("targets.json"))
    if not tf:
        T.die("No targets. Run /trader-copycat or /trader-screener first, or write trader/targets.json.")
    targets = tf.get("targets", tf) if isinstance(tf, dict) else tf
    px = T.prices(a.prices)
    for kv in a.price:
        k, _, v = kv.partition("=")
        px[k.strip().upper()] = float(v)
    lots = {t["symbol"].upper(): t.get("lot", 1) for t in targets}

    p = plan(targets, px, cfg, lots=lots)
    print_plan(p, cfg)
    if a.write:
        T.save_json(T.path("orders.json"), to_orders_file(p, cfg))
        print("wrote %s (%d proposals)" % (T.path("orders.json"), len(p["orders"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
