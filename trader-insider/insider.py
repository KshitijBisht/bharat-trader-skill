#!/usr/bin/env python3
"""The Insider Tracker: promoters, directors and big money, from public NSE disclosures.

India has no Congress-style trade disclosure for politicians. The closest public
signals are:
  * SEBI PIT disclosures (Prohibition of Insider Trading Regulations, 2015, Reg. 7(2)):
    promoters, directors, KMP and designated persons must report trades over
    Rs 10 lakh in a quarter within 2 trading days; the company tells the exchange
    within 2 more.
  * Bulk deals (one client trades 0.5% or more of a company's shares in a day) and
    block deals (5 lakh shares or Rs 10 crore+ in the block window), published daily.

  python3 insider.py pit --symbol ITC                  # recent insider trades in one company
  python3 insider.py pit --symbol ITC --market-only    # only open-market buys and sells
  python3 insider.py deals                             # today's bulk + block deals
  python3 insider.py deals --client "kacholia"         # one investor's bulk deals
  python3 insider.py new                               # only what is new since the last run, for
                                                       #   your holdings and watchlist
"""

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trader-common"))
import inr as T  # noqa: E402

PIT = "https://www.nseindia.com/api/corporates-pit?index=equities&symbol=%s"
PIT_RANGE = "https://www.nseindia.com/api/corporates-pit?index=equities&from_date=%s&to_date=%s"
DEALS = "https://www.nseindia.com/api/snapshot-capital-market-largedeal"
MARKET_MODES = ("market purchase", "market sale")


def parse_pit(data):
    rows = data.get("data", data) if isinstance(data, dict) else data
    out = []
    for r in rows:
        buy_q, sell_q = T.num(r.get("buyQuantity"), 0), T.num(r.get("sellquantity"), 0)
        qty = T.num(r.get("secAcq"), 0)
        tt = (r.get("tdpTransactionType") or "").strip()
        mode = (r.get("acqMode") or "").strip()
        side = "BUY" if tt.lower() in ("buy", "acquisition") or buy_q > 0 else (
            "SELL" if tt.lower() in ("sell", "disposal") or sell_q > 0 else (tt.upper() or "-"))
        if mode.lower() == "market sale":
            side = "SELL"
        elif mode.lower() == "market purchase":
            side = "BUY"
        value = T.num(r.get("secVal"), 0)
        d_from = T.parse_date(r.get("acqfromDt"))
        d_to = T.parse_date(r.get("acqtoDt"))
        d_int = T.parse_date(r.get("intimDt"))
        filed = T.parse_date(r.get("date"))
        out.append({
            "id": "pit:%s" % (r.get("pid") or r.get("did") or "%s-%s-%s" % (r.get("symbol"), r.get("acqName"), r.get("date"))),
            "symbol": r.get("symbol"), "company": r.get("company"),
            "person": (r.get("acqName") or "").strip(), "category": (r.get("personCategory") or "-").strip(),
            "side": side, "mode": mode, "security": r.get("secType"), "qty": qty,
            "value": value, "avg_price": round(value / qty, 2) if qty and value else None,
            "before_pct": T.num(r.get("befAcqSharesPer")), "after_pct": T.num(r.get("afterAcqSharesPer")),
            "trade_from": d_from.date().isoformat() if d_from else None,
            "trade_to": d_to.date().isoformat() if d_to else None,
            "intimated": d_int.date().isoformat() if d_int else None,
            "filed": filed.isoformat(timespec="minutes") if filed else None,
            "days_to_disclose": (filed.date() - d_to.date()).days if (filed and d_to) else None,
            "market": mode.lower() in MARKET_MODES,
            "xbrl": r.get("xbrl"),
        })
    return out


def parse_deals(data):
    out = []
    for kind, key in (("BULK", "BULK_DEALS_DATA"), ("BLOCK", "BLOCK_DEALS_DATA")):
        for r in data.get(key) or []:
            d = T.parse_date(r.get("date"))
            qty = T.num(r.get("qty"), 0)
            px = T.num(r.get("watp"), 0)
            out.append({"id": "%s:%s:%s:%s:%s:%s" % (kind, r.get("date"), r.get("symbol"), r.get("clientName"),
                                                     r.get("buySell"), r.get("qty")),
                        "kind": kind, "date": d.date().isoformat() if d else r.get("date"),
                        "symbol": r.get("symbol"), "company": r.get("name"), "client": (r.get("clientName") or "").strip(),
                        "side": (r.get("buySell") or "").upper(), "qty": qty, "price": px,
                        "value": round(qty * px, 2)})
    return out


def watchlist():
    syms = set()
    port = T.load_json(T.path("portfolio.json"), {}) or {}
    syms |= {s.upper() for s in (port.get("positions") or {})}
    tg = T.load_json(T.path("targets.json"), {}) or {}
    syms |= {t["symbol"].upper() for t in tg.get("targets", [])}
    cfg = T.config()
    syms |= {s.upper() for s in cfg.get("watchlist", [])}
    return sorted(syms)


def seen_store():
    return T.load_json(T.path("insider-seen.json"), {"ids": []}) or {"ids": []}


def crore(v):
    return "%s cr" % format(round(v / 1e7, 2), ",") if v >= 1e6 else T.inr(v, 0)


