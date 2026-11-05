#!/usr/bin/env python3
"""The News Monitor: NSE corporate announcements + headlines for what you hold.

Sources:
  * NSE corporate announcements (Reg. 30 LODR disclosures: results, board meetings,
    acquisitions, credit ratings, auditor or KMP resignations, pledges, orders...)
  * Google News RSS per company (en-IN), and Economic Times / Moneycontrol market feeds

  python3 news.py --symbols ITC TITAN --hours 48     # only items newer than 48 hours
  python3 news.py                                    # holdings + targets + watchlist
  python3 news.py --new                              # only items not shown before
  python3 news.py --market                           # the market-wide feeds too
"""

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import os
import re
import sys
import urllib.parse
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trader-common"))
import inr as T  # noqa: E402

ANN = "https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=%s"
GNEWS = "https://news.google.com/rss/search?q=%s&hl=en-IN&gl=IN&ceid=IN:en"
MARKET_FEEDS = [
    ("ET Markets", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
    ("Moneycontrol", "https://www.moneycontrol.com/rss/latestnews.xml"),
]

# what matters, roughly in order of how much it can move a stock
FLAGS = [
    ("RED", r"\bresign\w*\b.*\bauditor|\bauditors?\b.*\bresign|\bdefault(s|ed)?\b|\binsolven|\bIBC\b|\bNCLT\b|"
            r"\bfraud|\bforensic|\bSEBI order|\bsearch (and|&) (seizure|survey)|\braids?\b|\bEnforcement Directorate\b|"
            r"\bqualified opinion|\bgoing concern|\bdelist|\bsuspen(d|sion)"),
    ("RED", r"\bpledg|\binvocation|\bencumbr"),
    ("RESULTS", r"\bfinancial results?\b|\bquarterly results?\b|\bresults? for the (quarter|period)|\bQ[1-4] ?FY ?\d"),
    ("DEAL", r"\bacqui(re|sition)|\bmerger|\bamalgamat|\bdemerger|\bscheme of arrangement|\bopen offer|\bbuy-?back|"
             r"\bstake sale|\bdivest|\bjoint venture|\btakeover|\bSAST\b"),
    ("PEOPLE", r"\bresign|\bappoint|\bcessation|\bCEO\b|\bmanaging director|\bCFO\b|\bkey managerial"),
    ("MONEY", r"\bdividend|\bbonus\b|\bstock split|\bsub-division|\brights issue|\brecord date|\bQIP\b|"
              r"\bpreferential|\bfund ?rais"),
    ("RATING", r"\bcredit rating|\brating action|\bdowngrade|\bupgrade"),
    ("ORDER", r"\border (win|receiv|bagg)|\bbags? (an? )?order|\bletter of award|\bwins? (a |an )?contract"),
]
NOISE = (r"newspaper publication|trading window|loss of share certificate|duplicate share|"
         r"certificate under sebi \(depositories|regulation 74\(5\)|investor (meet|conference)|"
         r"analysts?/institutional investor meet|con\. call|ESOP|allotment of (equity )?shares under|"
         r"share price|stock price - live")


def classify(text):
    if re.search(NOISE, text, re.I):
        return "noise"
    for tag, pat in FLAGS:
        if re.search(pat, text, re.I):
            return tag
    return ""


def parse_announcements(data):
    out = []
    for r in data or []:
        when = T.parse_date(r.get("an_dt") or r.get("sort_date"))
        subject = (r.get("desc") or "").strip()
        body = (r.get("attchmntText") or "").strip()
        text = "%s: %s" % (subject, body)
        out.append({"id": "nse:%s" % (r.get("seq_id") or hashlib.sha1(text.encode()).hexdigest()[:12]),
                    "symbol": r.get("symbol"), "source": "NSE filing",
                    "when": when.replace(tzinfo=T.IST) if when else None,
                    "title": "%s - %s" % (subject, body[:220]) if body else subject,
                    "link": r.get("attchmntFile"), "flag": classify(text)})
    return out


def parse_rss(xml, symbol=None, source="news"):
    out = []
    try:
        root = ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    except ET.ParseError:
        return out
    for it in root.iter("item"):
        title = html.unescape((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate")
        when = None
        if pub:
            try:
                when = email.utils.parsedate_to_datetime(pub).astimezone(T.IST)
            except (TypeError, ValueError):
                when = None
        src = it.find("source")
        name = src.text if src is not None and src.text else source
        out.append({"id": "rss:" + hashlib.sha1((link or title).encode()).hexdigest()[:16], "symbol": symbol,
                    "source": name, "when": when, "title": title, "link": link, "flag": classify(title)})
    return out


def company_query(sym, eq):
    name = (eq.get(sym) or {}).get("name") or sym
    name = re.sub(r"\b(limited|ltd\.?|india)\b", "", name, flags=re.I).strip()
    return '"%s" share OR stock OR NSE' % name


def gather(symbols, hours, market=False, eq=None, files=None):
    eq = eq or {}
    since = T.now_ist() - dt.timedelta(hours=hours)
    items, errors = [], []
    files = files or {}
    for sym in symbols:
        try:
            src = files.get(("ann", sym))
            data = T.load_json(src) if src else T.http_json(ANN % sym)
            items += parse_announcements(data)
        except Exception as exc:
            errors.append("%s NSE: %s" % (sym, str(exc)[:70]))
        try:
            src = files.get(("rss", sym))
            xml = open(src, encoding="utf-8").read() if src else \
                T.http_text(GNEWS % urllib.parse.quote(company_query(sym, eq)))
            items += parse_rss(xml, sym, "Google News")
        except Exception as exc:
            errors.append("%s news: %s" % (sym, str(exc)[:70]))
    if market:
        for name, url in MARKET_FEEDS:
            try:
                src = files.get(("market", name))
                xml = open(src, encoding="utf-8").read() if src else T.http_text(url)
                items += parse_rss(xml, None, name)
            except Exception as exc:
                errors.append("%s: %s" % (name, str(exc)[:70]))
    items = [i for i in items if i["when"] is None or i["when"] >= since]
    uniq = {}
    for i in items:
        uniq.setdefault(i["id"], i)
    items = sorted(uniq.values(), key=lambda i: i["when"] or dt.datetime.min.replace(tzinfo=T.IST), reverse=True)
    return items, errors


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", nargs="*")
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--new", action="store_true", help="hide items shown before")
    ap.add_argument("--market", action="store_true")
    ap.add_argument("--all", action="store_true", help="include routine filings (newspaper ads, trading window...)")
    ap.add_argument("--limit", type=int, default=20, help="per section")
    ap.add_argument("--links", action="store_true", help="print each item's link")
    a = ap.parse_args(argv)

    syms = [s.upper() for s in a.symbols] if a.symbols else None
    if syms is None:
        held = set()
        port = T.load_json(T.path("portfolio.json"), {}) or {}
        held |= set((port.get("positions") or {}).keys())
        tg = T.load_json(T.path("targets.json"), {}) or {}
        held |= {t["symbol"] for t in tg.get("targets", [])}
        held |= {s.upper() for s in T.config().get("watchlist", [])}
        syms = sorted(held)
    if not syms and not a.market:
        T.die("No symbols. Pass --symbols ITC TITAN, or hold something, or use --market.")
    try:
        eq = T.equity_list() if syms else {}
    except Exception:
        eq = {}
    items, errors = gather(syms, a.hours, a.market, eq)
    seen = T.load_json(T.path("news-seen.json"), {"ids": []}) or {"ids": []}
    ids = set(seen["ids"])
    if a.new:
        items = [i for i in items if i["id"] not in ids]
    if not a.all:
        items = [i for i in items if i["flag"] != "noise"]
    filings = [i for i in items if i["source"] == "NSE filing"][:a.limit]
    heads = [i for i in items if i["source"] != "NSE filing"][:a.limit]
    shown = filings + heads
    for title, group in (("Exchange filings (NSE)", filings), ("Headlines", heads)):
        if not group:
            continue
        print("== %s" % title)
        for i in group:
            when = i["when"].strftime("%d %b %H:%M") if i["when"] else "?"
            flag = ("[%s] " % i["flag"]) if i["flag"] else ""
            print("%s  %-10s %s%s  (%s)" % (when, i["symbol"] or "market", flag, i["title"][:200], i["source"]))
            if i["link"] and a.links:
                print("               %s" % i["link"])
    if not shown:
        print("Nothing %sin the last %g hours for %s." % ("new " if a.new else "", a.hours, ", ".join(syms) or "the market"))
    for e in errors:
        print("  (source unavailable: %s)" % e)
    seen["ids"] = sorted(ids | {i["id"] for i in shown})[-20000:]
    T.save_json(T.path("news-seen.json"), seen)
    red = [i for i in shown if i["flag"] == "RED"]
    if red:
        print("\n%d RED item(s): read the filing itself before acting. A headline is not a reason to trade." % len(red))
    return 0


if __name__ == "__main__":
    sys.exit(main())
