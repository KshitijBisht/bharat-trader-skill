#!/usr/bin/env python3
"""The Earnings Analyst: quarterly results straight from the XBRL companies file with NSE.

Every listed company files its quarterly results (SEBI LODR Reg. 33) as XBRL. This
reads them: revenue from operations, other income, EBITDA, PBT, net profit, diluted
EPS, margins, each quarter against the same quarter a year earlier, and the trailing
twelve months. Consolidated by default (what most analysts quote).

  python3 facts.py ITC                       # the last 5 quarters + TTM, consolidated
  python3 facts.py ITC --standalone
  python3 facts.py ITC TITAN INFY --write    # add to trader/metrics.json for the screener
  python3 facts.py --files q1.xml q2.xml     # offline, saved XBRL
"""

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trader-common"))
import inr as T  # noqa: E402
import xbrl  # noqa: E402

# SEBI's Integrated Filing (from the quarter ended Dec 2024 onward) carries the results;
# older quarters are in the legacy financial-results feed. Both use the same XBRL tags.
INTEGRATED = "https://www.nseindia.com/api/integrated-filing-results?index=equities&symbol=%s"
RESULTS = "https://www.nseindia.com/api/corporates-financial-results?index=equities&symbol=%s&period=Quarterly"
CR = 1e7

FIELDS = {
    "revenue": ["RevenueFromOperations"],
    "other_income": ["OtherIncome"],
    "total_income": ["Income", "TotalIncome"],
    "expenses": ["Expenses", "TotalExpenses"],
    "finance_costs": ["FinanceCosts"],
    "depreciation": ["DepreciationDepletionAndAmortisationExpense", "DepreciationAndAmortisationExpense"],
    "pbt": ["ProfitBeforeTax", "ProfitLossBeforeTax"],
    "exceptional": ["ExceptionalItemsBeforeTax", "ExceptionalItems"],
    "net_profit": ["ProfitLossForPeriod", "ProfitLossForThePeriod"],
    "net_profit_owners": ["ProfitOrLossAttributableToOwnersOfParent"],
    "eps_basic": ["BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
                  "BasicEarningsLossPerShareFromContinuingOperations"],
    "eps_diluted": ["DilutedEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
                    "DilutedEarningsLossPerShareFromContinuingOperations"],
    "paid_up_capital": ["PaidUpValueOfEquityShareCapital"],
    "face_value": ["FaceValueOfEquityShareCapital"],
}
# banks and NBFCs use a different taxonomy (in-bse-fin banking): interest earned, NII...
BANK_FIELDS = {
    "revenue": ["InterestEarned", "RevenueFromOperations", "TotalIncomeFromOperations"],
    "net_profit": ["ProfitLossForThePeriod", "NetProfitLossForThePeriod", "ProfitLossForPeriod"],
    "pbt": ["ProfitLossFromOrdinaryActivitiesBeforeTax", "ProfitBeforeTax"],
    "gross_npa_pct": ["PercentageOfGrossNpa"],
    "net_npa_pct": ["PercentageOfNpa", "PercentageOfNetNpa"],
}


def parse_result(data):
    """One results XBRL -> a quarter record (the 3-month column, context OneD)."""
    f = xbrl.facts(data)
    ctx = "OneD" if "OneD" in f else next((c for c in f if c.endswith("D") and "RevenueFromOperations" in f[c]), None)
    if ctx is None:
        raise ValueError("no quarterly (OneD) context in this XBRL")
    q = f[ctx]
    rec = {"symbol": xbrl.first(f, "Symbol"), "company": xbrl.first(f, "NameOfTheCompany"),
           "start": q.get("DateOfStartOfReportingPeriod"), "end": q.get("DateOfEndOfReportingPeriod"),
           "basis": q.get("NatureOfReportStandaloneConsolidated"),
           "quarter": xbrl.first(f, "ReportingQuarter"), "audited": xbrl.first(f, "WhetherResultsAreAuditedOrUnaudited")}
    fields = dict(FIELDS)
    if "InterestEarned" in q:
        fields.update(BANK_FIELDS)
        rec["bank"] = True
    for k, tags in fields.items():
        for t in tags:
            v = T.num(q.get(t))
            if v is not None:
                rec[k] = v
                break
    rev, np_ = rec.get("revenue"), rec.get("net_profit")
    if rec.get("pbt") is not None:
        ebitda = rec["pbt"] + (rec.get("finance_costs") or 0) + (rec.get("depreciation") or 0) \
            - (rec.get("other_income") or 0) - (rec.get("exceptional") or 0)
        rec["ebitda"] = ebitda
        if rev:
            rec["ebitda_margin"] = round(100 * ebitda / rev, 2)
    if rev and np_ is not None:
        rec["net_margin"] = round(100 * np_ / rev, 2)
    if rev and rec.get("pbt") is not None:
        rec["pbt_margin"] = round(100 * rec["pbt"] / rev, 2)
    if rec.get("total_income") and rec.get("other_income") is not None:
        rec["other_income_share"] = round(100 * rec["other_income"] / rec["total_income"], 2)
    if rec.get("paid_up_capital") and rec.get("face_value"):
        rec["shares"] = rec["paid_up_capital"] / rec["face_value"]
    return rec


