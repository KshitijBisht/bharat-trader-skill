#!/usr/bin/env python3
"""Price Alerts: NSE clock, quotes into trader/prices.json, and rules that ring once.

  python3 alerts.py clock                          # NSE open / pre-open / closed, next open, IST
  python3 alerts.py holidays [--fetch]             # the NSE trading-holiday list
  python3 alerts.py quote ITC TITAN                # Yahoo .NS (delayed) -> NSE bhavcopy fallback
  python3 alerts.py quote --bhav                   # every holding from the last NSE bhavcopy (EOD)
  python3 alerts.py add ITC below 400              # rules: above / below / stop / move-pct / bell
  python3 alerts.py add ITC move-pct 3             # +/- 3% from the previous close
  python3 alerts.py add BELL bell                  # the 09:15 opening bell, once a day
  python3 alerts.py list | remove --id 2
  python3 alerts.py check                          # fetch quotes, ring what hit, once each
"""

import argparse
import csv
import datetime as dt
import io
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trader-common"))
import inr as T  # noqa: E402

YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/%s?range=5d&interval=1d"
BHAV_FULL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_%s.csv"
HOLIDAYS = "https://www.nseindia.com/api/holiday-master?type=trading"
KINDS = ("above", "below", "stop", "move-pct", "bell")


# ---------------------------------------------------------------- prices

def yahoo_symbol(sym, exchange="NSE"):
    if sym.startswith("^") or "." in sym:
        return sym
    return sym + (".BO" if exchange == "BSE" else ".NS")


def parse_yahoo(data, sym):
    res = (data.get("chart") or {}).get("result") or []
    if not res:
        err = (data.get("chart") or {}).get("error") or {}
        raise ValueError("Yahoo has no data for %s: %s" % (sym, err.get("description", "unknown")))
    meta = res[0].get("meta", {})
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    closes = [c for c in (((res[0].get("indicators") or {}).get("quote") or [{}])[0].get("close") or []) if c]
    if len(closes) >= 2:
        prev = closes[-2]
    if price is None:
        raise ValueError("Yahoo returned no price for %s" % sym)
    t = meta.get("regularMarketTime")
    when = dt.datetime.fromtimestamp(t, T.IST).isoformat(timespec="minutes") if t else None
    return {"price": round(float(price), 2), "prev_close": round(float(prev), 2) if prev else None,
            "currency": meta.get("currency", "INR"), "time": when, "source": "yahoo (delayed)"}


def parse_bhav(text):
    """NSE sec_bhavdata_full CSV -> {symbol: quote} for EQ/BE/BZ/SM series."""
    rows = csv.reader(io.StringIO(text))
    header = [h.strip() for h in next(rows)]
    out = {}
    for r in rows:
        rec = dict(zip(header, [c.strip() for c in r]))
        if rec.get("SERIES") not in ("EQ", "BE", "BZ", "SM", "ST"):
            continue
        sym = rec["SYMBOL"]
        if sym in out and out[sym]["series"] == "EQ":
            continue
        d = T.parse_date(rec.get("DATE1"))
        out[sym] = {"price": T.num(rec.get("CLOSE_PRICE")), "prev_close": T.num(rec.get("PREV_CLOSE")),
                    "high": T.num(rec.get("HIGH_PRICE")), "low": T.num(rec.get("LOW_PRICE")),
                    "volume": int(T.num(rec.get("TTL_TRD_QNTY"), 0)), "delivery_pct": T.num(rec.get("DELIV_PER")),
                    "series": rec.get("SERIES"), "time": d.date().isoformat() + "T15:30" if d else None,
                    "source": "nse bhavcopy (end of day)"}
    return out


def fetch_bhav(day=None):
    """The latest NSE bhavcopy on or before `day`, trying back over holidays."""
    d = day or T.now_ist().date()
    if T.now_ist().time() < dt.time(18, 30) and d == T.now_ist().date():
        d -= dt.timedelta(days=1)            # today's file posts in the evening
    for _ in range(8):
        if T.is_trading_day(d):
            try:
                return d, parse_bhav(T.http_text(BHAV_FULL % d.strftime("%d%m%Y")))
            except Exception:
                pass
        d -= dt.timedelta(days=1)
    raise RuntimeError("could not fetch an NSE bhavcopy for the last week")


