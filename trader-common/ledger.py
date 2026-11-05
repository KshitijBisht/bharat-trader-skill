"""The local portfolio ledger: trader/portfolio.json.

  {"cash": 10000.0,
   "positions": {"ITC": {"qty": 6, "avg_price": 411.39}},
   "lots": [{"symbol": "ITC", "qty": 6, "price": 410.0, "cost": 2468.35, "date": "2026-11-05"}],
   "realized": [{"symbol": ..., "qty": ..., "buy_date": ..., "sell_date": ..., "cost": ..., "proceeds": ..., "gain": ...}]}

Lot cost includes buy charges; sale proceeds are net of sell charges, so gains are
what actually landed in your account. Sells consume lots FIFO, the way Indian
depositories (and the Income Tax Department, CBDT circular 768) treat demat shares.
"""

import inr as T


def load():
    p = T.load_json(T.path("portfolio.json"), None)
    if p is None:
        cfg = T.config()
        p = {"cash": float(cfg["budget"]), "positions": {}, "lots": [], "realized": []}
    p.setdefault("positions", {})
    p.setdefault("lots", [])
    p.setdefault("realized", [])
    if p["lots"]:
        _rebuild_positions(p)
    return p


def save(p):
    T.save_json(T.path("portfolio.json"), p)


def _rebuild_positions(p):
    pos = {}
    for lot in p["lots"]:
        s = lot["symbol"]
        q = pos.setdefault(s, {"qty": 0, "cost": 0.0})
        q["qty"] += lot["qty"]
        q["cost"] += lot["cost"]
    p["positions"] = {s: {"qty": v["qty"], "avg_price": round(v["cost"] / v["qty"], 4)}
                      for s, v in sorted(pos.items()) if v["qty"] > 0}


def apply_fill(p, symbol, side, qty, price, date, exchange="NSE", cfg=None, charges=None):
    """Book a fill. Returns the charges used."""
    symbol = symbol.upper()
    side = side.upper()
    qty = int(qty)
    value = qty * float(price)
    ch = charges if charges is not None else T.charges(side, value, exchange, cfg)["total"]
    if side == "BUY":
        p["cash"] = round(T.num(p.get("cash"), 0) - value - ch, 2)
        p["lots"].append({"symbol": symbol, "qty": qty, "price": float(price),
                          "cost": round(value + ch, 2), "date": date})
    elif side == "SELL":
        have = sum(l["qty"] for l in p["lots"] if l["symbol"] == symbol)
        if qty > have:
            raise ValueError("selling %d %s but the ledger holds %d" % (qty, symbol, have))
        proceeds_total = value - ch
        left = qty
        keep = []
        for lot in p["lots"]:
            if lot["symbol"] != symbol or left == 0:
                keep.append(lot)
                continue
            take = min(left, lot["qty"])
            unit_cost = lot["cost"] / lot["qty"]
            cost = round(unit_cost * take, 2)
            proceeds = round(proceeds_total * take / qty, 2)
            p["realized"].append({"symbol": symbol, "qty": take, "buy_date": lot["date"], "sell_date": date,
                                  "buy_price": lot["price"], "sell_price": float(price), "cost": cost,
                                  "proceeds": proceeds, "gain": round(proceeds - cost, 2)})
            if take < lot["qty"]:
                keep.append(dict(lot, qty=lot["qty"] - take, cost=round(lot["cost"] - cost, 2)))
            left -= take
        p["lots"] = keep
        p["cash"] = round(T.num(p.get("cash"), 0) + proceeds_total, 2)
    else:
        raise ValueError("side must be BUY or SELL")
    _rebuild_positions(p)
    return ch