def yoy(cur, prev, key):
    a, b = cur.get(key), (prev or {}).get(key)
    if a is None or not b:
        return None
    return round(100 * (a - b) / abs(b), 2)


def summarise(quarters):
    qs = sorted(quarters, key=lambda q: q["end"], reverse=True)
    by_end = {q["end"]: q for q in qs}
    for q in qs:
        end = dt.date.fromisoformat(q["end"])
        try:
            ly = end.replace(year=end.year - 1).isoformat()
        except ValueError:
            ly = (end - dt.timedelta(days=365)).isoformat()
        prev = by_end.get(ly)
        q["revenue_yoy"] = yoy(q, prev, "revenue")
        q["net_profit_yoy"] = yoy(q, prev, "net_profit")
        q["eps_yoy"] = yoy(q, prev, "eps_diluted")
    ttm = None
    if len(qs) >= 4:
        last4 = qs[:4]
        ttm = {"end": qs[0]["end"]}
        for k in ("revenue", "net_profit", "eps_diluted", "ebitda"):
            vals = [q.get(k) for q in last4]
            ttm[k] = sum(vals) if all(v is not None for v in vals) else None
        if ttm["revenue"] and ttm["net_profit"] is not None:
            ttm["net_margin"] = round(100 * ttm["net_profit"] / ttm["revenue"], 2)
    return qs, ttm


def filings(symbol, consolidated=True, integrated=None, legacy=None):
    """[{"end": date, "xbrl": url}] newest first, one per quarter."""
    out = {}
    try:
        data = integrated if integrated is not None else T.http_json(INTEGRATED % symbol)
        want = "Consolidated" if consolidated else "Standalone"
        for r in data.get("data", []):
            if "Financials" not in (r.get("type") or "") or r.get("consolidated") != want:
                continue
            d = T.parse_date(r.get("qe_Date"))
            if d and r.get("xbrl", "").endswith(".xml"):
                out.setdefault(d.date(), {"end": d.date().isoformat(), "xbrl": r["xbrl"], "feed": "integrated"})
    except Exception:
        pass
    try:
        rows = legacy if legacy is not None else T.http_json(RESULTS % symbol)
        want = "Consolidated" if consolidated else "Non-Consolidated"
        for r in rows:
            if r.get("consolidated") != want or not r.get("xbrl", "").endswith(".xml"):
                continue
            d = T.parse_date(r.get("toDate"))
            if d:
                out.setdefault(d.date(), {"end": d.date().isoformat(), "xbrl": r["xbrl"], "feed": "legacy"})
    except Exception:
        pass
    return [out[k] for k in sorted(out, reverse=True)]


def metrics_row(sym, qs, ttm, px):
    latest = qs[0]
    row = {"symbol": sym, "company": latest.get("company"), "as_of": latest["end"], "basis": latest.get("basis"),
           "revenue_cr": round(latest["revenue"] / CR, 2) if latest.get("revenue") else None,
           "revenue_yoy": latest.get("revenue_yoy"), "net_profit_yoy": latest.get("net_profit_yoy"),
           "eps_yoy": latest.get("eps_yoy"), "ebitda_margin": latest.get("ebitda_margin"),
           "net_margin": latest.get("net_margin"), "other_income_share": latest.get("other_income_share")}
    if ttm:
        row["ttm_revenue_cr"] = round(ttm["revenue"] / CR, 2) if ttm.get("revenue") else None
        row["ttm_net_profit_cr"] = round(ttm["net_profit"] / CR, 2) if ttm.get("net_profit") is not None else None
        row["ttm_eps"] = round(ttm["eps_diluted"], 2) if ttm.get("eps_diluted") is not None else None
        row["ttm_net_margin"] = ttm.get("net_margin")
    price = px.get(sym)
    if price:
        row["price"] = price
        if row.get("ttm_eps"):
            row["pe"] = round(price / row["ttm_eps"], 2) if row["ttm_eps"] > 0 else None
            row["earnings_yield"] = round(100 * row["ttm_eps"] / price, 2)
        if latest.get("shares"):
            row["market_cap_cr"] = round(price * latest["shares"] / CR, 0)
    return row