def quote(symbols, exchange="NSE", bhav_only=False):
    out, errors = {}, {}
    need = list(symbols)
    if not bhav_only:
        for s in list(need):
            try:
                out[s] = parse_yahoo(T.http_json(YAHOO % yahoo_symbol(s, exchange), retries=1, timeout=10), s)
                need.remove(s)
            except Exception as exc:
                errors[s] = str(exc)[:120]
                if "429" in str(exc):
                    break                    # rate limited: stop asking, use the bhavcopy
    if need:
        try:
            day, bhav = fetch_bhav()
            for s in list(need):
                if s in bhav:
                    out[s] = bhav[s]
                    need.remove(s)
                    errors.pop(s, None)
        except Exception as exc:
            for s in need:
                errors.setdefault(s, str(exc)[:120])
    for s in need:
        errors.setdefault(s, "not found")
    return out, errors


def save_prices(quotes):
    p = T.load_json(T.path("prices.json"), {}) or {}
    q = p.get("quotes", {})
    q.update(quotes)
    T.save_json(T.path("prices.json"), {"updated": T.now_ist().isoformat(timespec="seconds"), "quotes": q})


def holdings_symbols():
    syms = set()
    port = T.load_json(T.path("portfolio.json"), {}) or {}
    syms |= set((port.get("positions") or {}).keys())
    tg = T.load_json(T.path("targets.json"), {}) or {}
    syms |= {t["symbol"].upper() for t in tg.get("targets", [])}
    of = T.load_json(T.path("orders.json"), {}) or {}
    syms |= {o["order"]["trading_symbol"] for o in of.get("orders", [])}
    return sorted(syms)


# ---------------------------------------------------------------- rules

def evaluate(rules, quotes, now, state):
    """Return the alerts that ring now. state remembers what already rang."""
    rang = []
    today = now.date().isoformat()
    for r in rules:
        rid = str(r["id"])
        kind = r["kind"]
        if kind == "bell":
            ms = T.market_state(now)
            key = "bell:" + today
            if ms["state"] == "open" and state.get(rid) != key:
                state[rid] = key
                rang.append((r, "NSE is open (09:15 IST). Closes 15:30."))
            continue
        q = quotes.get(r["symbol"])
        if not q or q.get("price") is None:
            continue
        px = q["price"]
        hit, msg = False, ""
        if kind == "above" and px >= r["level"]:
            hit, msg = True, "%s at %s, at or above %s" % (r["symbol"], T.inr(px), T.inr(r["level"]))
        elif kind in ("below", "stop") and px <= r["level"]:
            hit, msg = True, "%s at %s, at or below %s%s" % (r["symbol"], T.inr(px), T.inr(r["level"]),
                                                            " (STOP: consider a sell, via /trader-risk)" if kind == "stop" else "")
        elif kind == "move-pct" and q.get("prev_close"):
            ch = 100 * (px - q["prev_close"]) / q["prev_close"]
            if abs(ch) >= r["level"]:
                hit, msg = True, "%s moved %+.2f%% from the previous close %s to %s" % (
                    r["symbol"], ch, T.inr(q["prev_close"]), T.inr(px))
        # level alerts ring once until re-armed; move-pct rings once per day
        key = today if kind == "move-pct" else "rang"
        if hit and state.get(rid) != key:
            state[rid] = key
            rang.append((r, msg))
        elif not hit and kind != "move-pct" and state.get(rid) == "rang":
            state.pop(rid)                   # back on the other side: re-armed
    return rang


def load_rules():
    return T.load_json(T.path("alerts.json"), {"rules": [], "state": {}}) or {"rules": [], "state": {}}


