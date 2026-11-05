#!/usr/bin/env python3
"""Risk Manager: PASS or BLOCK every proposed order before it can reach a broker.

Reads  trader/orders.json, trader/config.json, trader/portfolio.json, trader/prices.json,
       trader/surveillance.json (ASM / GSM lists, `check.py surveillance --fetch`),
       trader/EQUITY_L.csv (series: EQ, BE = trade-to-trade, SM/ST = SME)
Writes trader/risk.json  the verdicts, keyed by order fingerprint, dated today (IST).

  python3 check.py                       # check every proposed order
  python3 check.py surveillance --fetch  # cache NSE's ASM and GSM lists
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trader-common"))
import inr as T  # noqa: E402
import ledger as L  # noqa: E402

REQUIRED = ("trading_symbol", "quantity", "validity", "exchange", "segment", "product",
            "order_type", "transaction_type")
ASM_URL = "https://www.nseindia.com/api/reportASM"
GSM_URL = "https://www.nseindia.com/api/reportGSM"


def load_surveillance(p=None):
    data = T.load_json(p or T.path("surveillance.json"), {}) or {}
    return {k.upper(): v for k, v in data.get("symbols", {}).items()}


def parse_surveillance(asm, gsm):
    out = {}
    for section, block in (asm or {}).items():
        if isinstance(block, dict):
            for r in block.get("data", []):
                if r.get("symbol"):
                    out[r["symbol"].upper()] = r.get("survDesc") or r.get("survCode") or ("ASM " + section)
    for r in gsm or []:
        if r.get("symbol"):
            out[r["symbol"].upper()] = "GSM: " + (r.get("survDesc") or r.get("gsmStage") or "")
    return out


def series_map(src=None):
    try:
        eq = T.equity_list(src) if (src or os.path.exists(T.path("EQUITY_L.csv"))) else {}
    except Exception:
        eq = {}
    return {k: v.get("series", "") for k, v in eq.items()}


def check(orders, cfg, portfolio, px, surv=None, series=None, placed_today=0):
    surv = surv or {}
    series = series or {}
    blocked = {b.upper() for b in cfg.get("blocked", [])}
    positions = {k.upper(): v for k, v in (portfolio.get("positions") or {}).items()}
    cash = T.num(portfolio.get("cash"), None)
    if cash is None:
        cash = float(cfg["budget"])
    value_now = cash + sum(T.num(p.get("qty"), 0) * (px.get(s) or T.num(p.get("avg_price"), 0))
                           for s, p in positions.items())
    buffer = value_now * float(cfg["cash_buffer_pct"]) / 100

    seen = collections.Counter()
    sim_cash = cash
    own_cash = cash            # cash without the proceeds of sells that have not happened yet
    sells_passed = []
    sim_qty = {s: T.num(p.get("qty"), 0) for s, p in positions.items()}
    count = placed_today
    verdicts = []
    # sells first: they free cash for the buys
    ordered = sorted(orders, key=lambda o: 0 if (o.get("order") or {}).get("transaction_type") == "SELL" else 1)
    for item in ordered:
        o = item.get("order") or {}
        reasons, warnings = [], []
        depends_on = []
        missing = [k for k in REQUIRED if o.get(k) in (None, "")]
        if missing:
            reasons.append("malformed: missing " + ", ".join(missing))
        sym = str(o.get("trading_symbol", ""))
        side = str(o.get("transaction_type", ""))
        if sym != sym.upper():
            reasons.append("trading_symbol must be upper case (as NSE lists it)")
        qty = o.get("quantity")
        if not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0:
            reasons.append("quantity must be a whole number above 0 (no fractional shares in India)")
            qty = 0
        if side not in ("BUY", "SELL"):
            reasons.append("transaction_type must be exactly BUY or SELL")
        if o.get("validity") not in (None, "DAY"):
            reasons.append("validity must be DAY")
        if o.get("exchange") not in (None, "NSE", "BSE"):
            reasons.append("exchange must be NSE or BSE")

        seg, prod, ot = o.get("segment"), o.get("product"), o.get("order_type")
        if ot not in ("MARKET", "LIMIT", "SL", "SL_M"):
            reasons.append("order_type must be exactly MARKET, LIMIT, SL or SL_M")
        if seg == "FNO" and not cfg.get("allow_fno"):
            reasons.append("F&O is off (allow_fno=false)")
        elif seg not in ("CASH", "FNO", None):
            reasons.append("unknown segment %s" % seg)
        if prod == "MIS" and not cfg.get("allow_intraday"):
            reasons.append("intraday (MIS) is off (allow_intraday=false); delivery is CNC")
        if prod == "MTF" and not cfg.get("allow_mtf"):
            reasons.append("margin trading (MTF) is off (allow_mtf=false)")
        if prod == "NRML" and not cfg.get("allow_fno"):
            reasons.append("NRML is a derivatives product; F&O is off")
        if prod not in ("CNC", "MIS", "MTF", "NRML", None):
            reasons.append("unknown product %s" % prod)
        if ot in ("LIMIT", "SL") and not T.num(o.get("price")):
            reasons.append("%s order needs a price" % ot)
        if ot in ("SL", "SL_M") and not T.num(o.get("trigger_price")):
            reasons.append("%s order needs a trigger_price" % ot)

        if sym in blocked:
            reasons.append("%s is on your blocked list" % sym)
        if sym in surv and not cfg.get("allow_surveillance"):
            reasons.append("%s is under NSE surveillance (%s)" % (sym, surv[sym]))
        ser = series.get(sym, "")
        if ser in ("BE", "BZ", "BT") and not cfg.get("allow_t2t"):
            reasons.append("%s trades in series %s (trade-to-trade: no intraday netting, delivery is compulsory)" % (sym, ser))
        if ser in ("SM", "ST", "SZ") and not cfg.get("allow_sme"):
            reasons.append("%s is an SME stock (series %s): thin trading, large lots" % (sym, ser))

        price = T.num(o.get("price")) if ot in ("LIMIT", "SL") else None
        price = price or px.get(sym) or T.num(item.get("est_price"))
        if not price:
            reasons.append("no price for %s: run trader-alerts quote" % sym)
            price = 0.0
        value = qty * price
        ch = T.charges(side or "BUY", value, o.get("exchange") or "NSE", cfg)

        fp = T.fingerprint(o)
        seen[fp] += 1
        if seen[fp] > 1:
            reasons.append("duplicate of an order above")

        if side == "BUY":
            if value > float(cfg["max_order_inr"]) + 1e-9:
                reasons.append("order %s is over max_order_inr %s" % (T.inr(value), T.inr(cfg["max_order_inr"])))
            if value < float(cfg["min_order_inr"]) - 1e-9:
                reasons.append("order %s is under min_order_inr %s" % (T.inr(value), T.inr(cfg["min_order_inr"])))
            after = (sim_qty.get(sym, 0) + qty) * price
            cap = value_now * float(cfg["max_position_pct"]) / 100
            if after > cap + 1e-6:
                reasons.append("%s would be %s after the fill, over the %s%% cap (%s)"
                               % (sym, T.inr(after), cfg["max_position_pct"], T.inr(cap)))
            if sim_cash - value - ch["total"] < buffer - 1e-6:
                reasons.append("would leave %s cash, under the %s%% buffer (%s)"
                               % (T.inr(sim_cash - value - ch["total"]), cfg["cash_buffer_pct"], T.inr(buffer)))
            elif own_cash - value - ch["total"] < buffer - 1e-6 and sells_passed:
                # only affordable once the sells above have filled: trader-broker enforces the order
                depends_on = list(sells_passed)
            rt = T.round_trip_pct(value, o.get("exchange") or "NSE", cfg)
            if value > 0 and rt > float(cfg["max_charges_pct"]):
                reasons.append("charges are %.2f%% of a round trip, over max_charges_pct %s%%"
                               % (rt, cfg["max_charges_pct"]))
        elif side == "SELL":
            held = sim_qty.get(sym, 0)
            if qty > held and not cfg.get("allow_short"):
                reasons.append("selling %d but you hold %d: short selling is off" % (qty, held))
            if value > 0 and ch["total"] / value * 100 > float(cfg["max_charges_pct"]):
                warnings.append("charges are %.2f%% of this sale" % (ch["total"] / value * 100))

        count += 1
        if count > int(cfg["max_orders_per_day"]):
            reasons.append("over max_orders_per_day (%s)" % cfg["max_orders_per_day"])

        verdict = "BLOCK" if reasons else "PASS"
        if verdict == "PASS":
            if side == "BUY":
                sim_cash -= value + ch["total"]
                own_cash -= value + ch["total"]
                sim_qty[sym] = sim_qty.get(sym, 0) + qty
            else:
                sim_cash += value - ch["total"]
                sim_qty[sym] = sim_qty.get(sym, 0) - qty
                sells_passed.append(fp)
            if depends_on:
                warnings.append("needs the sells above to fill first")
        else:
            count -= 1
        verdicts.append({"index": item.get("index"), "fingerprint": fp, "symbol": sym, "side": side,
                         "qty": qty, "est_value": round(value, 2), "est_charges": ch["total"],
                         "verdict": verdict, "reasons": reasons, "warnings": warnings,
                         "depends_on": depends_on if verdict == "PASS" else []})
    verdicts.sort(key=lambda v: (v["index"] is None, v["index"]))
    return {"date": T.now_ist().date().isoformat(), "checked": T.now_ist().isoformat(timespec="seconds"),
            "portfolio_value": round(value_now, 2), "cash_after_passes": round(sim_cash, 2),
            "verdicts": verdicts}


def placed_today():
    log = T.load_json(T.path("broker-log.json"), []) or []
    today = T.now_ist().date().isoformat()
    return sum(1 for e in log if e.get("event") == "placed" and str(e.get("at", "")).startswith(today))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", default="check", choices=["check", "surveillance"])
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--orders", default=None)
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)

    if a.cmd == "surveillance":
        if a.fetch:
            syms = parse_surveillance(T.http_json(ASM_URL), T.http_json(GSM_URL))
            T.save_json(T.path("surveillance.json"), {"fetched": T.now_ist().isoformat(timespec="seconds"),
                                                       "source": [ASM_URL, GSM_URL], "symbols": syms})
            print("cached %d symbols under ASM/GSM surveillance -> %s" % (len(syms), T.path("surveillance.json")))
        else:
            s = load_surveillance()
            print("%d symbols cached. Use --fetch to refresh." % len(s))
        return 0

    cfg = T.config(a.config)
    of = T.load_json(a.orders or T.path("orders.json"))
    if not of or not of.get("orders"):
        T.die("No proposals in trader/orders.json. Run /trader-budget, /trader-rebalance or /trader-tax first.")
    if not os.path.exists(T.path("surveillance.json")):
        print("note: no surveillance list cached; run `check.py surveillance --fetch` to block ASM/GSM stocks.")
    portfolio = L.load()
    res = check(of["orders"], cfg, portfolio, T.prices(), load_surveillance(), series_map(), placed_today())
    rows = []
    for v in res["verdicts"]:
        rows.append([v["index"], v["side"], v["symbol"], v["qty"], T.inr(v["est_value"]), v["verdict"],
                     "; ".join(v["reasons"] or v["warnings"]) or "ok"])
    print(T.table(rows, ["#", "side", "symbol", "qty", "value", "verdict", "why"]))
    st = T.market_state()
    if st["state"] != "open":
        print("Market is %s (%s). Orders placed now queue as after-market orders (AMO) at Groww." %
              (st["state"], st["reason"]))
    T.save_json(T.path("risk.json"), res)
    n = sum(1 for v in res["verdicts"] if v["verdict"] == "PASS")
    print("%d PASS, %d BLOCK -> %s. Only PASS orders can reach /trader-broker."
          % (n, len(res["verdicts"]) - n, T.path("risk.json")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