def show(sym, qs, ttm):
    print("%s (%s), %s, rupees crore" % (qs[0].get("company"), sym, qs[0].get("basis")))
    rows = []
    for q in qs:
        rows.append([q["end"], _cr(q.get("revenue")), _pc(q.get("revenue_yoy")), _cr(q.get("ebitda")),
                     _pc(q.get("ebitda_margin"), False), _cr(q.get("net_profit")), _pc(q.get("net_profit_yoy")),
                     _pc(q.get("net_margin"), False), "%.2f" % q["eps_diluted"] if q.get("eps_diluted") is not None else "-",
                     _pc(q.get("eps_yoy"))])
    print(T.table(rows, ["quarter", "revenue", "yoy", "EBITDA", "margin", "net profit", "yoy", "net margin",
                         "dil. EPS", "yoy"]))
    if ttm:
        print("TTM to %s: revenue %s cr, net profit %s cr (%s), diluted EPS %s"
              % (ttm["end"], _cr(ttm.get("revenue")), _cr(ttm.get("net_profit")), _pc(ttm.get("net_margin"), False),
                 "%.2f" % ttm["eps_diluted"] if ttm.get("eps_diluted") is not None else "-"))
    q = qs[0]
    if q.get("other_income_share") and q["other_income_share"] > 15:
        print("note: other income is %.1f%% of total income; core operations earn less than the bottom line shows."
              % q["other_income_share"])
    if q.get("exceptional"):
        print("note: exceptional items of %s cr in the latest quarter." % _cr(q["exceptional"]))


def _cr(v):
    return "-" if v is None else format(round(v / CR, 2), ",.2f")


def _pc(v, sign=True):
    return "-" if v is None else (("%+.1f%%" if sign else "%.1f%%") % v)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--quarters", type=int, default=5)
    ap.add_argument("--standalone", action="store_true")
    ap.add_argument("--files", nargs="*", help="saved results XBRL (one company)")
    ap.add_argument("--write", action="store_true", help="merge into trader/metrics.json")
    a = ap.parse_args(argv)
    if not a.symbols and not a.files:
        T.die("Which company? e.g. facts.py ITC")
    px = T.prices()
    metrics = T.load_json(T.path("metrics.json"), {"companies": {}}) or {"companies": {}}
    jobs = [(None, a.files)] if a.files else [(s.upper(), None) for s in a.symbols]
    for sym, files in jobs:
        try:
            if files:
                qs = [parse_result(T.read_source(f)) for f in files]
            else:
                rows = filings(sym, not a.standalone)[:max(a.quarters, 8)]
                if not rows:
                    print("%s: no XBRL results on NSE (try --standalone)" % sym)
                    continue
                qs = []
                for r in rows:
                    try:
                        qs.append(parse_result(T.read_source(r["xbrl"])))
                    except Exception as exc:
                        print("  skipped %s %s: %s" % (sym, r["end"], str(exc)[:60]))
        except Exception as exc:
            print("%s: %s" % (sym, str(exc)[:120]))
            continue
        qs = [q for q in qs if q.get("end")]
        if not qs:
            continue
        sym = sym or qs[0]["symbol"]
        qs, ttm = summarise(qs)
        show(sym, qs[:a.quarters], ttm)
        print()
        metrics["companies"][sym] = metrics_row(sym, qs, ttm, px)
    if a.write:
        metrics["updated"] = T.now_ist().isoformat(timespec="seconds")
        T.save_json(T.path("metrics.json"), metrics)
        print("-> %s (%d companies). Next: /trader-screener." % (T.path("metrics.json"), len(metrics["companies"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