def print_pit(rows, held):
    out = []
    for r in rows:
        flag = "*" if r["symbol"] in held else ""
        out.append([flag + r["symbol"], r["person"][:34], r["category"][:18], r["side"], r["mode"][:16],
                    format(int(r["qty"]), ","), crore(r["value"]), r["trade_to"] or "", r["filed"][:10] if r["filed"] else "",
                    r["days_to_disclose"] if r["days_to_disclose"] is not None else ""])
    print(T.table(out, ["symbol", "person", "category", "side", "mode", "qty", "value", "traded", "filed", "days"]))


def print_deals(rows, held):
    out = [[("*" if r["symbol"] in held else "") + r["symbol"], r["kind"], r["client"][:40], r["side"],
            format(int(r["qty"]), ","), T.inr(r["price"]), crore(r["value"]), r["date"]] for r in rows]
    print(T.table(out, ["symbol", "kind", "client", "side", "qty", "avg price", "value", "date"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("pit")
    s.add_argument("--symbol")
    s.add_argument("--days", type=int, default=30, help="without --symbol: all companies, last N days")
    s.add_argument("--market-only", action="store_true", help="open-market trades only (no ESOP, gifts, pledges)")
    s.add_argument("--min-value", type=float, default=0, help="rupees")
    s.add_argument("--file", help="saved NSE JSON instead of downloading")
    s.add_argument("--limit", type=int, default=25)
    s = sub.add_parser("deals")
    s.add_argument("--client")
    s.add_argument("--symbol")
    s.add_argument("--file")
    s = sub.add_parser("new")
    s.add_argument("--pit-file", nargs="*")
    s.add_argument("--deals-file")
    s.add_argument("--all", action="store_true", help="every company, not only your watchlist")
    a = ap.parse_args(argv)
    held = set(watchlist())

    if a.cmd == "pit":
        if a.file:
            data = T.load_json(a.file)
        elif a.symbol:
            data = T.http_json(PIT % a.symbol.upper())
        else:
            end = T.now_ist().date()
            start = end - dt.timedelta(days=a.days)
            data = T.http_json(PIT_RANGE % (start.strftime("%d-%m-%Y"), end.strftime("%d-%m-%Y")))
        rows = parse_pit(data)
        if a.market_only:
            rows = [r for r in rows if r["market"]]
        rows = [r for r in rows if r["value"] >= a.min_value]
        rows.sort(key=lambda r: r["filed"] or "", reverse=True)
        print_pit(rows[:a.limit], held)
        buys = sum(r["value"] for r in rows if r["side"] == "BUY" and r["market"])
        sells = sum(r["value"] for r in rows if r["side"] == "SELL" and r["market"])
        print("Open-market insider buying %s vs selling %s in these %d filings. ESOP allotments, gifts and "
              "pledges are not conviction trades; --market-only hides them." % (crore(buys), crore(sells), len(rows)))
        return 0

    if a.cmd == "deals":
        data = T.load_json(a.file) if a.file else T.http_json(DEALS)
        rows = parse_deals(data)
        if a.client:
            rows = [r for r in rows if a.client.lower() in r["client"].lower()]
        if a.symbol:
            rows = [r for r in rows if r["symbol"] == a.symbol.upper()]
        rows.sort(key=lambda r: -r["value"])
        print("NSE bulk and block deals, %s:" % data.get("as_on_date", "latest"))
        print_deals(rows, held)
        return 0

    if a.cmd == "new":
        seen = seen_store()
        last = seen.get("checked")
        ids = set(seen["ids"])
        fresh_pit, fresh_deals = [], []
        sources = a.pit_file or [None] * len(held)
        targets = sorted(held) if not a.pit_file else [None] * len(a.pit_file)
        for sym, f in zip(targets, sources):
            try:
                data = T.load_json(f) if f else T.http_json(PIT % sym)
            except Exception as exc:
                print("  %s: PIT unavailable (%s)" % (sym, str(exc)[:60]))
                continue
            for r in parse_pit(data):
                if r["id"] not in ids and r["market"]:
                    fresh_pit.append(r)
                    ids.add(r["id"])
        try:
            deals = parse_deals(T.load_json(a.deals_file) if a.deals_file else T.http_json(DEALS))
        except Exception as exc:
            deals = []
            print("  deals unavailable (%s)" % str(exc)[:60])
        for r in deals:
            if r["id"] not in ids and (a.all or r["symbol"] in held):
                fresh_deals.append(r)
                ids.add(r["id"])
        seen["ids"] = sorted(ids)[-20000:]
        seen["checked"] = T.now_ist().isoformat(timespec="seconds")
        T.save_json(T.path("insider-seen.json"), seen)
        if not held and not a.all and not a.pit_file:
            print("No holdings or watchlist yet; add \"watchlist\": [\"ITC\", ...] to trader/config.json.")
        if fresh_pit:
            print("NEW insider trades (open market):")
            print_pit(fresh_pit, held)
        if fresh_deals:
            print("NEW bulk / block deals:")
            print_deals(fresh_deals, held)
        if not fresh_pit and not fresh_deals:
            print("Nothing new since %s." % (last or "the last check"))
        print("(* = in your holdings, targets or watchlist.) A disclosure is a public fact, not a tip.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
