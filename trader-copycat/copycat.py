#!/usr/bin/env python3
"""The Reverse Engineer: rebuild an Indian investor's or fund's portfolio from public filings.

Two sources, both public and free:

  * Mutual funds publish their FULL portfolio every month (SEBI rule). Parse the
    AMC's .xlsx disclosure, keep the listed Indian equity, diff against last month.
  * Individual "superstar" investors show up in each company's quarterly
    shareholding pattern (SHP) on NSE/BSE, but only where they hold 1% or more.
    Give a list of symbols to check; the tool reads each company's latest SHP XBRL
    and its previous quarter, finds the investor under every alias, and sums them.

  python3 copycat.py list                                   # investors and funds in the registry
  python3 copycat.py fund PPFCF --month 2026-09             # download PPFAS Flexi Cap's disclosure
  python3 copycat.py fund ./Sept.xlsx --prev ./Aug.xlsx     # any AMC's .xlsx, offline
  python3 copycat.py investor rekha --symbols TITAN METROBRAND CRISIL
  python3 copycat.py investor rekha                         # the registry's symbols to check
  python3 copycat.py shp TITAN                              # every >1% holder in TITAN's latest SHP
  ... --top 10 --write                                      # -> trader/targets.json
"""

import argparse
import calendar
import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "trader-common"))
import inr as T  # noqa: E402
import xbrl  # noqa: E402
import xlsx  # noqa: E402

SHP_MASTER = "https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol=%s"
PPFAS = ("https://amc.ppfas.com/downloads/portfolio-disclosure/%(y)d/"
         "%(code)s_PPFAS_Monthly_Portfolio_Report_%(month)s_%(day)d_%(y)d.xlsx")


def registry():
    with open(os.path.join(HERE, "investors.json"), encoding="utf-8") as fh:
        return json.load(fh)


def find_investor(key):
    reg = registry()["investors"]
    k = key.lower()
    for inv in reg:
        if k == inv["id"] or k in inv["name"].lower():
            return inv
    T.die("No investor %r in investors.json. Known: %s" % (key, ", ".join(i["id"] for i in reg)))


# ---------------------------------------------------------------- mutual funds

def parse_fund(data):
    """AMC monthly portfolio .xlsx -> {"fund", "as_of", "holdings": [...]} (listed Indian equity)."""
    rows = xlsx.rows(data)
    fund = as_of = None
    header = None
    for i, r in enumerate(rows[:15]):
        text = " ".join(r)
        if fund is None and re.search(r"fund", text, re.I):
            fund = next(c for c in r if c)
            fund = re.sub(r"\s*\(.*$", "", fund).strip()
        m = re.search(r"as on\s+(.+?)\s*$", text, re.I)
        if m and as_of is None:
            d = _date_words(m.group(1))
            as_of = d.isoformat() if d else m.group(1)
        low = [c.lower() for c in r]
        if any("isin" == c.strip() for c in low) and header is None:
            header = i
            cols = {"name": _find(low, "name of the instrument", "name of instrument", "instrument"),
                    "isin": _find(low, "isin"),
                    "industry": _find(low, "industry"),
                    "qty": _find(low, "quantity"),
                    "value": _find(low, "market", "value"),
                    "pct": _find(low, "% to net", "% to nav", "% of net", "% to aum", "net assets")}
    if header is None:
        raise ValueError("no header row with an ISIN column; is this a portfolio disclosure?")
    holdings = []
    section_ok = False
    for r in rows[header + 1:]:
        name = r[cols["name"]] if cols["name"] < len(r) else ""
        isin = r[cols["isin"]] if cols["isin"] < len(r) else ""
        low = name.lower()
        if not isin:
            if re.search(r"equity", low) and not re.search(r"foreign|overseas|international", low):
                section_ok = True
            elif re.search(r"foreign|overseas|international|money market|debt|reit|invit|arbitrage|"
                           r"derivative|treps|mutual fund units|grand total", low):
                section_ok = False
            continue
        if not section_ok or not re.match(r"^INE[A-Z0-9]{9}$", isin):
            continue
        pct = T.num(_get(r, cols["pct"]), 0) or 0
        pct = pct * 100 if pct <= 1.0 else pct           # some AMCs write 0.0775, some 7.75
        holdings.append({"name": name, "isin": isin, "industry": _get(r, cols["industry"]),
                         "qty": T.num(_get(r, cols["qty"]), 0), "value_lakh": T.num(_get(r, cols["value"]), 0),
                         "pct_nav": round(pct, 4)})
    agg = {}
    for h in holdings:
        a = agg.setdefault(h["isin"], dict(h, qty=0, value_lakh=0, pct_nav=0))
        a["qty"] += h["qty"]
        a["value_lakh"] += h["value_lakh"]
        a["pct_nav"] = round(a["pct_nav"] + h["pct_nav"], 4)
    hs = sorted(agg.values(), key=lambda h: -h["pct_nav"])
    return {"fund": fund, "as_of": as_of, "holdings": hs}