# ---------------------------------------------------------------- commands

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("clock")
    s = sub.add_parser("holidays")
    s.add_argument("--fetch", action="store_true")
    s = sub.add_parser("quote")
    s.add_argument("symbols", nargs="*")
    s.add_argument("--bhav", action="store_true", help="end-of-day NSE bhavcopy only")
    s.add_argument("--bse", action="store_true", help="Yahoo .BO instead of .NS")
    s = sub.add_parser("add")
    s.add_argument("symbol")
    s.add_argument("kind", choices=KINDS)
    s.add_argument("level", nargs="?", type=float)
    s.add_argument("--note", default="")
    sub.add_parser("list")
    s = sub.add_parser("remove")
    s.add_argument("--id", type=int, required=True)
    s = sub.add_parser("check")
    s.add_argument("--bhav", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "clock":
        now = T.now_ist()
        ms = T.market_state(now)
        print("%s IST  NSE capital market: %s (%s)" % (now.strftime("%a %d %b %Y %H:%M"), ms["state"].upper(),
                                                       ms["reason"]))
        if "next_open" in ms:
            print("next open: %s" % ms["next_open"])
        if "closes" in ms:
            print("closes: %s" % ms["closes"])
        print("sessions: pre-open 09:00-09:15, normal 09:15-15:30, closing 15:40-16:00. "
              "Groww takes after-market orders (AMO) outside hours.")
        return 0
    if a.cmd == "holidays":
        if a.fetch:
            data = T.http_json(HOLIDAYS)
            cm = {}
            for r in data.get("CM", []):
                d = T.parse_date(r["tradingDate"])
                if d:
                    cm[d.date().isoformat()] = r["description"]
            T.save_json(T.path("holidays.json"), {"fetched": T.now_ist().isoformat(timespec="seconds"), "CM": cm})
            print("cached %d NSE trading holidays -> %s" % (len(cm), T.path("holidays.json")))
        h = T.holidays()
        year = str(T.now_ist().year)
        for d in sorted(h):
            if d.startswith(year) or d > T.now_ist().date().isoformat():
                wd = dt.date.fromisoformat(d).strftime("%a")
                print("%s %s  %s" % (d, wd, h[d]))
        return 0
    if a.cmd == "quote":
        syms = [s.upper() for s in a.symbols] or holdings_symbols()
        if not syms:
            T.die("Which symbols? e.g. quote ITC TITAN")
        quotes, errors = quote(syms, "BSE" if a.bse else "NSE", a.bhav)
        rows = []
        for s in syms:
            q = quotes.get(s)
            if q:
                ch = (100 * (q["price"] - q["prev_close"]) / q["prev_close"]) if q.get("prev_close") else None
                rows.append([s, T.inr(q["price"]), "%+.2f%%" % ch if ch is not None else "-", q.get("time") or "",
                             q["source"]])
            else:
                rows.append([s, "-", "-", "", "error: " + errors.get(s, "")])
        print(T.table(rows, ["symbol", "price", "change", "as of", "source"]))
        if quotes:
            save_prices(quotes)
            print("-> %s. Free quotes are delayed; your broker's price is the one that fills." % T.path("prices.json"))
        return 0 if quotes else 1
    data = load_rules()
    if a.cmd == "add":
        if a.kind != "bell" and a.level is None:
            T.die("%s needs a level, e.g. add ITC below 400" % a.kind)
        rid = max([r["id"] for r in data["rules"]] + [0]) + 1
        data["rules"].append({"id": rid, "symbol": a.symbol.upper(), "kind": a.kind, "level": a.level,
                              "note": a.note, "created": T.now_ist().isoformat(timespec="seconds")})
        T.save_json(T.path("alerts.json"), data)
        print("added #%d %s %s %s" % (rid, a.symbol.upper(), a.kind, "" if a.level is None else a.level))
        return 0
    if a.cmd == "list":
        rows = [[r["id"], r["symbol"], r["kind"], r.get("level") if r.get("level") is not None else "",
                 data["state"].get(str(r["id"]), "armed"), r.get("note", "")] for r in data["rules"]]
        print(T.table(rows, ["id", "symbol", "kind", "level", "state", "note"]) if rows else "no alerts")
        return 0
    if a.cmd == "remove":
        data["rules"] = [r for r in data["rules"] if r["id"] != a.id]
        data["state"].pop(str(a.id), None)
        T.save_json(T.path("alerts.json"), data)
        print("removed #%d" % a.id)
        return 0
    if a.cmd == "check":
        syms = sorted({r["symbol"] for r in data["rules"] if r["kind"] != "bell"})
        quotes, errors = quote(syms, bhav_only=a.bhav) if syms else ({}, {})
        if quotes:
            save_prices(quotes)
        rang = evaluate(data["rules"], quotes, T.now_ist(), data["state"])
        T.save_json(T.path("alerts.json"), data)
        for r, msg in rang:
            print("ALERT #%d: %s%s" % (r["id"], msg, (" - " + r["note"]) if r.get("note") else ""))
        for s, e in errors.items():
            print("  no quote for %s: %s" % (s, e))
        if not rang:
            print("nothing rang (%d rules, market %s)" % (len(data["rules"]), T.market_state()["state"]))
        return 0


if __name__ == "__main__":
    sys.exit(main())