def _date_words(s):
    s = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", s.strip().rstrip("."))
    s = s.replace(",", " ")
    s = re.sub(r"\s+", " ", s)
    for fmt in ("%B %d %Y", "%d %B %Y", "%b %d %Y", "%d %b %Y", "%d-%b-%Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(s.title() if "%" in fmt else s, fmt).date()
        except ValueError:
            continue
    return None


def _find(low, *keys):
    for k in keys:
        for i, c in enumerate(low):
            if k in c:
                return i
    return 10 ** 6


def _get(r, i):
    return r[i] if i < len(r) else ""


def ppfas_url(code, month):
    y, m = int(month[:4]), int(month[5:7])
    day = calendar.monthrange(y, m)[1]
    return PPFAS % {"y": y, "code": code, "month": calendar.month_name[m], "day": day}


def prev_month(month):
    y, m = int(month[:4]), int(month[5:7])
    return "%04d-%02d" % ((y, m - 1) if m > 1 else (y - 1, 12))


def diff(now, before, key="isin", weight="pct_nav"):
    a = {h[key]: h for h in now}
    b = {h[key]: h for h in (before or [])}
    out = []
    for k, h in a.items():
        if k not in b:
            out.append(("NEW", h, None))
        else:
            q0, q1 = b[k].get("qty") or 0, h.get("qty") or 0
            if q1 > q0 * 1.005:
                out.append(("ADDED", h, b[k]))
            elif q1 < q0 * 0.995:
                out.append(("TRIMMED", h, b[k]))
    for k, h in b.items():
        if k not in a:
            out.append(("SOLD", None, h))
    order = {"NEW": 0, "ADDED": 1, "TRIMMED": 2, "SOLD": 3}
    return sorted(out, key=lambda x: (order[x[0]], -((x[1] or x[2]).get(weight) or 0)))


# ---------------------------------------------------------------- shareholding patterns

def parse_shp(data):
    """SHP XBRL -> {"symbol", "company", "as_of", "total_shares", "holders": [{name, category, shares, pct}]}"""
    f = xbrl.facts(data)
    total = T.num((f.get("ShareholdingPattern_ContextI") or {}).get("NumberOfShares"))
    holders = []
    for ctx, vals in f.items():
        name = vals.get("NameOfTheShareholder")
        if not name:
            continue
        num = f.get(xbrl.instant_twin(ctx), {})
        shares = T.num(num.get("NumberOfShares") or num.get("NumberOfFullyPaidUpEquityShares"), 0)
        pct = T.num(num.get("ShareholdingAsAPercentageOfTotalNumberOfShares"), None)
        if pct is None and total:
            pct = shares / total
        cat = re.sub(r"_Context\w*$", "", xbrl.instant_twin(ctx))
        holders.append({"name": name.strip(), "category": _category(cat), "shares": shares,
                        "pct": round(100 * (pct or 0), 4)})
    return {"symbol": xbrl.first(f, "Symbol"), "company": xbrl.first(f, "NameOfTheCompany"),
            "isin": xbrl.first(f, "ISIN"), "as_of": xbrl.first(f, "DateOfReport"),
            "total_shares": total, "holders": sorted(holders, key=lambda h: -h["shares"])}


def _category(c):
    c = c.replace("DetailsOfSharesHeldBy", "")
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", c)


def matches(name, aliases):
    n = xbrl.norm_name(name)
    for a in aliases:
        a = xbrl.norm_name(a)
        if a and (n == a or re.search(r"\b%s\b" % re.escape(a), n)):
            return True
    return False


def investor_stake(shp, aliases):
    hits = [h for h in shp["holders"] if matches(h["name"], aliases)]
    return {"shares": sum(h["shares"] for h in hits), "pct": round(sum(h["pct"] for h in hits), 4),
            "names": sorted({h["name"] for h in hits})}


def shp_filings(symbol):
    rows = T.http_json(SHP_MASTER % symbol)
    rows = [r for r in rows if r.get("xbrl") and r["xbrl"].endswith(".xml")]
    rows.sort(key=lambda r: T.parse_date(r["date"]) or dt.datetime.min, reverse=True)
    return rows


# ---------------------------------------------------------------- targets

def write_targets(rows, source, as_of, top=None):
    rows = [r for r in rows if r["weight"] > 0]
    rows.sort(key=lambda r: -r["weight"])
    if top:
        rows = rows[:top]
    tot = sum(r["weight"] for r in rows)
    targets = [{"symbol": r["symbol"], "weight": round(100 * r["weight"] / tot, 2), "name": r.get("name", ""),
                "isin": r.get("isin", "")} for r in rows]
    T.save_json(T.path("targets.json"), {"source": source, "as_of": as_of,
                                         "generated": T.now_ist().isoformat(timespec="seconds"),
                                         "targets": targets})
    print("wrote %s: %d targets, renormalised to 100%%" % (T.path("targets.json"), len(targets)))


def symbols_for(holdings, eq):
    by_isin = T.isin_map(eq)
    for h in holdings:
        h["symbol"] = by_isin.get(h["isin"])
    return holdings


# ---------------------------------------------------------------- commands

def cmd_list(a):
    reg = registry()
    print("Investors (quarterly SHP, holdings of 1% or more only):")
    for i in reg["investors"]:
        print("  %-10s %s  aliases: %d, symbols to check: %s" % (i["id"], i["name"], len(i["aliases"]),
                                                                 " ".join(i.get("check", [])) or "-"))
    print("Funds (monthly full portfolio):")
    for f in reg["funds"]:
        print("  %-10s %s  %s" % (f["id"], f["name"], f.get("auto") and "auto-download" or f["page"]))
    return 0


def cmd_fund(a):
    reg = {f["id"]: f for f in registry()["funds"]}
    eq = T.equity_list(a.equity_list)
    src_now, src_prev = a.source, a.prev
    if a.source.upper() in reg:
        f = reg[a.source.upper()]
        if not f.get("auto"):
            T.die("Download the .xlsx from %s and pass the file path." % f["page"])
        month = a.month or _last_month()
        src_now = ppfas_url(f["code"], month)
        src_prev = src_prev or ppfas_url(f["code"], prev_month(month))
    now = parse_fund(T.read_source(src_now))
    before = None
    if src_prev:
        try:
            before = parse_fund(T.read_source(src_prev))
        except Exception as exc:
            print("note: previous month unavailable (%s)" % str(exc)[:80])
    hs = symbols_for(now["holdings"], eq)
    eq_pct = sum(h["pct_nav"] for h in hs)
    print("%s, portfolio as on %s: %d listed Indian stocks = %.2f%% of NAV"
          % (now["fund"], now["as_of"], len(hs), eq_pct))
    show = hs[:a.top] if a.top else hs
    rows = [[i, h["symbol"] or "?", h["name"][:40], "%.2f%%" % h["pct_nav"], "%.2f%%" % (100 * h["pct_nav"] / eq_pct)]
            for i, h in enumerate(show, 1)]
    print(T.table(rows, ["#", "symbol", "company", "% of NAV", "% of Indian equity"]))
    unmapped = [h["name"] for h in hs if not h["symbol"]]
    if unmapped:
        print("  no NSE symbol (BSE-only or new listing): %s" % ", ".join(unmapped[:8]))
    if before:
        symbols_for(before["holdings"], eq)
        print("\nChanges since %s:" % before["as_of"])
        for kind, h, b in diff(hs, before["holdings"]):
            x = h or b
            q = "" if kind in ("NEW", "SOLD") else " (%s -> %s shares)" % (int(b["qty"]), int(h["qty"]))
            print("  %-7s %-12s %s%s" % (kind, x.get("symbol") or "?", x["name"][:40], q))
    print("\nOther assets in the fund (foreign stocks, debt, cash, arbitrage) are left out. "
          "A fund rebalances daily; this is a month-end snapshot published ~10 days later.")
    if a.write:
        write_targets([{"symbol": h["symbol"], "weight": h["pct_nav"], "name": h["name"], "isin": h["isin"]}
                       for h in hs if h["symbol"]], now["fund"], now["as_of"], a.top)
    return 0


def _last_month():
    d = T.now_ist().date().replace(day=1) - dt.timedelta(days=1)
    if T.now_ist().day < 11:                     # disclosures post by the 10th
        d = d.replace(day=1) - dt.timedelta(days=1)
    return d.strftime("%Y-%m")


def cmd_shp(a):
    if a.file:
        shp = parse_shp(T.read_source(a.file))
    else:
        rows = shp_filings(a.symbol.upper())
        if not rows:
            T.die("No SHP filings for %s on NSE." % a.symbol)
        shp = parse_shp(T.read_source(rows[0]["xbrl"]))
    print("%s (%s) shareholding pattern as of %s, %s shares" % (shp["company"], shp["symbol"], shp["as_of"],
                                                               format(int(shp["total_shares"] or 0), ",")))
    rows = [[h["name"][:60], h["category"][:42], format(int(h["shares"]), ","), "%.2f%%" % h["pct"]]
            for h in shp["holders"]]
    print(T.table(rows, ["holder", "category", "shares", "%"]))
    return 0


def cmd_investor(a):
    inv = find_investor(a.who)
    if a.symbols is not None:
        symbols = a.symbols
    else:
        symbols = [] if a.files else inv.get("check", [])
    symbols = list(dict.fromkeys(s.upper() for s in symbols))
    if not symbols and not a.files:
        T.die("Which stocks? Indian SHPs only name holders of 1%% or more, so give --symbols to check.")
    px = T.prices()
    results = []
    jobs = [(None, f, p) for f, p in zip(a.files or [], (a.prev_files or []) + [None] * len(a.files or []))]
    jobs += [(s, None, None) for s in symbols]
    for sym, f_now, f_prev in jobs:
        try:
            if f_now:
                now = parse_shp(T.read_source(f_now))
                before = parse_shp(T.read_source(f_prev)) if f_prev else None
            else:
                rows = shp_filings(sym)
                now = parse_shp(T.read_source(rows[0]["xbrl"]))
                before = parse_shp(T.read_source(rows[1]["xbrl"])) if len(rows) > 1 else None
        except Exception as exc:
            print("  %s: could not read SHP (%s)" % (sym or f_now, str(exc)[:80]))
            continue
        if any(r["symbol"] == now["symbol"] for r in results):
            continue
        st = investor_stake(now, inv["aliases"])
        pv = investor_stake(before, inv["aliases"]) if before else None
        results.append({"symbol": now["symbol"], "company": now["company"], "as_of": now["as_of"],
                        "stake": st, "prev": pv, "prev_as_of": before and before["as_of"]})
    held = [r for r in results if r["stake"]["shares"] > 0]
    print("%s: %d of %d companies checked show a stake of 1%% or more" % (inv["name"], len(held), len(results)))
    rows = []
    for r in sorted(results, key=lambda r: -(r["stake"]["shares"] * (px.get(r["symbol"]) or 0))):
        s, p = r["stake"], r["prev"]
        if p is None:
            change = "?"
        elif p["shares"] == 0 and s["shares"] > 0:
            change = "NEW"
        elif s["shares"] == 0 and p["shares"] > 0:
            change = "EXITED or <1%"
        elif s["shares"] > p["shares"]:
            change = "ADDED %+d" % (s["shares"] - p["shares"])
        elif s["shares"] < p["shares"]:
            change = "TRIMMED %+d" % (s["shares"] - p["shares"])
        else:
            change = "same" if s["shares"] else "-"
        value = s["shares"] * px[r["symbol"]] if px.get(r["symbol"]) else None
        r["value"] = value
        rows.append([r["symbol"], r["as_of"], format(int(s["shares"]), ","), "%.2f%%" % s["pct"],
                     T.inr(value / 1e7, 1) + " cr" if value else "no price", change])
    print(T.table(rows, ["symbol", "as of", "shares", "% of company", "value", "vs last quarter"]))
    for r in held:
        if len(r["stake"]["names"]) > 1:
            print("  %s: summed %s" % (r["symbol"], "; ".join(r["stake"]["names"])))
    print("Holdings under 1% are not disclosed, so this is a floor, not the whole portfolio.")
    if a.write:
        if any(r["value"] is None for r in held):
            T.die("Weights need prices: run trader-alerts quote %s first." % " ".join(r["symbol"] for r in held))
        write_targets([{"symbol": r["symbol"], "weight": r["value"], "name": r["company"]} for r in held],
                      inv["name"], max(r["as_of"] for r in held), a.top)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    s = sub.add_parser("fund")
    s.add_argument("source", help="registry id (PPFCF) or an .xlsx path/URL")
    s.add_argument("--prev", help="previous month's .xlsx for the diff")
    s.add_argument("--month", help="YYYY-MM for registry downloads")
    s.add_argument("--equity-list", help="NSE EQUITY_L.csv path (default: cached or downloaded)")
    s.add_argument("--top", type=int)
    s.add_argument("--write", action="store_true")
    s = sub.add_parser("shp")
    s.add_argument("symbol", nargs="?", default="")
    s.add_argument("--file")
    s = sub.add_parser("investor")
    s.add_argument("who")
    s.add_argument("--symbols", nargs="*")
    s.add_argument("--files", nargs="*", help="SHP XBRL files instead of downloading")
    s.add_argument("--prev-files", nargs="*")
    s.add_argument("--top", type=int)
    s.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    return {"list": cmd_list, "fund": cmd_fund, "shp": cmd_shp, "investor": cmd_investor}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
